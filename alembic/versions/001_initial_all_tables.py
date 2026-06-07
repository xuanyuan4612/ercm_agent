"""Initial migration — all Hermes tables

Revision ID: 001
Revises: None
Create Date: 2026-06-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # for gen_random_uuid()

    # ── 共享基础表 ─────────────────────────────────────────────

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("login_attempts", sa.Integer(), default=0),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("idx_users_role", "users", ["role"], postgresql_where=sa.text("is_active"))
    op.create_index("idx_users_username", "users", ["username"])

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("operator_id", sa.String(50), nullable=True),
        sa.Column("operator_role", sa.String(20), nullable=True),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("target_table", sa.String(50), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("changes", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "external_sync_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_module", sa.String(30), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("system_name", sa.String(50), nullable=False),
        sa.Column("sync_type", sa.String(30), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=True),
        sa.Column("response_payload", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("retry_count", sa.SmallInteger(), default=0),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "a2a_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_module", sa.String(30), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_agent", sa.String(50), nullable=False),
        sa.Column("command", sa.String(50), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=True),
        sa.Column("response_payload", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("callback_received", sa.Boolean(), default=False),
        sa.Column("retry_count", sa.SmallInteger(), default=0),
        sa.Column("max_retries", sa.SmallInteger(), default=3),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 廉洁监察 ─────────────────────────────────────────────

    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", sa.String(30), nullable=False),
        sa.Column("case_code", sa.String(50), nullable=True),
        sa.Column("fraud_source", sa.String(30), nullable=False),
        sa.Column("client", sa.String(20), nullable=False),
        sa.Column("reported_staff_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("reported_suppliers_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("reported_dealers_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("fraud_tel_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("fraud_email_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("fraud_event_detail", sa.Text(), nullable=True),
        sa.Column("proof", sa.Text(), nullable=True),
        sa.Column("attachments", postgresql.JSONB(), nullable=True),
        sa.Column("risk_control_case_id", sa.String(50), nullable=True),
        sa.Column("current_stage", sa.String(50), nullable=True),
        sa.Column("workflow_state", postgresql.JSONB(), nullable=True),
        sa.Column("langgraph_thread_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False),
        sa.Column("is_deleted", sa.Boolean(), default=False),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("updated_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )

    op.create_table(
        "case_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_name", sa.String(50), nullable=False),
        sa.Column("stage_order", sa.SmallInteger(), nullable=False),
        sa.Column("ai_input", postgresql.JSONB(), nullable=True),
        sa.Column("ai_output", postgresql.JSONB(), nullable=True),
        sa.Column("knowledge_refs", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_info", postgresql.JSONB(), nullable=True),
        sa.Column("retry_count", sa.SmallInteger(), default=0),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "human_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_name", sa.String(50), nullable=False),
        sa.Column("reviewer_id", sa.String(50), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("original_output", postgresql.JSONB(), nullable=True),
        sa.Column("modified_output", postgresql.JSONB(), nullable=True),
        sa.Column("modifications_summary", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("signature", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "generated_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doc_type", sa.String(50), nullable=False),
        sa.Column("stage_name", sa.String(50), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_format", sa.String(10), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_confirmed", sa.Boolean(), default=False),
        sa.Column("storage_bucket", sa.String(100), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
    )

    # ── 风险监控 ─────────────────────────────────────────────

    op.create_table(
        "risk_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("rule_code", sa.String(50), nullable=False),
        sa.Column("business_unit", sa.String(50), nullable=True),
        sa.Column("channel", sa.String(50), nullable=True),
        sa.Column("format", sa.String(50), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("position", sa.String(100), nullable=True),
        sa.Column("personnel_info", sa.Text(), nullable=True),
        sa.Column("business_cycle", sa.String(100), nullable=True),
        sa.Column("level1_scene", sa.String(100), nullable=True),
        sa.Column("level2_scene", sa.String(100), nullable=True),
        sa.Column("level3_scene", sa.String(100), nullable=False),
        sa.Column("sql_statement", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("threshold", sa.Numeric(12, 4), nullable=True),
        sa.Column("monitor_frequency", sa.String(20), nullable=False),
        sa.Column("monitor_business_unit", sa.String(50), nullable=True),
        sa.Column("use_external_data", sa.Boolean(), default=False),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("reviewed_by", sa.String(50), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("updated_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_code"),
    )

    op.create_table(
        "risk_analysis_subjects",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("subject_code", sa.String(50), nullable=False),
        sa.Column("subject_name", sa.String(200), nullable=False),
        sa.Column("subject_type", sa.String(30), nullable=False),
        sa.Column("contact_info", postgresql.JSONB(), nullable=True),
        sa.Column("merge_source_ids", postgresql.JSONB(), nullable=True),
        sa.Column("risk_behavior", sa.Text(), nullable=True),
        sa.Column("risk_business", sa.Text(), nullable=True),
        sa.Column("impact_scope", sa.Text(), nullable=True),
        sa.Column("involved_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("analysis_report_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_code"),
    )

    op.create_table(
        "risk_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("alert_code", sa.String(50), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("business_unit", sa.String(50), nullable=True),
        sa.Column("alert_time", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("alert_data", postgresql.JSONB(), nullable=True),
        sa.Column("risk_type", sa.String(50), nullable=False),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("severity", sa.String(10), nullable=True),
        sa.Column("widespread", sa.String(10), nullable=True),
        sa.Column("impact_degree", sa.Text(), nullable=True),
        sa.Column("impact_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("handling_suggestion", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False),
        sa.Column("reviewed_by", sa.String(50), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alert_code"),
        sa.ForeignKeyConstraint(["rule_id"], ["risk_rules.id"]),
        sa.ForeignKeyConstraint(["analysis_subject_id"], ["risk_analysis_subjects.id"]),
    )

    op.create_table(
        "risk_push_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_module", sa.String(30), nullable=False),
        sa.Column("target_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("push_payload", postgresql.JSONB(), nullable=True),
        sa.Column("push_status", sa.String(20), default="pending"),
        sa.Column("callback_status", sa.String(20), default="pending"),
        sa.Column("callback_detail", postgresql.JSONB(), nullable=True),
        sa.Column("push_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("callback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["alert_id"], ["risk_alerts.id"]),
    )

    op.create_table(
        "rule_iteration_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("iteration_type", sa.String(20), nullable=False),
        sa.Column("old_sql", sa.Text(), nullable=True),
        sa.Column("new_sql", sa.Text(), nullable=True),
        sa.Column("old_threshold", sa.Numeric(12, 4), nullable=True),
        sa.Column("new_threshold", sa.Numeric(12, 4), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("operator_id", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["rule_id"], ["risk_rules.id"]),
    )

    # ── 内控评价 ─────────────────────────────────────────────

    op.create_table(
        "ic_evaluation_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_code", sa.String(50), nullable=False),
        sa.Column("project_name", sa.String(200), nullable=False),
        sa.Column("evaluation_purpose", sa.Text(), nullable=True),
        sa.Column("audited_unit", sa.String(200), nullable=False),
        sa.Column("evaluation_period_start", sa.Date(), nullable=False),
        sa.Column("evaluation_period_end", sa.Date(), nullable=False),
        sa.Column("project_leader", sa.String(100), nullable=False),
        sa.Column("project_members", postgresql.JSONB(), nullable=True),
        sa.Column("business_cycles", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("risk_control_project_id", sa.String(50), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("updated_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_code"),
    )

    # ── 知识库 ───────────────────────────────────────────────

    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kb_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("metadata_", postgresql.JSONB(), nullable=True),
        sa.Column("source_path", sa.String(500), nullable=True),
        sa.Column("chunk_index", sa.Integer(), default=1),
        sa.Column("total_chunks", sa.Integer(), default=1),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 持续改善 ─────────────────────────────────────────────

    op.create_table(
        "improvement_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("issue_code", sa.String(50), nullable=False),
        sa.Column("project_year", sa.String(10), nullable=True),
        sa.Column("business_unit", sa.String(50), nullable=True),
        sa.Column("source_module", sa.String(30), nullable=False),
        sa.Column("source_project_code", sa.String(50), nullable=True),
        sa.Column("source_project_name", sa.String(200), nullable=True),
        sa.Column("source_finding_code", sa.String(50), nullable=True),
        sa.Column("finding_description", sa.Text(), nullable=False),
        sa.Column("business_cycle", sa.String(100), nullable=True),
        sa.Column("improvement_suggestion", sa.Text(), nullable=True),
        sa.Column("project_leader", sa.String(100), nullable=True),
        sa.Column("risk_control_follower", sa.String(100), nullable=True),
        sa.Column("responsible_department", sa.String(100), nullable=False),
        sa.Column("responsible_person", sa.String(100), nullable=False),
        sa.Column("improvement_plan_requirement", sa.Text(), nullable=True),
        sa.Column("planned_completion_date", sa.Date(), nullable=False),
        sa.Column("ai_review_plan_date", sa.Date(), nullable=True),
        sa.Column("ai_review_plan_opinion", sa.Text(), nullable=True),
        sa.Column("audit_review_plan_opinion", sa.Text(), nullable=True),
        sa.Column("audit_review_plan_date", sa.Date(), nullable=True),
        sa.Column("actual_completion_date", sa.Date(), nullable=True),
        sa.Column("is_overdue", sa.Boolean(), default=False),
        sa.Column("overdue_days", sa.Integer(), default=0),
        sa.Column("ai_review_opinion", sa.Text(), nullable=True),
        sa.Column("ai_review_date", sa.Date(), nullable=True),
        sa.Column("audit_review_opinion", sa.Text(), nullable=True),
        sa.Column("reviewer", sa.String(100), nullable=True),
        sa.Column("ai_review_evidence_date", sa.Date(), nullable=True),
        sa.Column("ai_review_evidence_opinion", sa.Text(), nullable=True),
        sa.Column("audit_review_evidence_date", sa.Date(), nullable=True),
        sa.Column("response_count", sa.Integer(), default=0),
        sa.Column("status", sa.String(20), default="pending_push", nullable=False),
        sa.Column("direct_recovery_amount", sa.Numeric(18, 2), default=0),
        sa.Column("indirect_recovery_amount", sa.Numeric(18, 2), default=0),
        sa.Column("personnel_handling", sa.Text(), nullable=True),
        sa.Column("is_voided", sa.Boolean(), default=False),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("updated_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_code"),
    )

    # ── 专项审计 ─────────────────────────────────────────────

    op.create_table(
        "audit_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_code", sa.String(50), nullable=False),
        sa.Column("project_name", sa.String(200), nullable=False),
        sa.Column("audit_purpose", sa.Text(), nullable=False),
        sa.Column("audit_focus", sa.Text(), nullable=True),
        sa.Column("audit_period_start", sa.Date(), nullable=False),
        sa.Column("audit_period_end", sa.Date(), nullable=False),
        sa.Column("audited_unit", sa.String(200), nullable=False),
        sa.Column("project_leader", sa.String(100), nullable=False),
        sa.Column("project_members", postgresql.JSONB(), nullable=True),
        sa.Column("risk_control_project_id", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("updated_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_code"),
    )

    op.create_table(
        "audit_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_code", sa.String(50), nullable=False),
        sa.Column("finding_description", sa.Text(), nullable=False),
        sa.Column("business_cycle", sa.String(100), nullable=True),
        sa.Column("risk_level", sa.String(10), nullable=True),
        sa.Column("related_evidence", postgresql.JSONB(), nullable=True),
        sa.Column("improvement_suggestion", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("confirmed_by", sa.String(50), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finding_code"),
        sa.ForeignKeyConstraint(["project_id"], ["audit_projects.id"], ondelete="CASCADE"),
    )

    # ── 离任审计 ─────────────────────────────────────────────

    op.create_table(
        "exit_audit_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_code", sa.String(50), nullable=False),
        sa.Column("project_name", sa.String(200), nullable=False),
        sa.Column("business_unit", sa.String(50), nullable=False),
        sa.Column("exit_person_name_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("exit_person_id", sa.String(50), nullable=True),
        sa.Column("exit_person_department", sa.String(100), nullable=True),
        sa.Column("exit_person_position", sa.String(100), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=True),
        sa.Column("last_working_day", sa.Date(), nullable=False),
        sa.Column("audit_period_start", sa.Date(), nullable=False),
        sa.Column("audit_period_end", sa.Date(), nullable=False),
        sa.Column("project_leader", sa.String(100), nullable=False),
        sa.Column("project_members", postgresql.JSONB(), nullable=True),
        sa.Column("responsibility_config", postgresql.JSONB(), nullable=True),
        sa.Column("risk_control_project_id", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("updated_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_code"),
    )

    # ── 商业秘密 ─────────────────────────────────────────────

    op.create_table(
        "trade_secret_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("item_code", sa.String(50), nullable=False),
        sa.Column("item_name", sa.String(200), nullable=False),
        sa.Column("secret_type", sa.String(50), nullable=False),
        sa.Column("secret_level", sa.String(20), nullable=False),
        sa.Column("business_unit", sa.String(50), nullable=False),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("project_name", sa.String(200), nullable=True),
        sa.Column("file_list", postgresql.JSONB(), nullable=False),
        sa.Column("secret_personnel_scope", postgresql.JSONB(), nullable=True),
        sa.Column("storage_certificate_no", sa.String(100), nullable=True),
        sa.Column("keeper_id", sa.String(50), nullable=True),
        sa.Column("keeper_name", sa.String(100), nullable=True),
        sa.Column("risk_control_item_id", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("pre_review_count", sa.Integer(), default=0),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("updated_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_code"),
    )

    # ── 行为风险 ─────────────────────────────────────────────

    op.create_table(
        "behavior_risk_analysis_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("report_code", sa.String(50), nullable=False),
        sa.Column("business_unit", sa.String(50), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("position", sa.String(100), nullable=True),
        sa.Column("personnel_name", sa.String(100), nullable=True),
        sa.Column("role_type", sa.String(50), nullable=True),
        sa.Column("analysis_period_start", sa.Date(), nullable=False),
        sa.Column("analysis_period_end", sa.Date(), nullable=False),
        sa.Column("behavior_data_sources", postgresql.JSONB(), nullable=True),
        sa.Column("abnormal_behaviors", postgresql.JSONB(), nullable=True),
        sa.Column("risk_level", sa.String(10), nullable=True),
        sa.Column("correlation_analysis", sa.Text(), nullable=True),
        sa.Column("report_path", sa.String(500), nullable=True),
        sa.Column("storage_bucket", sa.String(100), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("reviewed_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_code"),
    )


def downgrade() -> None:
    """Drop all tables in reverse order"""
    op.drop_table("behavior_risk_analysis_reports")
    op.drop_table("trade_secret_items")
    op.drop_table("exit_audit_projects")
    op.drop_table("audit_findings")
    op.drop_table("audit_projects")
    op.drop_table("improvement_issues")
    op.drop_table("knowledge_documents")
    op.drop_table("ic_evaluation_projects")
    op.drop_table("rule_iteration_log")
    op.drop_table("risk_push_records")
    op.drop_table("risk_alerts")
    op.drop_table("risk_analysis_subjects")
    op.drop_table("risk_rules")
    op.drop_table("generated_documents")
    op.drop_table("human_approvals")
    op.drop_table("case_stages")
    op.drop_table("cases")
    op.drop_table("a2a_tasks")
    op.drop_table("external_sync_logs")
    op.drop_table("audit_log")
    op.drop_table("users")
