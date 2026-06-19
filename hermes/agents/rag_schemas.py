"""
RAG 统一请求/响应数据契约

基于 doc/agents/10-rag-shared-agent.md §三 定义。
所有 RAG 调用方均使用此契约，确保检索结果可校验、可审计、可追溯。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TenantScope(BaseModel):
    """租户权限上下文（必填）"""
    client: str = Field(..., description="租户: group / ecovacs / tineco")
    org_ids: list[str] = Field(default_factory=list, description="组织 ID 列表")
    role: str = Field(..., description="角色: risk_manager / auditor / admin 等")
    security_levels: list[str] = Field(
        default_factory=lambda: ["public"],
        description="可访问密级: public / internal / confidential / secret",
    )


class RAGRequest(BaseModel):
    """RAG 检索请求 — 必须携带业务上下文和权限上下文"""
    query: str = Field(..., min_length=1, description="检索问题")
    module: str = Field(..., description="调用模块: integrity_supervision 等")
    stage: str = Field(..., description="当前业务阶段")
    tenant_scope: TenantScope = Field(..., description="租户权限上下文")
    trace_id: str = Field(..., description="分布式链路追踪 ID")
    workflow_thread_id: str = Field(default="", description="工作流线程 ID")
    case_id: str = Field(default="", description="案件 ID")
    kb_types: list[str] | None = Field(default=None, description="知识库类型，None=从 Profile 获取")
    knowledge_scope: list[str] | None = Field(default=None, description="Profile 下发的知识域")
    top_k: int = Field(default=5, ge=1, le=20, description="返回结果数")
    mode: Literal["hybrid", "semantic", "keyword"] = Field(default="hybrid", description="检索模式")
    evidence_refs: list[str] = Field(default_factory=list, description="证据引用")
    schema_version: str = Field(default="1.0", description="契约版本")


class RetrievalDetail(BaseModel):
    """单条结果的检索溯源信息"""
    channels: list[str] = Field(default_factory=list, description="命中通道: keyword / vector")
    keyword_score: float | None = Field(default=None, description="全文检索分数")
    vector_score: float | None = Field(default=None, description="向量语义分数")
    fusion_score: float | None = Field(default=None, description="RRF 融合分数")
    rerank_score: float | None = Field(default=None, description="Reranker 精排分数")


class DocMetadata(BaseModel):
    """文档元数据"""
    source: str | None = None
    version: str | None = None
    effective_at: str | None = None
    expired_at: str | None = None
    security_level: str | None = None
    client: str | None = None
    org_id: str | None = None
    approval_status: str | None = None
    chunk_index: int | None = None
    total_chunks: int | None = None


class RAGResult(BaseModel):
    """单条检索结果"""
    doc_id: str = Field(..., description="文档 UUID")
    chunk_id: str = Field(..., description="chunk 标识: doc-uuid:chunk_index")
    kb_type: str = Field(..., description="知识库类型")
    title: str = Field(..., description="文档标题")
    content_snippet: str = Field(..., description="内容片段，≤300 字符")
    relevance: float = Field(..., ge=0.0, le=1.0, description="综合相关度分数")
    source_path: str | None = Field(default=None, description="原始文件路径")
    metadata: DocMetadata = Field(default_factory=DocMetadata)
    retrieval: RetrievalDetail = Field(default_factory=RetrievalDetail)


class RAGDiagnostics(BaseModel):
    """检索诊断信息"""
    recall_mode: str = Field(default="hybrid", description="实际召回模式")
    query_count: int = Field(default=1, description="子查询数量")
    search_latency_ms: int = Field(default=0, description="全文召回耗时")
    vector_latency_ms: int = Field(default=0, description="向量召回耗时")
    rerank_latency_ms: int = Field(default=0, description="精排耗时")
    total_latency_ms: int = Field(default=0, description="RAG 总耗时")
    degraded: bool = Field(default=False, description="是否降级")
    degrade_reasons: list[str] = Field(default_factory=list, description="降级原因")
    embedding_unavailable: bool = Field(default=False)
    reranker_unavailable: bool = Field(default=False)
    knowledge_insufficient: bool = Field(default=False, description="知识不足")
    blocked_candidates: int = Field(default=0, description="权限拦截候选数")
    prompt_injection_suspected: bool = Field(default=False)
    suggested_actions: list[str] = Field(default_factory=list, description="建议行动")


class RAGResponse(BaseModel):
    """RAG 检索响应 — 同时服务机器校验、Prompt 注入和审计追溯"""
    results: list[RAGResult] = Field(default_factory=list)
    context: str = Field(default="", description="给 LLM 注入的压缩上下文文本")
    knowledge_refs: list[str] = Field(default_factory=list, description="与 results 对应的引用 ID 列表")
    diagnostics: RAGDiagnostics = Field(default_factory=RAGDiagnostics)
