"""知识库文档模型（pgvector 向量存储）"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hermes.db.models.base import UUIDMixin
from hermes.db.session import Base


class KnowledgeDocument(UUIDMixin, Base):
    __tablename__ = "knowledge_documents"

    kb_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(JSONB, name="metadata_", nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=1)
    total_chunks: Mapped[int] = mapped_column(Integer, default=1)
    # ── 新增字段 ──
    approval_status: Mapped[str] = mapped_column(
        String(20), default="approved", nullable=False, index=True,
        comment="审核状态: pending / approved / rejected"
    )
    effective_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="生效日期"
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="失效日期"
    )
    security_level: Mapped[str] = mapped_column(
        String(20), default="internal", nullable=False, index=True,
        comment="密级: public / internal / confidential / secret"
    )
    client: Mapped[str] = mapped_column(
        String(20), default="group", nullable=False, index=True,
        comment="租户: group / ecovacs / tineco"
    )
    org_id: Mapped[str] = mapped_column(
        String(50), default="*", nullable=False, index=True,
        comment="组织 ID，* 表示公共"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
