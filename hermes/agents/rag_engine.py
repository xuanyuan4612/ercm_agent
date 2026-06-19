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


# ═══════════════════════════════════════════════════════════════
# RAG Orchestrator
# ═══════════════════════════════════════════════════════════════

class RAGOrchestrator:
    """RAG 编排器 — 13 步检索流水线

    使用方式:
        orch = RAGOrchestrator(db_session)
        response = await orch.retrieve(request)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── 公开方法 ─────────────────────────────────────────────────

    async def retrieve(self, request: RAGRequest) -> RAGResponse:
        """执行完整 13 步检索流水线，返回标准 RAG 响应"""
        t_start = time.monotonic()
        diag = RAGDiagnostics(recall_mode=request.mode)

        # S1: 请求校验
        self._validate_request(request)

        # S2: 权限解析 → metadata_filter
        profile = MODULE_PROFILES.get(request.module)
        metadata_filter = self._resolve_permissions(request, profile)

        # S3: 查询预处理
        queries, injection_suspected = self._preprocess_query(request.query)
        diag.query_count = len(queries)
        diag.prompt_injection_suspected = injection_suspected

        # S4: Embedding 向量化
        t_emb = time.monotonic()
        query_embeddings: list[list[float]] = []
        embedding_available = True
        for q in queries:
            vec = await self._get_embedding(q)
            if vec:
                query_embeddings.append(vec)
            else:
                embedding_available = False
        if not embedding_available:
            diag.embedding_unavailable = True
            diag.degraded = True
            diag.degrade_reasons.append("embedding_unavailable")

        # S5: 双路召回（并行）
        t_search = time.monotonic()
        vector_candidates, keyword_candidates = await asyncio.gather(
            self._vector_recall(query_embeddings, metadata_filter, request.top_k),
            self._keyword_recall(queries, metadata_filter, request.top_k),
        )
        diag.vector_latency_ms = int((time.monotonic() - t_search) * 1000)
        diag.search_latency_ms = diag.vector_latency_ms  # 两路并行，取较大者近似

        # S6: 候选合并去重 + RRF 融合
        merged = self._merge_and_fuse(
            vector_candidates, keyword_candidates, request.mode
        )

        # S7-S13 见 Part 3
        # S7: 二次硬过滤
        filtered, blocked = self._hard_filter(merged, metadata_filter, profile, request)
        diag.blocked_candidates = blocked

        # S8: Rerank 精排
        t_rerank = time.monotonic()
        reranked, reranker_ok = await self._rerank(filtered, queries[0])
        diag.rerank_latency_ms = int((time.monotonic() - t_rerank) * 1000)
        if not reranker_ok:
            diag.reranker_unavailable = True
            diag.degraded = True
            diag.degrade_reasons.append("reranker_unavailable")

        # S9: 引用校验
        verified = self._verify_citations(reranked)

        # S10: 上下文组装
        context = self._assemble_context(verified)

        # S11: 质量诊断
        top_k_results = verified[:request.top_k]
        self._finalize_diagnostics(diag, top_k_results, request.top_k)

        # S12: 观测日志
        diag.total_latency_ms = int((time.monotonic() - t_start) * 1000)

        return RAGResponse(
            results=[self._to_rag_result(r) for r in top_k_results],
            context=context,
            knowledge_refs=[r["chunk_id"] for r in top_k_results],
            diagnostics=diag,
        )

    async def search(
        self,
        query: str,
        kb_types: list[str] | None = None,
        top_k: int = 5,
        mode: str = "hybrid",
    ) -> list[dict[str, Any]]:
        """简化搜索（兼容旧调用方），返回旧 dict 格式。"""
        if kb_types is None:
            kb_types = list(KB_TYPE_MAP.keys())

        request = RAGRequest(
            query=query,
            module="common",
            stage="search",
            tenant_scope={"client": "group", "org_ids": ["*"], "role": "admin", "security_levels": ["public", "internal", "confidential", "secret"]},
            trace_id="search-api",
            kb_types=kb_types,
            top_k=top_k,
            mode=mode,  # type: ignore[arg-type]
        )
        response = await self.retrieve(request)
        return [
            {
                "doc_id": r.doc_id,
                "kb_type": r.kb_type,
                "title": r.title,
                "content_snippet": r.content_snippet,
                "relevance": r.relevance,
                "updated_at": r.metadata.effective_at,
            }
            for r in response.results
        ]

    def get_retrieval_context(
        self,
        query: str,
        kb_types: list[str],
        top_k: int = 5,
    ) -> str:
        """获取格式化后的检索上下文（同步包装）"""
        import asyncio as _asyncio
        return _asyncio.run(self._get_context_async(query, kb_types, top_k))

    async def _get_context_async(
        self, query: str, kb_types: list[str], top_k: int
    ) -> str:
        request = RAGRequest(
            query=query,
            module="common",
            stage="context",
            tenant_scope={"client": "group", "org_ids": ["*"], "role": "admin", "security_levels": ["public", "internal", "confidential", "secret"]},
            trace_id="context-api",
            kb_types=kb_types,
            top_k=top_k,
        )
        response = await self.retrieve(request)
        return response.context

    # ── S1: 请求校验 ────────────────────────────────────────────

    @staticmethod
    def _validate_request(request: RAGRequest) -> None:
        """校验请求必填字段，截断超限 top_k"""
        if not request.query.strip():
            raise ValueError("query 不能为空")
        if request.top_k > settings.RAG_MAX_TOP_K:
            object.__setattr__(request, "top_k", settings.RAG_MAX_TOP_K)

    # ── S2: 权限解析 ────────────────────────────────────────────

    @staticmethod
    def _resolve_permissions(
        request: RAGRequest, profile: ModuleAgentProfile | None
    ) -> dict[str, Any]:
        """合并 Profile + 请求参数 → 统一 metadata_filter"""
        if request.kb_types:
            kb_types = request.kb_types
        elif profile and profile.knowledge_scopes:
            kb_types = [s for s in profile.knowledge_scopes if s in KB_TYPE_MAP]
        else:
            kb_types = list(KB_TYPE_MAP.keys())

        ts = request.tenant_scope

        return {
            "kb_types": kb_types,
            "client": [ts.client, "group"],
            "org_ids": list(set(ts.org_ids + ["*"])),
            "security_levels": ts.security_levels,
            "is_active": True,
            "approval_status": "approved",
        }

    # ── S3: 查询预处理 ───────────────────────────────────────────

    @staticmethod
    def _preprocess_query(query: str) -> tuple[list[str], bool]:
        """清洗、脱敏、检测注入，生成 1-5 个子查询"""
        injection_suspected = False

        # 清洗
        cleaned = query.strip()
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', cleaned)

        # 脱敏
        for pattern, replacement in _PII_PATTERNS:
            cleaned = pattern.sub(replacement, cleaned)

        # 注入检测
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(query):
                injection_suspected = True
                logger.warning(
                    "rag_prompt_injection_suspected",
                    query_hash=hashlib.sha256(query.encode()).hexdigest()[:16],
                )
                break

        if injection_suspected:
            return [cleaned], True

        # 超长 query 截断
        if len(cleaned) > 500:
            cleaned = cleaned[:500]

        # 子查询生成：按分号/问号拆分
        sub_queries = [cleaned]
        separators = re.split(r'[；;？?。]', cleaned)
        if len(separators) > 1:
            meaningful = [s.strip() for s in separators if len(s.strip()) > 5]
            if meaningful:
                sub_queries = meaningful[:5]

        return sub_queries, False

    # ── S4: Embedding ────────────────────────────────────────────

    async def _get_embedding(self, text: str) -> list[float] | None:
        """获取文本 embedding，优先使用缓存"""
        cached = _embedding_cache_get(text)
        if cached:
            return cached

        try:
            api_key = settings.EMBEDDING_API_KEY.get_secret_value()
            if not api_key:
                return None

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{settings.EMBEDDING_API_BASE}/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": settings.EMBEDDING_MODEL, "input": text},
                )
                if response.status_code == 200:
                    data = response.json()
                    vec = data["data"][0]["embedding"]
                    if len(vec) == settings.EMBEDDING_DIM:
                        _embedding_cache_set(text, vec)
                        return vec
                    logger.warning("embedding_dimension_mismatch", expected=settings.EMBEDDING_DIM, got=len(vec))
                    return None
                logger.warning("embedding_api_failed", status=response.status_code)
                return None
        except Exception as e:
            logger.warning("embedding_api_error", error=str(e))
            return None

    # ── S5: 向量召回 ────────────────────────────────────────────

    async def _vector_recall(
        self,
        embeddings: list[list[float]],
        metadata_filter: dict,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """PGVector 余弦相似度语义召回"""
        if not embeddings:
            return []

        recall_n = top_k * settings.RAG_RECALL_MULTIPLIER
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        for emb in embeddings[:3]:
            embedding_str = f"[{','.join(str(x) for x in emb)}]"

            try:
                query_sql = text("""
                    SELECT id, kb_type, title,
                           substring(content, 1, 300) AS content_snippet,
                           1.0 - (embedding <=> :emb::vector) AS vector_score,
                           source_path, chunk_index, total_chunks,
                           metadata_, security_level, client, org_id,
                           approval_status
                    FROM knowledge_documents
                    WHERE kb_type = ANY(:kb_types)
                      AND is_active = true
                      AND embedding IS NOT NULL
                      AND approval_status = 'approved'
                      AND client = ANY(:clients)
                      AND security_level = ANY(:security_levels)
                    ORDER BY embedding <=> :emb::vector
                    LIMIT :limit
                """)
                result = await self.db.execute(
                    query_sql,
                    {
                        "kb_types": metadata_filter["kb_types"],
                        "clients": metadata_filter.get("client", ["group"]),
                        "security_levels": metadata_filter.get("security_levels", ["public", "internal"]),
                        "emb": embedding_str,
                        "limit": recall_n,
                    },
                )
                for row in result.fetchall():
                    doc_id = str(row[0])
                    if doc_id in seen:
                        continue
                    seen.add(doc_id)
                    candidates.append({
                        "doc_id": doc_id,
                        "chunk_id": f"{doc_id}:{row[6] or 1}",
                        "kb_type": row[1],
                        "title": row[2],
                        "content_snippet": row[3] or "",
                        "source_path": row[5],
                        "chunk_index": row[6] or 1,
                        "total_chunks": row[7] or 1,
                        "vector_score": float(row[4]) if row[4] else 0.0,
                        "keyword_score": None,
                        "channels": ["vector"],
                        "metadata_": row[8] or {},
                        "security_level": row[9] or "internal",
                        "client": row[10] or "group",
                        "org_id": row[11] or "*",
                        "approval_status": row[12] or "approved",
                    })
            except Exception as e:
                logger.warning("vector_recall_failed", error=str(e))

        return candidates

    # ── S5: 全文召回 ────────────────────────────────────────────

    async def _keyword_recall(
        self,
        queries: list[str],
        metadata_filter: dict,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """ILIKE 全文召回（生产环境替换为 Elasticsearch）"""
        recall_n = top_k * settings.RAG_RECALL_MULTIPLIER
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        for q in queries[:3]:
            try:
                pattern = f"%{q}%"
                exact_pattern = f"%{q.strip()}%"

                where_clauses = [
                    KnowledgeDocument.kb_type.in_(metadata_filter["kb_types"]),
                    KnowledgeDocument.is_active == True,
                    KnowledgeDocument.approval_status == "approved",
                    or_(
                        KnowledgeDocument.title.ilike(pattern),
                        KnowledgeDocument.content.ilike(pattern),
                    ),
                ]
                if metadata_filter.get("client"):
                    where_clauses.append(KnowledgeDocument.client.in_(metadata_filter["client"]))
                if metadata_filter.get("security_levels"):
                    where_clauses.append(KnowledgeDocument.security_level.in_(metadata_filter["security_levels"]))

                stmt = (
                    select(
                        KnowledgeDocument.id,
                        KnowledgeDocument.kb_type,
                        KnowledgeDocument.title,
                        func.substring(KnowledgeDocument.content, 1, 300).label("content_snippet"),
                        KnowledgeDocument.source_path,
                        KnowledgeDocument.chunk_index,
                        KnowledgeDocument.total_chunks,
                        KnowledgeDocument.metadata_,
                        KnowledgeDocument.security_level,
                        KnowledgeDocument.client,
                        KnowledgeDocument.org_id,
                        KnowledgeDocument.approval_status,
                    )
                    .where(and_(*where_clauses))
                    .order_by(KnowledgeDocument.updated_at.desc())
                    .limit(recall_n)
                )

                result = await self.db.execute(stmt)
                rows = result.fetchall()

                for row in rows:
                    doc_id = str(row[0])
                    if doc_id in seen:
                        continue
                    seen.add(doc_id)

                    # 简单 keyword_score 基于标题匹配
                    title = row[2] or ""
                    content_snippet = row[3] or ""
                    if q.lower() in title.lower():
                        ks = 0.80
                    elif q.lower() in content_snippet.lower():
                        ks = 0.55
                    else:
                        ks = 0.30

                    candidates.append({
                        "doc_id": doc_id,
                        "chunk_id": f"{doc_id}:{row[5] or 1}",
                        "kb_type": row[1],
                        "title": title,
                        "content_snippet": content_snippet or "",
                        "source_path": row[4],
                        "chunk_index": row[5] or 1,
                        "total_chunks": row[6] or 1,
                        "vector_score": None,
                        "keyword_score": ks,
                        "channels": ["keyword"],
                        "metadata_": row[7] or {},
                        "security_level": row[8] or "internal",
                        "client": row[9] or "group",
                        "org_id": row[10] or "*",
                        "approval_status": row[11] or "approved",
                    })
            except Exception as e:
                logger.warning("keyword_recall_failed", error=str(e))

        return candidates

    # ── S6: 合并去重 + RRF 融合 ──────────────────────────────────

    @staticmethod
    def _merge_and_fuse(
        vector_candidates: list[dict[str, Any]],
        keyword_candidates: list[dict[str, Any]],
        mode: str,
    ) -> list[dict[str, Any]]:
        """doc_id 去重 + 通道信息合并 + RRF 融合评分"""
        merged: dict[str, dict[str, Any]] = {}

        for rank, c in enumerate(vector_candidates, 1):
            key = c["chunk_id"]
            c["vector_rank"] = rank
            merged[key] = c

        for rank, c in enumerate(keyword_candidates, 1):
            key = c["chunk_id"]
            c["keyword_rank"] = rank
            if key in merged:
                merged[key]["channels"] = ["keyword", "vector"]
                merged[key]["keyword_score"] = c["keyword_score"]
                merged[key]["keyword_rank"] = rank
                if merged[key]["vector_score"] is None:
                    merged[key]["vector_score"] = c.get("vector_score")
            else:
                c["vector_rank"] = None
                merged[key] = c

        k = settings.RAG_RRF_K
        for c in merged.values():
            rrf = 0.0
            if c.get("vector_rank"):
                rrf += 1.0 / (k + c["vector_rank"])
            if c.get("keyword_rank"):
                rrf += 1.0 / (k + c["keyword_rank"])
            if mode == "semantic" and c.get("vector_rank"):
                rrf = c.get("vector_score", rrf)
            elif mode == "keyword" and c.get("keyword_rank"):
                rrf = c.get("keyword_score", rrf)
            c["fusion_score"] = rrf

        sorted_candidates = sorted(
            merged.values(), key=lambda x: x["fusion_score"], reverse=True
        )
        return sorted_candidates
