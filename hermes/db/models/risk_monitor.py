"""风险监控模块数据模型"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hermes.db.models.base import UUIDMixin
from hermes.db.session import Base


class RiskRule(UUIDMixin, Base):
    __tablename__ = "risk_rules"

    rule_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    business_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    personnel_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_cycle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    level1_scene: Mapped[str | None] = mapped_column(String(100), nullable=True)
    level2_scene: Mapped[str | None] = mapped_column(String(100), nullable=True)
    level3_scene: Mapped[str] = mapped_column(String(100), nullable=False)
    sql_statement: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)  # 高/中/低
    threshold: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    monitor_frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    monitor_business_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    use_external_data: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    reviewed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RiskAnalysisSubject(UUIDMixin, Base):
    __tablename__ = "risk_analysis_subjects"

    subject_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    subject_name: Mapped[str] = mapped_column(String(200), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(30), nullable=False)
    contact_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    merge_source_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risk_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_business: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    involved_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    analysis_report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RiskAlert(UUIDMixin, Base):
    __tablename__ = "risk_alerts"

    alert_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_rules.id"), nullable=False)
    analysis_subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("risk_analysis_subjects.id"), nullable=True
    )
    business_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    alert_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    alert_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risk_type: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)  # 高/中/低
    severity: Mapped[str | None] = mapped_column(String(10), nullable=True)
    widespread: Mapped[str | None] = mapped_column(String(10), nullable=True)
    impact_degree: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    handling_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskPushRecord(UUIDMixin, Base):
    __tablename__ = "risk_push_records"

    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_alerts.id"), nullable=False)
    target_module: Mapped[str] = mapped_column(String(30), nullable=False)
    target_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    push_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    push_status: Mapped[str] = mapped_column(String(20), default="pending")
    callback_status: Mapped[str] = mapped_column(String(20), default="pending")
    callback_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    push_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    callback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RuleIterationLog(UUIDMixin, Base):
    __tablename__ = "rule_iteration_log"

    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("risk_rules.id"), nullable=False)
    iteration_type: Mapped[str] = mapped_column(String(20), nullable=False)
    old_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_threshold: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    new_threshold: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    operator_id: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
