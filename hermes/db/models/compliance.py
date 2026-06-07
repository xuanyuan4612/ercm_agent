"""
合规与改善模块数据模型

包含：商业秘密、行为风险、持续改善
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hermes.db.models.base import UUIDMixin
from hermes.db.session import Base


# ═══════════════════════════════════════════════════════════════
# 商业秘密 (Trade Secret)
# ═══════════════════════════════════════════════════════════════

class TradeSecretItem(UUIDMixin, Base):
    __tablename__ = "trade_secret_items"

    item_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    secret_type: Mapped[str] = mapped_column(String(50), nullable=False)
    secret_level: Mapped[str] = mapped_column(String(20), nullable=False)
    business_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    project_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    file_list: Mapped[dict] = mapped_column(JSONB, nullable=False)
    secret_personnel_scope: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    storage_certificate_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    keeper_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    keeper_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    risk_control_item_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    pre_review_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TradeSecretReview(UUIDMixin, Base):
    __tablename__ = "trade_secret_reviews"

    review_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trade_secret_items.id"), nullable=False
    )
    review_organization: Mapped[str | None] = mapped_column(String(100), nullable=True)
    review_period: Mapped[str | None] = mapped_column(String(50), nullable=True)
    review_workflow_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    review_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TradeSecretSuggestion(UUIDMixin, Base):
    __tablename__ = "trade_secret_suggestions"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trade_secret_items.id"), nullable=False
    )
    suggestion_type: Mapped[str] = mapped_column(String(30), nullable=False)
    pre_review_report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    suggestion_content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    keeper_feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)
    keeper_feedback_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    storage_bucket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TradeSecretManagementReport(UUIDMixin, Base):
    __tablename__ = "trade_secret_management_reports"

    report_period: Mapped[str] = mapped_column(String(20), nullable=False)
    report_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    report_type: Mapped[str] = mapped_column(String(30), default="monthly", nullable=False)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_bucket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    statistics_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ═══════════════════════════════════════════════════════════════
# 行为风险 (Behavioral Risk)
# ═══════════════════════════════════════════════════════════════

class BehaviorRiskAnalysisReport(UUIDMixin, Base):
    __tablename__ = "behavior_risk_analysis_reports"

    report_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    business_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    personnel_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    analysis_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    analysis_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    behavior_data_sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    abnormal_behaviors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    correlation_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_bucket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BehaviorRiskManagementReport(UUIDMixin, Base):
    __tablename__ = "behavior_risk_management_reports"

    report_period: Mapped[str] = mapped_column(String(20), nullable=False)
    report_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    report_type: Mapped[str] = mapped_column(String(30), default="monthly", nullable=False)
    monitoring_systems_coverage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    missing_coverage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    data_quality_assessment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    high_risk_behaviors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    high_frequency_behaviors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    optimization_suggestions: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_bucket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ═══════════════════════════════════════════════════════════════
# 持续改善 (Continuous Improvement)
# ═══════════════════════════════════════════════════════════════

class ImprovementIssue(UUIDMixin, Base):
    __tablename__ = "improvement_issues"

    issue_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    project_year: Mapped[str | None] = mapped_column(String(10), nullable=True)
    business_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_module: Mapped[str] = mapped_column(String(30), nullable=False)
    source_project_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_project_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_finding_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    finding_description: Mapped[str] = mapped_column(Text, nullable=False)
    business_cycle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    improvement_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_leader: Mapped[str | None] = mapped_column(String(100), nullable=True)
    risk_control_follower: Mapped[str | None] = mapped_column(String(100), nullable=True)
    responsible_department: Mapped[str] = mapped_column(String(100), nullable=False)
    responsible_person: Mapped[str] = mapped_column(String(100), nullable=False)
    improvement_plan_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_completion_date: Mapped[date] = mapped_column(Date, nullable=False)
    ai_review_plan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ai_review_plan_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_review_plan_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_review_plan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False)
    overdue_days: Mapped[int] = mapped_column(Integer, default=0)
    ai_review_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    audit_review_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_review_evidence_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ai_review_evidence_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_review_evidence_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    response_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending_push", nullable=False)
    direct_recovery_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    indirect_recovery_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    personnel_handling: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_voided: Mapped[bool] = mapped_column(Boolean, default=False)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ImprovementPlan(UUIDMixin, Base):
    __tablename__ = "improvement_plans"

    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("improvement_issues.id", ondelete="CASCADE"), nullable=False
    )
    plan_description: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_paths: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ai_first_review_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_review_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImprovementTask(UUIDMixin, Base):
    __tablename__ = "improvement_tasks"

    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("improvement_issues.id", ondelete="CASCADE"), nullable=False
    )
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    task_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assignee_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assignee_department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    push_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ImprovementEvidence(UUIDMixin, Base):
    __tablename__ = "improvement_evidence"

    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("improvement_issues.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evidence_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_paths: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    storage_bucket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_keys: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImprovementReview(UUIDMixin, Base):
    __tablename__ = "improvement_reviews"

    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("improvement_issues.id", ondelete="CASCADE"), nullable=False
    )
    review_type: Mapped[str] = mapped_column(String(20), nullable=False)
    review_result: Mapped[str] = mapped_column(String(20), nullable=False)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
