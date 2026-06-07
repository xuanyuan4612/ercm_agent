"""
廉洁监察模块数据模型

cases - 案件主表
case_stages - 案件阶段流转记录
human_approvals - 碳基守门记录
generated_documents - 生成文档
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hermes.db.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin
from hermes.db.session import Base


class Case(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """案件主表（双轨来源：系统抓取 + 人工录入）"""

    __tablename__ = "cases"

    task_id: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    case_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fraud_source: Mapped[str] = mapped_column(String(30), nullable=False)
    client: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # ecovacs / tineco / group

    # 敏感字段 (AES-256-GCM 加密)
    reported_staff_encrypted: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    reported_suppliers_encrypted: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    reported_dealers_encrypted: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    fraud_tel_encrypted: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    fraud_email_encrypted: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)

    fraud_detail: Mapped[str | None] = mapped_column(Text, nullable=True, name="fraud_event_detail")
    proof: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risk_control_case_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    current_stage: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    workflow_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    langgraph_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 关联
    stages: Mapped[list["CaseStage"]] = relationship(back_populates="case", order_by="CaseStage.stage_order")
    approvals: Mapped[list["HumanApproval"]] = relationship(back_populates="case")
    documents: Mapped[list["GeneratedDocument"]] = relationship(back_populates="case")


class CaseStage(UUIDMixin, Base):
    """案件阶段流转记录"""

    __tablename__ = "case_stages"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_name: Mapped[str] = mapped_column(String(50), nullable=False)
    stage_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ai_input: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    knowledge_refs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    retry_count: Mapped[int] = mapped_column(SmallInteger, default=0)

    case: Mapped["Case"] = relationship(back_populates="stages")


class HumanApproval(UUIDMixin, Base):
    """碳基守门记录（不可篡改，审计追溯）"""

    __tablename__ = "human_approvals"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_name: Mapped[str] = mapped_column(String(50), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # approved / rejected / modified
    original_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    modified_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    modifications_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped["Case"] = relationship(back_populates="approvals")


class GeneratedDocument(UUIDMixin, Base):
    """生成文档（MinIO 对象存储）"""

    __tablename__ = "generated_documents"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    stage_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    storage_bucket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped["Case"] = relationship(back_populates="documents")
