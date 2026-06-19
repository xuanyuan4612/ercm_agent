"""知识库管理接口 — 检索 + 上传 + 管理"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.agents.rag_engine import KB_TYPE_MAP, RAGOrchestrator
from hermes.agents.rag_schemas import RAGRequest, TenantScope
from hermes.api.dependencies import CurrentUser, GroupRoleRequired
from hermes.core.exceptions import (
    KnowledgeBaseNotFoundError,
    NotFoundError,
    UnsupportedFileFormatError,
)
from hermes.core.logging import get_logger
from hermes.core.response import paginated, success
from hermes.db.models.knowledge import KnowledgeDocument
from hermes.db.session import get_db
from hermes.services.knowledge_ingestion import SUPPORTED_FORMATS, KnowledgeIngestionService

logger = get_logger(__name__)

router = APIRouter(prefix="/knowledge-bases")

VALID_KB_TYPES = frozenset(KB_TYPE_MAP.keys())

TYPE_NAMES: dict[str, str] = {
    # ── 廉洁监察 ──
    "intake": "初筛知识库",
    "investigation": "调查方案知识库",
    "analysis": "分析报告知识库",
    "disposition": "处置分流知识库",
    "enforcement": "处罚执行知识库",
    # ── 风险监控 ──
    "risk_rules": "风险规则知识库",
    "risk_cases": "风险案例知识库",
    "database_schema": "数据库 Schema 知识库",
    "disposition_feedback": "处置反馈知识库",
    "risk_monitor": "风险监控知识库",
    # ── 内控评价 ──
    "ic_policy": "内控制度知识库",
    "control_matrix": "控制矩阵知识库",
    "audit_plan": "审计计划知识库",
    "interview_template": "访谈模板知识库",
    "deficiency_rating": "缺陷评级知识库",
    "ic_evaluation": "内控评价知识库",
    # ── 专项审计 ──
    "sa_plan": "专项审计计划知识库",
    "sa_history": "专项审计历史知识库",
    "audit_workpaper_template": "审计底稿模板知识库",
    "improvement_suggestion": "改善建议知识库",
    "special_audit": "专项审计知识库",
    # ── 离任审计 ──
    "ea_plan": "离任审计计划知识库",
    "position_duty": "岗位职责知识库",
    "personal_risk_case": "个人风险案例知识库",
    "business_audit_case": "业务审计案例知识库",
    "behavioral_risk_history": "行为风险历史知识库",
    "exit_audit": "离任审计知识库",
    # ── 商业秘密 ──
    "trade_secret_policy": "商业秘密制度知识库",
    "ip_policy": "知识产权制度知识库",
    "trade_secret_law": "商业秘密法律知识库",
    "trade_secret_cases": "商业秘密案例知识库",
    "historical_secret_review": "历史定密评审知识库",
    "trade_secret": "商业秘密知识库",
    # ── 行为风险 ──
    "behavior_policy": "行为规范制度知识库",
    "employee_lifecycle": "员工生命周期知识库",
    "historical_behavior_analysis": "历史行为分析知识库",
    "behavior_risk": "行为风险知识库",
    # ── 持续改善 ──
    "improvement_case": "改善案例知识库",
    "rectification_template": "整改模板知识库",
    "audit_issue_history": "审计问题历史知识库",
    "policy_and_process": "制度与流程知识库",
    "improvement": "持续改善知识库",
    # ── 共享 ──
    "common": "公共知识库",
    "law_and_regulation": "法律法规知识库",
    "kb_integrity_policy": "廉洁制度知识库",
    "kb_integrity_cases": "廉洁案例知识库",
}


# ═══════════════════════════════════════════════════════════════
# 基础设施依赖
# ═══════════════════════════════════════════════════════════════

def _get_es_client(request: Request) -> Any:
    """从 app.state 获取 Elasticsearch 客户端（可能为 None）"""
    return getattr(request.app.state, "es", None)


def _get_minio_client(request: Request) -> Any:
    """从 app.state 获取 MinIO 客户端（可能为 None）"""
    return getattr(request.app.state, "minio", None)


# ═══════════════════════════════════════════════════════════════
# 检索端点
# ═══════════════════════════════════════════════════════════════

@router.post("/retrieve")
async def retrieve_knowledge(
    request: RAGRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    es_client: Any = Depends(_get_es_client),
) -> dict[str, Any]:
    """完整 RAG 检索（13 步流水线）

    返回标准 RAGResponse，包含 results、context、knowledge_refs、diagnostics。
    """
    # 从当前用户注入 tenant_scope（如果请求未提供完整）
    ts = request.tenant_scope
    if not ts.client:
        ts.client = getattr(current_user, "client", "group")
    if not ts.org_ids:
        ts.org_ids = [getattr(current_user, "org_id", "*")]
    if not ts.role:
        ts.role = getattr(current_user, "role", "viewer")

    orch = RAGOrchestrator(db, es_client=es_client)
    try:
        response = await orch.retrieve(request)
    except ValueError as e:
        return success({
            "results": [],
            "context": "（检索请求无效）",
            "knowledge_refs": [],
            "diagnostics": {
                "recall_mode": request.mode,
                "knowledge_insufficient": True,
                "degrade_reasons": [str(e)],
                "total_latency_ms": 0,
            },
        })

    return success(response.model_dump())


@router.get("/search")
async def search_knowledge(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    es_client: Any = Depends(_get_es_client),
    query: str = Query(..., description="搜索关键词"),
    kb_types: str | None = Query(None, description="限定知识库类型，逗号分隔"),
    top_k: int = Query(5, ge=1, le=20),
) -> dict[str, Any]:
    """知识库混合搜索（简化接口，向后兼容）"""
    allowed = set(kb_types.split(",")) if kb_types else VALID_KB_TYPES
    allowed = {t for t in allowed if t in VALID_KB_TYPES}
    if not allowed:
        return success([])

    # 从当前用户构建权限上下文
    user_client = getattr(current_user, "client", "group")
    user_org = getattr(current_user, "org_id", "*")
    user_role = getattr(current_user, "role", "viewer")

    try:
        orch = RAGOrchestrator(db, es_client=es_client)
        # 使用 retrieve() 替代 search() 以确保权限过滤生效
        request = RAGRequest(
            query=query,
            module="common",
            stage="search",
            tenant_scope=TenantScope(
                client=user_client,
                org_ids=[user_org],
                role=user_role,
                security_levels=["public", "internal"],
            ),
            trace_id="search-api",
            kb_types=list(allowed),
            top_k=top_k,
        )
        response = await orch.retrieve(request)
        return success([
            {
                "doc_id": r.doc_id,
                "kb_type": r.kb_type,
                "title": r.title,
                "content_snippet": r.content_snippet,
                "relevance": r.relevance,
                "updated_at": r.metadata.effective_at,
            }
            for r in response.results
        ])
    except Exception as e:
        logger.warning("rag_search_failed", error=str(e))

    # 降级搜索：直接 ILIKE
    search_sql = (
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.kb_type.in_(allowed),
            KnowledgeDocument.is_active,
            KnowledgeDocument.content.ilike(f"%{query}%"),
        )
        .order_by(KnowledgeDocument.updated_at.desc())
        .limit(top_k)
    )
    result = await db.execute(search_sql)
    docs = result.scalars().all()

    return success([
        {
            "doc_id": str(d.id),
            "kb_type": d.kb_type,
            "title": d.title,
            "content_snippet": (d.content or "")[:300],
            "relevance": 0.6 + (0.2 if query.lower() in (d.title or "").lower() else 0),
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }
        for d in docs
    ])


# ═══════════════════════════════════════════════════════════════
# 上传端点
# ═══════════════════════════════════════════════════════════════

@router.post("/{kb_type}/upload")
async def upload_document(
    kb_type: str,
    current_user: GroupRoleRequired,
    file: UploadFile = File(...),
    client: str = Query("group", description="租户"),
    org_id: str = Query("*", description="组织 ID"),
    security_level: str = Query("internal", description="密级: public/internal/confidential/secret"),
    db: AsyncSession = Depends(get_db),
    minio_client: Any = Depends(_get_minio_client),
    es_client: Any = Depends(_get_es_client),
) -> dict[str, Any]:
    """上传知识库文档

    支持格式: txt, md, json, docx, pdf
    文件自动解析、分块、向量化并写入 PG + ES，原始文件存储到 MinIO。
    """
    if kb_type not in VALID_KB_TYPES:
        raise KnowledgeBaseNotFoundError(kb_type)

    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
    if ext not in SUPPORTED_FORMATS:
        raise UnsupportedFileFormatError(ext)

    content = await file.read()
    if not content:
        return success({"success": False, "error": "文件内容为空"})

    service = KnowledgeIngestionService(db, minio_client=minio_client, es_client=es_client)
    result = await service.ingest_file(
        file_content=content,
        filename=file.filename or "unknown",
        kb_type=kb_type,
        client=client,
        org_id=org_id,
        security_level=security_level,
    )
    await db.commit()

    return success(result.to_dict())


@router.post("/{kb_type}/upload-text")
async def upload_text_knowledge(
    kb_type: str,
    body: dict[str, Any],
    current_user: GroupRoleRequired,
    db: AsyncSession = Depends(get_db),
    es_client: Any = Depends(_get_es_client),
) -> dict[str, Any]:
    """上传纯文本知识条目

    Body:
        {"title": "条目标题", "content": "条目内容", "client": "group", "security_level": "internal"}
    """
    if kb_type not in VALID_KB_TYPES:
        raise KnowledgeBaseNotFoundError(kb_type)

    title = body.get("title", "").strip()
    content = body.get("content", "").strip()
    if not title or not content:
        return success({"success": False, "error": "title 和 content 不能为空"})

    service = KnowledgeIngestionService(db, es_client=es_client)
    result = await service.ingest_text(
        title=title,
        content=content,
        kb_type=kb_type,
        client=body.get("client", "group"),
        org_id=body.get("org_id", "*"),
        security_level=body.get("security_level", "internal"),
        metadata=body.get("metadata"),
    )
    await db.commit()

    return success(result.to_dict())


# ═══════════════════════════════════════════════════════════════
# 管理端点
# ═══════════════════════════════════════════════════════════════

@router.get("")
async def list_knowledge_bases(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """查询所有知识库及其文档统计"""
    result = await db.execute(
        select(
            KnowledgeDocument.kb_type,
            func.count(KnowledgeDocument.id).label("doc_count"),
        )
        .where(KnowledgeDocument.is_active)
        .group_by(KnowledgeDocument.kb_type)
    )
    rows = result.all()

    kb_list = []
    for kb_type, count in rows:
        kb_list.append({
            "type": kb_type,
            "name": TYPE_NAMES.get(kb_type, kb_type),
            "doc_count": count,
            "last_synced": None,
        })
    return success(kb_list)


@router.get("/{kb_type}/documents")
async def list_documents(
    kb_type: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    keyword: str | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """查询知识库文档列表"""
    if kb_type not in VALID_KB_TYPES:
        raise KnowledgeBaseNotFoundError(kb_type)

    query = select(KnowledgeDocument).where(KnowledgeDocument.kb_type == kb_type)
    if is_active is not None:
        query = query.where(KnowledgeDocument.is_active == is_active)
    else:
        query = query.where(KnowledgeDocument.is_active)
    if keyword:
        query = query.where(KnowledgeDocument.title.ilike(f"%{keyword}%"))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(KnowledgeDocument.updated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    docs = result.scalars().all()

    return paginated(
        items=[{
            "id": str(d.id),
            "kb_type": d.kb_type,
            "title": d.title,
            "chunk_index": d.chunk_index,
            "total_chunks": d.total_chunks,
            "security_level": d.security_level,
            "client": d.client,
            "is_active": d.is_active,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        } for d in docs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{kb_type}/documents/{doc_id}")
async def get_document_detail(
    kb_type: str,
    doc_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取文档详情（包含所有 chunk）"""
    if kb_type not in VALID_KB_TYPES:
        raise KnowledgeBaseNotFoundError(kb_type)

    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.kb_type == kb_type,
            KnowledgeDocument.id == doc_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError(message="文档不存在")

    # 查询同一文档的其他 chunks（优先 document_id，兼容旧数据按 title）
    if doc.document_id:
        chunks_query = select(KnowledgeDocument).where(
            KnowledgeDocument.document_id == doc.document_id,
            KnowledgeDocument.is_active == True,
        ).order_by(KnowledgeDocument.chunk_index)
    else:
        chunks_query = select(KnowledgeDocument).where(
            KnowledgeDocument.kb_type == kb_type,
            KnowledgeDocument.title == doc.title,
            KnowledgeDocument.is_active == True,
        ).order_by(KnowledgeDocument.chunk_index)
    chunks_result = await db.execute(chunks_query)
    all_chunks = chunks_result.scalars().all()

    return success({
        "id": str(doc.id),
        "kb_type": doc.kb_type,
        "title": doc.title,
        "chunks": [
            {
                "chunk_id": str(chunk.id),
                "chunk_index": chunk.chunk_index,
                "content_snippet": (chunk.content or "")[:500],
                "content_hash": chunk.content_hash,
            }
            for chunk in all_chunks
        ],
        "source_path": doc.source_path,
        "security_level": doc.security_level,
        "client": doc.client,
        "org_id": doc.org_id,
        "approval_status": doc.approval_status,
        "metadata": doc.metadata_,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    })


@router.delete("/{kb_type}/documents/{doc_id}")
async def delete_document(
    kb_type: str,
    doc_id: uuid.UUID,
    current_user: GroupRoleRequired,
    db: AsyncSession = Depends(get_db),
    es_client: Any = Depends(_get_es_client),
) -> dict[str, Any]:
    """删除知识库文档（逻辑删除所有 chunk + ES 同步）"""
    if kb_type not in VALID_KB_TYPES:
        raise KnowledgeBaseNotFoundError(kb_type)

    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError(message="文档不存在")

    # 按 document_id 或 title 查找所有关联 chunk
    delete_key = doc.document_id
    if delete_key:
        chunks_result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.document_id == delete_key,
                KnowledgeDocument.is_active == True,
            )
        )
    else:
        # 兼容旧数据：无 document_id 时按 title + kb_type 匹配
        chunks_result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.kb_type == kb_type,
                KnowledgeDocument.title == doc.title,
                KnowledgeDocument.is_active == True,
            )
        )

    chunks = chunks_result.scalars().all()
    deleted_count = 0
    for chunk in chunks:
        chunk.is_active = False
        deleted_count += 1
    await db.flush()

    # 从 ES 中删除
    from hermes.integrations.search_adapter import SearchAdapter
    es_adapter = SearchAdapter(es_client)
    if es_adapter.available:
        await es_adapter.delete_by_title(kb_type, doc.title)

    return success(message=f"文档 {doc.title} 已删除（{deleted_count} 个 chunk）")


# ═══════════════════════════════════════════════════════════════
# 文件下载
# ═══════════════════════════════════════════════════════════════

@router.get("/{kb_type}/documents/{doc_id}/download")
async def download_knowledge_document(
    kb_type: str,
    doc_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    minio_client: Any = Depends(_get_minio_client),
) -> Any:
    """下载知识库文档的原始文件（从 MinIO）"""
    if kb_type not in VALID_KB_TYPES:
        raise KnowledgeBaseNotFoundError(kb_type)

    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == doc_id,
            KnowledgeDocument.is_active == True,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError(message="文档不存在")

    # 尝试从 MinIO 下载
    minio_bucket = (doc.metadata_ or {}).get("minio_bucket", "")
    minio_key = (doc.metadata_ or {}).get("minio_key", "")
    if minio_client and minio_bucket and minio_key:
        try:
            obj = minio_client.get_object(minio_bucket, minio_key)
            filename = (doc.metadata_ or {}).get("original_filename", doc.title)
            return StreamingResponse(
                obj.stream(64 * 1024),
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
                },
            )
        except Exception as e:
            logger.warning("minio_knowledge_download_failed", doc_id=str(doc_id), error=str(e))

    # 降级：无 MinIO 或文件不存在
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=doc.content or "",
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{doc.title}.txt",
        },
    )


# ═══════════════════════════════════════════════════════════════
# 反馈端点（预留）
# ═══════════════════════════════════════════════════════════════

@router.post("/feedback")
async def submit_feedback(
    body: dict[str, Any],
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """检索反馈（预留接口）

    Body:
        {"trace_id": "...", "rag_call_id": "...", "accepted_refs": [...], "rejected_refs": [...]}
    """
    # TODO: 反馈写入 feedback 表，对接模型训练闭环
    return success(message="反馈已记录（full feedback loop 待后续实现）")
