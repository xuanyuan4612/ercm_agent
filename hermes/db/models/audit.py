"""
审计相关模块数据模型

包含：内控评价、专项审计、离任审计
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hermes.db.models.base import UUIDMixin
from hermes.db.session import Base

# ═══════════════════════════════════════════════════════════════
# 内控评价 (IC Evaluation)
# ═══════════════════════════════════════════════════════════════

class ICEvaluationProject(UUIDMixin, Base):
    __tablename__ = "ic_evaluation_projects"

    project_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    evaluation_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    audited_unit: Mapped[str] = mapped_column(String(200), nullable=False)
    evaluation_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    evaluation_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    project_leader: Mapped[str] = mapped_column(String(100), nullable=False)
    project_members: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    business_cycles: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    risk_control_project_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ICControlMatrix(UUIDMixin, Base):
    __tablename__ = "ic_control_matrices"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ic_evaluation_projects.id", ondelete="CASCADE"), nullable=False
    )
    business_cycle: Mapped[str] = mapped_column(String(100), nullable=False)
    level1_process: Mapped[str | None] = mapped_column(String(200), nullable=True)
    control_activity_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    control_target: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_control_point: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_procedure: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    design_test_basis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    execution_test_basis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ICDesignDefect(UUIDMixin, Base):
    __tablename__ = "ic_design_defects"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ic_evaluation_projects.id", ondelete="CASCADE"), nullable=False
    )
    matrix_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ic_control_matrices.id"), nullable=True
    )
    business_cycle: Mapped[str] = mapped_column(String(100), nullable=False)
    regulation_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    regulation_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    defect_type: Mapped[str] = mapped_column(String(50), nullable=False)
    defect_description: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(
        "score", Numeric(5, 2), nullable=True,
    )
    identified_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    identified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ICExecutionDefect(UUIDMixin, Base):
    __tablename__ = "ic_execution_defects"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ic_evaluation_projects.id", ondelete="CASCADE"), nullable=False
    )
    matrix_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ic_control_matrices.id"), nullable=True
    )
    business_cycle: Mapped[str] = mapped_column(String(100), nullable=False)
    defect_type: Mapped[str] = mapped_column(String(50), nullable=False)
    defect_description: Mapped[str] = mapped_column(Text, nullable=False)
    data_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(
        "score", Numeric(5, 2), nullable=True,
    )
    identified_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    identified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ═══════════════════════════════════════════════════════════════
# 专项审计 (Special Audit)
# ═══════════════════════════════════════════════════════════════

class AuditProject(UUIDMixin, Base):
    __tablename__ = "audit_projects"

    project_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    audit_purpose: Mapped[str] = mapped_column(Text, nullable=False)
    audit_focus: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    audit_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    audited_unit: Mapped[str] = mapped_column(String(200), nullable=False)
    project_leader: Mapped[str] = mapped_column(String(100), nullable=False)
    project_members: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risk_control_project_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditPlan(UUIDMixin, Base):
    __tablename__ = "audit_plans"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_projects.id", ondelete="CASCADE"), nullable=False
    )
    plan_type: Mapped[str] = mapped_column(String(30), nullable=False)
    audit_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_strategy: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plan_content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditInterview(UUIDMixin, Base):
    __tablename__ = "audit_interviews"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_projects.id", ondelete="CASCADE"), nullable=False
    )
    interviewee_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    interviewee_department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    interviewee_position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    questionnaire: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    interview_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    interview_conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    interviewer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    interview_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
    attachment_paths: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditChecklist(UUIDMixin, Base):
    __tablename__ = "audit_checklists"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_projects.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_plans.id"), nullable=True
    )
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    check_item: Mapped[str] = mapped_column(Text, nullable=False)
    data_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    check_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_issue_found: Mapped[bool] = mapped_column(Boolean, default=False)
    issue_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    checked_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditFinding(UUIDMixin, Base):
    __tablename__ = "audit_findings"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_projects.id", ondelete="CASCADE"), nullable=False
    )
    finding_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    finding_description: Mapped[str] = mapped_column(Text, nullable=False)
    business_cycle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    related_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    improvement_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditReport(UUIDMixin, Base):
    __tablename__ = "audit_reports"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_projects.id", ondelete="CASCADE"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(30), nullable=False)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_bucket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ═══════════════════════════════════════════════════════════════
# 离任审计 (Exit Audit)
# ═══════════════════════════════════════════════════════════════

class ExitAuditProject(UUIDMixin, Base):
    __tablename__ = "exit_audit_projects"

    project_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    exit_person_name_encrypted: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    exit_person_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    exit_person_department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    exit_person_position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_working_day: Mapped[date] = mapped_column(Date, nullable=False)
    audit_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    audit_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    project_leader: Mapped[str] = mapped_column(String(100), nullable=False)
    project_members: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    responsibility_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risk_control_project_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ICScoreRecord(UUIDMixin, Base):
    __tablename__ = "ic_score_records"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ic_evaluation_projects.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(30), nullable=False)
    dimension_value: Mapped[str] = mapped_column(String(200), nullable=False)
    design_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    execution_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    score_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    scored_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ICEvaluationReport(UUIDMixin, Base):
    __tablename__ = "ic_evaluation_reports"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ic_evaluation_projects.id", ondelete="CASCADE"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(30), nullable=False)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_bucket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    report_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExitAuditPlan(UUIDMixin, Base):
    __tablename__ = "exit_audit_plans"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exit_audit_projects.id", ondelete="CASCADE"), nullable=False
    )
    plan_type: Mapped[str] = mapped_column(String(30), nullable=False)
    responsibility_scope: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    business_scope: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    audit_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_strategy: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExitAuditQuestionnaire(UUIDMixin, Base):
    __tablename__ = "exit_audit_questionnaires"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exit_audit_projects.id", ondelete="CASCADE"), nullable=False
    )
    questionnaire_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    questions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_exit_person_confirmable: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExitAuditDataRequest(UUIDMixin, Base):
    __tablename__ = "exit_audit_data_requests"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exit_audit_projects.id", ondelete="CASCADE"), nullable=False
    )
    data_item: Mapped[str] = mapped_column(Text, nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    request_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    provided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExitAuditFinding(UUIDMixin, Base):
    __tablename__ = "exit_audit_findings"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exit_audit_projects.id", ondelete="CASCADE"), nullable=False
    )
    finding_category: Mapped[str] = mapped_column(String(20), nullable=False)
    finding_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    finding_description: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    related_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    improvement_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExitAuditReport(UUIDMixin, Base):
    __tablename__ = "exit_audit_reports"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exit_audit_projects.id", ondelete="CASCADE"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(30), nullable=False)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_bucket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
