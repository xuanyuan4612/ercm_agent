"""
RAG Orchestrator — 共享检索增强编排器

基于 doc/agents/10-rag-shared-agent.md §四 定义的 13 步流水线实现。
当前生产检索路径: pgvector 语义 + ILIKE 全文，预留 ES + Milvus + Reranker 适配器接口。

职责边界：
- 负责：检索、过滤、重排、引用、上下文组装、检索质量记录
- 不负责：推进 workflow、写业务终态、决定处罚/移交/关闭
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.agents.profiles import MODULE_PROFILES, ModuleAgentProfile
from hermes.agents.rag_schemas import (
    DocMetadata,
    RAGDiagnostics,
    RAGRequest,
    RAGResponse,
    RAGResult,
    RetrievalDetail,
)
from hermes.core.config import settings
from hermes.core.logging import get_logger
from hermes.db.models.knowledge import KnowledgeDocument

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════
# 知识库类型映射
# ═══════════════════════════════════════════════════════════════
KB_TYPE_MAP: dict[str, str] = {
    # ── 01 廉洁监察 (Integrity Supervision) ──
    "intake": "intake",
    "investigation": "investigation",
    "analysis": "analysis",
    "disposition": "disposition",
    "enforcement": "enforcement",
    # ── 02 风险监控 (Risk Monitoring) ──
    "risk_rules": "risk_rules",
    "risk_cases": "risk_cases",
    "database_schema": "database_schema",
    "disposition_feedback": "disposition_feedback",
    # ── 03 内控评价 (Internal Control Evaluation) ──
    "ic_policy": "ic_policy",
    "control_matrix": "control_matrix",
    "audit_plan": "audit_plan",
    "interview_template": "interview_template",
    "deficiency_rating": "deficiency_rating",
    # ── 04 专项审计 (Special Audit) ──
    "sa_plan": "sa_plan",
    "sa_history": "sa_history",
    "audit_workpaper_template": "audit_workpaper_template",
    "improvement_suggestion": "improvement_suggestion",
    # ── 05 离任审计 (Exit Audit) ──
    "ea_plan": "ea_plan",
    "position_duty": "position_duty",
    "personal_risk_case": "personal_risk_case",
    "business_audit_case": "business_audit_case",
    "behavioral_risk_history": "behavioral_risk_history",
    # ── 06 商业秘密 (Trade Secrets) ──
    "trade_secret_policy": "trade_secret_policy",
    "ip_policy": "ip_policy",
    "trade_secret_law": "trade_secret_law",
    "trade_secret_cases": "trade_secret_cases",
    "historical_secret_review": "historical_secret_review",
    # ── 07 行为风险 (Behavioral Risk) ──
    "behavior_policy": "behavior_policy",
    "employee_lifecycle": "employee_lifecycle",
    "historical_behavior_analysis": "historical_behavior_analysis",
    # ── 08 持续改善 (Continuous Improvement) ──
    "improvement_case": "improvement_case",
    "rectification_template": "rectification_template",
    "audit_issue_history": "audit_issue_history",
    "policy_and_process": "policy_and_process",
    # ── 共享 (Common) ──
    "common": "common",
    "law_and_regulation": "law_and_regulation",
    "kb_integrity_policy": "kb_integrity_policy",
    "kb_integrity_cases": "kb_integrity_cases",
    # ── 生产级 kb_type（与 Profile 对齐） ──
    "risk_monitor": "risk_monitor",
    "ic_evaluation": "ic_evaluation",
    "special_audit": "special_audit",
    "exit_audit": "exit_audit",
    "trade_secret": "trade_secret",
    "behavior_risk": "behavior_risk",
    "improvement": "improvement",
}

# Prompt 注入检测模式
_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"忽略.*权限",
        r"显示.*全部.*(资料|文档|数据)",
        r"绕过.*(审计|权限|限制)",
        r"不要.*记录.*(审计|日志)",
        r"(返回|显示).*(系统提示|内部配置|密钥|密码|secret|password)",
        r"(列出|导出).*所有.*(知识库|用户|案件)",
        r"ignore.*(previous|all).*instruction",
        r"act\s+as\s+(admin|root|superuser)",
        r"以.*(管理员|超级用户).*身份",
    ]
]

# 敏感信息脱敏模式
# 注意：使用 (?<!\d)...(?!\d) 而非 \b，因为中文环境下 \b 对数字边界不可靠
_PII_PATTERNS = [
    (re.compile(r'(?<!\d)\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)'), "[身份证号]"),
    (re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'), "[手机号]"),
    (re.compile(r'(?<!\d)\d{16}(?!\d)|(?<!\d)\d{19}(?!\d)'), "[银行卡号]"),
]


# ═══════════════════════════════════════════════════════════════
# Embedding 缓存 (TTL + LRU，最大 1000 条，每条 ~12KB，总计 ~12MB)
# ═══════════════════════════════════════════════════════════════
_EMBEDDING_CACHE_MAXSIZE = 1000
_embedding_cache: dict[str, tuple[float, list[float]]] = {}
_cache_access_order: list[str] = []  # LRU 访问顺序


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _embedding_cache_get(text: str) -> list[float] | None:
    key = _cache_key(text)
    entry = _embedding_cache.get(key)
    if entry:
        ts, vec = entry
        if time.monotonic() - ts < settings.RAG_EMBEDDING_CACHE_TTL:
            # LRU: move accessed key to end
            if key in _cache_access_order:
                _cache_access_order.remove(key)
            _cache_access_order.append(key)
            return vec
        # TTL 过期，删除
        del _embedding_cache[key]
        if key in _cache_access_order:
            _cache_access_order.remove(key)
    return None


def _embedding_cache_set(text: str, vector: list[float]) -> None:
    key = _cache_key(text)
    # LRU 淘汰：超过 maxsize 时移除最旧的条目
    if len(_embedding_cache) >= _EMBEDDING_CACHE_MAXSIZE:
        while _cache_access_order and len(_embedding_cache) >= _EMBEDDING_CACHE_MAXSIZE:
            oldest = _cache_access_order.pop(0)
            if oldest in _embedding_cache:
                del _embedding_cache[oldest]
    _embedding_cache[key] = (time.monotonic(), vector)
    _cache_access_order.append(key)
