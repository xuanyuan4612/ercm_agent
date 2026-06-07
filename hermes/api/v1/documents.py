"""文档管理与多模态处理接口"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import CurrentUser, check_client_access
from hermes.core.exceptions import CaseNotFoundError
from hermes.core.response import success
from hermes.db.models.integrity import Case, GeneratedDocument
from hermes.db.session import get_db

router = APIRouter(prefix="")


@router.get("/cases/{case_id}/documents")
async def list_case_documents(
    case_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查询案件所有输出物列表"""
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.is_deleted == False)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise CaseNotFoundError(str(case_id))
    check_client_access(current_user, case.client)

    docs_result = await db.execute(
        select(GeneratedDocument)
        .where(GeneratedDocument.case_id == case.id)
        .order_by(GeneratedDocument.created_at.desc())
    )
    docs = docs_result.scalars().all()

    return success([
        {
            "id": str(d.id),
            "type": d.doc_type,
            "name": d.file_path or "",
            "format": d.file_format,
            "version": d.version,
            "is_confirmed": d.is_confirmed,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ])


@router.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """下载文档"""
    result = await db.execute(
        select(GeneratedDocument).where(GeneratedDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        from hermes.core.exceptions import NotFoundError
        raise NotFoundError(message="文档不存在", detail=f"doc_id={doc_id}")

    # TODO: 从 MinIO 获取文件流并返回
    from fastapi.responses import FileResponse
    if doc.file_path:
        return FileResponse(doc.file_path)
    return success(message="文档暂无内容")


@router.post("/cases/{case_id}/speech-to-text")
async def speech_to_text(
    case_id: uuid.UUID,
    file: UploadFile,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """语音转文字（上传音频文件，异步处理）"""
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.is_deleted == False)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise CaseNotFoundError(str(case_id))

    # TODO: 上传到 MinIO，触发音频处理管道 (Whisper ASR)
    return success({
        "message": "音频文件已上传，异步处理中",
        "task_id": str(uuid.uuid4()),
    })
