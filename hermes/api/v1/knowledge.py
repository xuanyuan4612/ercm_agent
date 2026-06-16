"""知识库管理接口"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import CurrentUser, GroupRoleRequired
from hermes.core.exceptions import KnowledgeBaseNotFoundError, NotFoundError
from hermes.core.logging import get_logger
from hermes.core.response import paginated, success
from hermes.db.models.knowledge import KnowledgeDocument
from hermes.db.session import get_db

logger = get_logger(__name__)

router = APIRouter(prefix="/knowledge-bases")

VALID_KB_TYPES = frozenset({
    "intake", "investigation", "analysis", "disposition", "enforcement",
    "risk_monitor", "ic_evaluation", "special_audit", "exit_audit",
    "trade_secret", "improvement", "behavior_risk", "common",
})


@router.get("")
async def list_knowledge_bases(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查询所有知识库及其文档统计"""
    # 按 kb_type 聚合计数
    result = await db.execute(
        select(
            KnowledgeDocument.kb_type,
            func.count(KnowledgeDocument.id).label("doc_count"),
        )
        .where(KnowledgeDocument.is_active)
        .group_by(KnowledgeDocument.kb_type)
    )
    rows = result.all()

    type_names = {
        "intake": "初筛知识库",
        "investigation": "调查方案知识库",
        "analysis": "分析报告知识库",
        "disposition": "处置分流知识库",
        "enforcement": "处罚执行知识库",
        "risk_monitor": "风险监控知识库",
        "ic_evaluation": "内控评价知识库",
        "special_audit": "专项审计知识库",
        "exit_audit": "离任审计知识库",
        "trade_secret": "商业秘密知识库",
        "improvement": "持续改善知识库",
        "behavior_risk": "行为风险知识库",
        "common": "公共知识库",
    }

    kb_list = []
    for kb_type, count in rows:
        kb_list.append({
            "type": kb_type,
            "name": type_names.get(kb_type, kb_type),
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
):
    """查询知识库文档列表"""
    if kb_type not in VALID_KB_TYPES:
        raise KnowledgeBaseNotFoundError(kb_type)

    query = select(KnowledgeDocument).where(
        KnowledgeDocument.kb_type == kb_type,
    )
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
            "is_active": d.is_active,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        } for d in docs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/{kb_type}/documents/{doc_id}")
async def delete_document(
    kb_type: str,
    doc_id: uuid.UUID,
    current_user: GroupRoleRequired,
    db: AsyncSession = Depends(get_db),
):
    """删除知识库文档（逻辑删除）"""
    if kb_type not in VALID_KB_TYPES:
        raise KnowledgeBaseNotFoundError(kb_type)

    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError(message="文档不存在")

    doc.is_active = False
    await db.flush()
    return success(message=f"文档 {doc.title} 已删除")


@router.get("/search")
async def search_knowledge(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    query: str = Query(..., description="搜索关键词"),
    kb_types: str | None = Query(None, description="限定知识库类型，逗号分隔"),
    top_k: int = Query(5, ge=1, le=20),
):
    """知识库混合搜索（全文 + 语义）"""
    allowed = set(kb_types.split(",")) if kb_types else VALID_KB_TYPES
    allowed = {t for t in allowed if t in VALID_KB_TYPES}

    if not allowed:
        return success([])

    # 使用 RAG Engine 进行混合检索（向量语义 + 全文）
    # pgvector + Elasticsearch 混合检索在生产环境自动启用
    try:
        from hermes.agents.rag_engine import RAGEngine
        rag = RAGEngine(db)
        results = await rag.search(query, list(allowed), top_k, mode="hybrid")
        return success(results)
    except Exception as e:
        logger.warning("rag_search_failed", error=str(e),
                       message="RAG Engine 不可用，降级为 ILIKE 全文搜索")

    # 降级搜索：ILIKE 全文匹配 + 相关度评分
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
            "content_snippet": d.content[:300] if d.content else "",
            "relevance": 0.6 + (0.2 if query.lower() in (d.title or "").lower() else 0)
                        + (0.15 if query.lower() in (d.content or "").lower()[:100] else 0),
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }
        for d in docs
    ])
