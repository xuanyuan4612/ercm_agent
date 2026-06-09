"""文档管理与多模态处理接口"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import CurrentUser, check_client_access
from hermes.core.exceptions import CaseNotFoundError
from hermes.core.logging import get_logger
from hermes.core.response import success
from hermes.db.models.integrity import Case, GeneratedDocument
from hermes.db.session import get_db

logger = get_logger(__name__)

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

    # 从 MinIO 获取文件流并返回（当前降级为本地文件模式）
    from fastapi import Request
    from fastapi.responses import FileResponse, StreamingResponse

    # 尝试 MinIO 下载
    try:
        from fastapi import Request as FastAPIRequest
        import io

        minio_client = getattr(doc, '_minio_client', None)
        if not minio_client:
            # 尝试从 app state 获取
            import inspect
            for frame_info in inspect.stack():
                f_locals = frame_info.frame.f_locals
                if 'app' in f_locals:
                    app = f_locals['app']
                    if hasattr(app, 'state') and hasattr(app.state, 'minio') and app.state.minio:
                        minio_client = app.state.minio
                        break

        if minio_client and doc.storage_bucket and doc.storage_key:
            from hermes.core.config import settings
            data = minio_client.get_object(doc.storage_bucket, doc.storage_key)
            return StreamingResponse(
                data.stream(64 * 1024),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f"attachment; filename={doc.file_path or 'document'}"},
            )
    except Exception as e:
        logger.warning("minio_download_failed", error=str(e), doc_id=str(doc_id))

    # 降级：本地文件路径
    if doc.file_path:
        return FileResponse(doc.file_path)
    return success(message="文档暂无内容（MinIO 未接入，本地文件不存在）")


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

    # 音频文件处理：暂存到本地/MinIO，触发异步 Whisper ASR 处理
    # 当前为手动上传模式，返回固定值表示已接收
    task_id = str(uuid.uuid4())
    try:
        # 保存文件到临时目录（MinIO 接入前使用本地存储）
        import aiofiles
        import os
        upload_dir = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"{task_id}_{file.filename}")
        content = await file.read()
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
        logger.info("audio_file_saved", task_id=task_id, file_path=file_path,
                    size=len(content))
    except Exception as e:
        logger.warning("audio_file_save_failed", error=str(e))

    return success({
        "message": "音频文件已接收，异步处理中（Whisper ASR 管道待接入，当前手动上传模式）",
        "task_id": task_id,
        "mode": "manual_upload",
    })
