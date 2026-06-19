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
from typing import Any, Literal

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
        orch = RAGOrchestrator(db_session, es_client=app.state.es)
        response = await orch.retrieve(request)
    """

    def __init__(
        self,
        db: AsyncSession,
        es_client: Any | None = None,
    ) -> None:
        self.db = db
        # SearchAdapter 延迟初始化
        self._search_adapter: Any = None
        self._es_client = es_client

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

        # S4: Embedding 向量化（并行请求，降低串行等待放大延迟）
        t_emb_start = time.monotonic()
        embedding_tasks = [self._get_embedding(q) for q in queries]
        embedding_results = await asyncio.gather(*embedding_tasks)
        query_embeddings = [v for v in embedding_results if v is not None]
        embedding_available = len(query_embeddings) > 0
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
        filtered, blocked = self._hard_filter(merged, metadata_filter, request)
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
        mode: Literal["hybrid", "semantic", "keyword"] = "hybrid",
    ) -> list[dict[str, Any]]:
        """简化搜索（内部兼容旧调用方），返回旧 dict 格式。

        注意：此方法仅供 Agent 内部调用，使用系统级全权限 scope。
        外部 API 必须使用 retrieve() 并传入用户 tenant_scope。
        """
        if kb_types is None:
            kb_types = list(KB_TYPE_MAP.keys())

        request = RAGRequest(
            query=query,
            module="common",
            stage="search",
            tenant_scope={
                "client": "group", "org_ids": ["*"], "role": "admin",
                "security_levels": ["public", "internal", "confidential", "secret"],
            },
            trace_id="search-api",
            kb_types=kb_types,
            top_k=top_k,
            mode=mode,
        )
        response = await self.retrieve(request)
        return [
            {
                "doc_id": r.doc_id,
                "kb_type": r.kb_type,
                "title": r.title,
                "content_snippet": r.content_snippet,
                "relevance": r.relevance,
                "updated_at": "",  # 旧兼容字段，父级模型无此字段
            }
            for r in response.results
        ]

    def get_retrieval_context(
        self,
        query: str,
        kb_types: list[str],
        top_k: int = 5,
    ) -> str:
        """获取格式化后的检索上下文

        注意：此方法为同步包装，内部使用 asyncio.run()。
        如果在已有事件循环的上下文中调用（如 FastAPI handler），
        将引发 RuntimeError。推荐在异步上下文中直接使用 _get_context_async()。
        在同步上下文中（如脚本/CLI/测试），可安全调用。
        """
        import asyncio as _asyncio
        try:
            # 尝试直接运行（同步上下文）
            return _asyncio.run(self._get_context_async(query, kb_types, top_k))
        except RuntimeError as err:
            # 已有运行中的事件循环（异步上下文），抛出明确提示
            raise RuntimeError(
                "get_retrieval_context() 不能在异步上下文中调用。"
                "请使用 await orch._get_context_async(query, kb_types, top_k)"
            ) from err

    async def _get_context_async(
        self, query: str, kb_types: list[str], top_k: int
    ) -> str:
        request = RAGRequest(
            query=query,
            module="common",
            stage="context",
            tenant_scope={
                "client": "group", "org_ids": ["*"], "role": "admin",
                "security_levels": ["public", "internal", "confidential", "secret"],
            },
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

            async with httpx.AsyncClient(timeout=5.0) as client:
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
            # 注意：asyncpg 不支持 ::vector 语法，必须用 CAST(:param AS vector)
            embedding_str = f"[{','.join(str(x) for x in emb)}]"

            try:
                query_sql = text("""
                    SELECT id, kb_type, title,
                           substring(content, 1, 300) AS content_snippet,
                           1.0 - (embedding <=> CAST(:emb AS vector)) AS vector_score,
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
                    ORDER BY embedding <=> CAST(:emb AS vector)
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
                    chunk_id_val = f"{doc_id}:{row[6] or 1}"
                    if chunk_id_val in seen:
                        continue
                    seen.add(chunk_id_val)
                    candidates.append({
                        "doc_id": doc_id,
                        "chunk_id": chunk_id_val,
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

    def _get_search_adapter(self) -> Any:
        """获取 SearchAdapter（延迟初始化）"""
        if self._search_adapter is None:
            from hermes.integrations.search_adapter import SearchAdapter
            self._search_adapter = SearchAdapter(self._es_client)
        return self._search_adapter

    async def _keyword_recall(
        self,
        queries: list[str],
        metadata_filter: dict,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """全文召回：优先 Elasticsearch BM25，降级为 ILIKE"""
        adapter = self._get_search_adapter()
        recall_n = top_k * settings.RAG_RECALL_MULTIPLIER

        # ── 优先：Elasticsearch 全文检索 ──
        if adapter.available:
            try:
                all_results: list[dict[str, Any]] = []
                seen: set[str] = set()
                for q in queries[:3]:
                    es_results = await adapter.search(
                        query=q,
                        kb_types=metadata_filter["kb_types"],
                        top_k=recall_n,
                        client_filters=metadata_filter.get("client"),
                        security_levels=metadata_filter.get("security_levels"),
                    )
                    for r in es_results:
                        if r["chunk_id"] not in seen:
                            seen.add(r["chunk_id"])
                            r["vector_score"] = None
                            all_results.append(r)
                if all_results:
                    logger.info("es_keyword_recall_hits", count=len(all_results))
                    return all_results
            except Exception as e:
                logger.warning("es_keyword_recall_failed_fallback_ilike", error=str(e))

        # ── 降级：ILIKE 全文搜索 ──
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        for q in queries[:3]:
            try:
                pattern = f"%{q}%"

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
                    chunk_id_val = f"{doc_id}:{row[5] or 1}"
                    if chunk_id_val in seen:
                        continue
                    seen.add(chunk_id_val)

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

        # 归一化 fusion_score 到 0-1 区间（RRF 原始值极小，直接使用会低于阈值）
        if merged:
            scores = [c["fusion_score"] for c in merged.values()]
            max_score = max(scores) if scores else 1.0
            min_score = min(scores) if scores else 0.0
            score_range = max_score - min_score
            if score_range > 0:
                for c in merged.values():
                    c["fusion_score"] = (c["fusion_score"] - min_score) / score_range
            else:
                # 所有分数相同时（单结果或完全等价），给一个能通过阈值的高分
                for c in merged.values():
                    c["fusion_score"] = 0.75

        sorted_candidates = sorted(
            merged.values(), key=lambda x: x["fusion_score"], reverse=True
        )
        return sorted_candidates

    # ── S7: 二次硬过滤 ───────────────────────────────────────────

    @staticmethod
    def _hard_filter(
        candidates: list[dict[str, Any]],
        metadata_filter: dict,
        request: RAGRequest,
    ) -> tuple[list[dict[str, Any]], int]:
        """内存级权限/密级/状态二次过滤，防止索引延迟导致越权"""
        blocked = 0
        filtered: list[dict[str, Any]] = []

        allowed_clients = set(metadata_filter.get("client", []))
        allowed_orgs = set(metadata_filter.get("org_ids", []))
        allowed_levels = set(metadata_filter.get("security_levels", []))

        for c in candidates:
            if c.get("client") not in allowed_clients:
                blocked += 1
                continue
            if c.get("org_id") not in allowed_orgs:
                blocked += 1
                continue
            if c.get("security_level") not in allowed_levels:
                blocked += 1
                continue
            if c.get("approval_status") != "approved":
                blocked += 1
                continue
            if request.kb_types and c.get("kb_type") not in request.kb_types:
                blocked += 1
                continue
            filtered.append(c)

        if blocked > 0:
            logger.info("rag_blocked_candidates", count=blocked, total=len(candidates))

        return filtered, blocked

    # ── S8: Rerank 精排 ──────────────────────────────────────────

    async def _rerank(
        self, candidates: list[dict[str, Any]], query: str
    ) -> tuple[list[dict[str, Any]], bool]:
        """领域 Reranker 精排。

        当前实现：使用融合分数排序（降级方案）。
        预留 RerankerAdapter 接口，可接入 Cohere/Jina/自建 Reranker。
        """
        if not candidates:
            return candidates, True

        # TODO: 接入 Reranker API 后替换此段
        # reranker = get_reranker_adapter()
        # pairs = [(query, c["content_snippet"]) for c in candidates]
        # scores = await reranker.rerank(query, pairs)
        # for c, s in zip(candidates, scores):
        #     c["rerank_score"] = s
        #     c["relevance"] = 0.6 * c["fusion_score"] + 0.4 * s

        # 当前：fusion_score 作为最终 relevance（降级模式）
        for c in candidates:
            c["rerank_score"] = None
            c["relevance"] = c.get("fusion_score", 0.0)

        candidates.sort(key=lambda x: x["relevance"], reverse=True)

        # 降级模式下不硬过滤，fusion_score 已归一化到 0-1
        # 真正的阈值过滤留待 Reranker 接入后启用
        return candidates, False  # reranker_ok=False（降级模式）

    # ── S9: 引用校验 ────────────────────────────────────────────

    @staticmethod
    def _verify_citations(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """校验每条候选的引用完整性"""
        verified: list[dict[str, Any]] = []
        for c in candidates:
            if not c.get("doc_id") or not c.get("chunk_id"):
                continue
            if not c.get("source_path") and not c.get("title"):
                continue
            if not c.get("content_snippet"):
                continue
            verified.append(c)
        return verified

    # ── S10: 上下文组装 ──────────────────────────────────────────

    @staticmethod
    def _assemble_context(results: list[dict[str, Any]]) -> str:
        """将检索结果压缩为 LLM 可注入的上下文文本"""
        if not results:
            return "（未找到相关知识库内容）"

        lines = ["【相关知识库内容】"]
        for i, r in enumerate(results[:5], 1):
            lines.append(f"\n--- 参考 {i} ---")
            lines.append(f"引用ID: {r.get('chunk_id', 'N/A')}")
            lines.append(f"类型: {r.get('kb_type', 'N/A')}")
            lines.append(f"标题: {r.get('title', 'N/A')}")
            lines.append(f"来源: {r.get('source_path', 'N/A')}")
            lines.append(f"相关度: {r.get('relevance', 0):.2f}")
            lines.append(f"内容: {r.get('content_snippet', '')}")
        return "\n".join(lines)

    # ── S11: 质量诊断 ────────────────────────────────────────────

    @staticmethod
    def _finalize_diagnostics(
        diag: RAGDiagnostics,
        results: list[dict[str, Any]],
        top_k: int,
    ) -> None:
        """根据最终结果完善诊断信息"""
        if not results:
            diag.knowledge_insufficient = True
            diag.degraded = True
            diag.degrade_reasons.append("no_results")
            diag.suggested_actions = [
                "补充知识库文档",
                "扩大授权范围需人工审批",
                "改用更具体的问题重新检索",
            ]
        # 降级模式下不检查最低阈值，fusion_score 已归一化排序
        # 只在 Reranker 启用时才用 RAG_MIN_RELEVANCE_THRESHOLD 过滤

    # ── 辅助：转为 RAGResult ─────────────────────────────────────

    @staticmethod
    def _to_rag_result(r: dict[str, Any]) -> RAGResult:
        return RAGResult(
            doc_id=r.get("doc_id", ""),
            chunk_id=r.get("chunk_id", ""),
            kb_type=r.get("kb_type", ""),
            title=r.get("title", ""),
            content_snippet=r.get("content_snippet", ""),
            relevance=r.get("relevance", 0.0),
            source_path=r.get("source_path"),
            metadata=DocMetadata(
                source=r.get("metadata_", {}).get("source"),
                version=r.get("metadata_", {}).get("version"),
                effective_at=r.get("metadata_", {}).get("effective_at"),
                expired_at=r.get("metadata_", {}).get("expired_at"),
                security_level=r.get("security_level"),
                client=r.get("client"),
                org_id=r.get("org_id"),
                approval_status=r.get("approval_status"),
                chunk_index=r.get("chunk_index"),
                total_chunks=r.get("total_chunks"),
            ),
            retrieval=RetrievalDetail(
                channels=r.get("channels", []),
                keyword_score=r.get("keyword_score"),
                vector_score=r.get("vector_score"),
                fusion_score=r.get("fusion_score"),
                rerank_score=r.get("rerank_score"),
            ),
        )
