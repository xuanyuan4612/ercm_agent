"""Add missing tables and indexes — complete Hermes schema

Revision ID: 002
Revises: 001
Create Date: 2026-06-16

变更内容：
  A. 补充 001 缺失的索引 (8):
     knowledge_documents.kb_type, cases.client, cases.risk_control_case_id,
     cases.current_stage, cases.status, case_stages.case_id,
     human_approvals.case_id, generated_documents.case_id

  B. 补充 001 缺失的 22 张表：
     内控评价 (5): ic_control_matrices, ic_design_defects, ic_execution_defects,
                   ic_score_records, ic_evaluation_reports
     专项审计 (4): audit_plans, audit_interviews, audit_checklists, audit_reports
     离任审计 (5): exit_audit_plans, exit_audit_questionnaires, exit_audit_data_requests,
                   exit_audit_findings, exit_audit_reports
     商业秘密 (3): trade_secret_reviews, trade_secret_suggestions, trade_secret_management_reports
     行为风险 (1): behavior_risk_management_reports
     持续改善 (4): improvement_plans, improvement_tasks, improvement_evidence, improvement_reviews
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── A. 补充 001 缺失的索引 ───────────────────────────────

    op.create_index("idx_kb_type", "knowledge_documents", ["kb_type"])
    op.create_index("idx_cases_client", "cases", ["client"])
    op.create_index("idx_cases_risk_control_case", "cases", ["risk_control_case_id"])
    op.create_index("idx_cases_current_stage", "cases", ["current_stage"])
    op.create_index("idx_cases_status", "cases", ["status"])
    op.create_index("idx_case_stages_case", "case_stages", ["case_id"])
    op.create_index("idx_human_approvals_case", "human_approvals", ["case_id"])
    op.create_index("idx_generated_documents_case", "generated_documents", ["case_id"])

    # ── B. 补充 001 缺失的表 ─────────────────────────────────

    # ═══════════════════════════════════════════════════════════════
    # 内控评价 (IC Evaluation) — 补充 5 张表
    # ═══════════════════════════════════════════════════════════════

    op.create_table(
        "ic_control_matrices",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_cycle", sa.String(100), nullable=False),
        sa.Column("level1_process", sa.String(200), nullable=True),
        sa.Column("control_activity_id", sa.String(50), nullable=True),
        sa.Column("control_target", sa.Text(), nullable=True),
        sa.Column("key_control_point", sa.Text(), nullable=True),
        sa.Column("test_procedure", sa.Text(), nullable=True),
        sa.Column("schedule", sa.String(100), nullable=True),
        sa.Column("assignee", sa.String(100), nullable=True),
        sa.Column("design_test_basis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_test_basis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["ic_evaluation_projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_ic_matrix_project", "ic_control_matrices", ["project_id"])

    op.create_table(
        "ic_design_defects",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("matrix_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("business_cycle", sa.String(100), nullable=False),
        sa.Column("regulation_code", sa.String(100), nullable=True),
        sa.Column("regulation_name", sa.String(500), nullable=True),
        sa.Column("defect_type", sa.String(50), nullable=False),
        sa.Column("defect_description", sa.Text(), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("identified_by", sa.String(50), nullable=True),
        sa.Column("identified_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("confirmed_by", sa.String(50), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["ic_evaluation_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matrix_id"], ["ic_control_matrices.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_ic_dd_project", "ic_design_defects", ["project_id"])

    op.create_table(
        "ic_execution_defects",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("matrix_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("business_cycle", sa.String(100), nullable=False),
        sa.Column("defect_type", sa.String(50), nullable=False),
        sa.Column("defect_description", sa.Text(), nullable=False),
        sa.Column("data_source", sa.Text(), nullable=True),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("identified_by", sa.String(50), nullable=True),
        sa.Column("identified_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("confirmed_by", sa.String(50), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["ic_evaluation_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matrix_id"], ["ic_control_matrices.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_ic_ed_project", "ic_execution_defects", ["project_id"])

    op.create_table(
        "ic_score_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dimension", sa.String(30), nullable=False),
        sa.Column("dimension_value", sa.String(200), nullable=False),
        sa.Column("design_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("execution_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("total_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("score_detail", postgresql.JSONB(), nullable=True),
        sa.Column("scored_by", sa.String(50), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["ic_evaluation_projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_ic_score_project", "ic_score_records", ["project_id"])

    op.create_table(
        "ic_evaluation_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.String(30), nullable=False),
        sa.Column("report_path", sa.String(500), nullable=True),
        sa.Column("storage_bucket", sa.String(100), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_final", sa.Boolean(), default=False),
        sa.Column("report_summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["ic_evaluation_projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_ic_report_project", "ic_evaluation_reports", ["project_id"])

    # ═══════════════════════════════════════════════════════════════
    # 专项审计 (Special Audit) — 补充 4 张表
    # ═══════════════════════════════════════════════════════════════

    op.create_table(
        "audit_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_type", sa.String(30), nullable=False),
        sa.Column("audit_scope", sa.Text(), nullable=True),
        sa.Column("audit_method", sa.Text(), nullable=True),
        sa.Column("sample_strategy", sa.String(200), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("schedule", sa.Text(), nullable=True),
        sa.Column("assignee", sa.String(100), nullable=True),
        sa.Column("plan_content", postgresql.JSONB(), nullable=True),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_approved", sa.Boolean(), default=False),
        sa.Column("approved_by", sa.String(50), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["audit_projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_audit_plan_project", "audit_plans", ["project_id"])

    op.create_table(
        "audit_interviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interviewee_name", sa.String(100), nullable=True),
        sa.Column("interviewee_department", sa.String(100), nullable=True),
        sa.Column("interviewee_position", sa.String(100), nullable=True),
        sa.Column("questionnaire", postgresql.JSONB(), nullable=True),
        sa.Column("interview_result", sa.Text(), nullable=True),
        sa.Column("interview_conclusion", sa.Text(), nullable=True),
        sa.Column("interviewer", sa.String(100), nullable=True),
        sa.Column("interview_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), default="planned", nullable=False),
        sa.Column("attachment_paths", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["audit_projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_audit_intv_project", "audit_interviews", ["project_id"])

    op.create_table(
        "audit_checklists",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("check_item", sa.Text(), nullable=False),
        sa.Column("data_source", sa.String(200), nullable=True),
        sa.Column("check_method", sa.String(100), nullable=True),
        sa.Column("expected_result", sa.Text(), nullable=True),
        sa.Column("actual_result", sa.Text(), nullable=True),
        sa.Column("is_issue_found", sa.Boolean(), default=False),
        sa.Column("issue_ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("checked_by", sa.String(50), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["audit_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["audit_plans.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_audit_cl_project", "audit_checklists", ["project_id"])

    op.create_table(
        "audit_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.String(30), nullable=False),
        sa.Column("report_path", sa.String(500), nullable=True),
        sa.Column("storage_bucket", sa.String(100), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_final", sa.Boolean(), default=False),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["audit_projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_audit_report_project", "audit_reports", ["project_id"])

    # ═══════════════════════════════════════════════════════════════
    # 离任审计 (Exit Audit) — 补充 5 张表
    # ═══════════════════════════════════════════════════════════════

    op.create_table(
        "exit_audit_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_type", sa.String(30), nullable=False),
        sa.Column("responsibility_scope", postgresql.JSONB(), nullable=True),
        sa.Column("business_scope", postgresql.JSONB(), nullable=True),
        sa.Column("audit_method", sa.Text(), nullable=True),
        sa.Column("sample_strategy", sa.String(200), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_approved", sa.Boolean(), default=False),
        sa.Column("approved_by", sa.String(50), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["exit_audit_projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_ea_plan_project", "exit_audit_plans", ["project_id"])

    op.create_table(
        "exit_audit_questionnaires",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("questionnaire_type", sa.String(30), nullable=True),
        sa.Column("questions", postgresql.JSONB(), nullable=False),
        sa.Column("is_exit_person_confirmable", sa.Boolean(), default=False),
        sa.Column("confirmed_by", sa.String(50), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["exit_audit_projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_ea_q_project", "exit_audit_questionnaires", ["project_id"])

    op.create_table(
        "exit_audit_data_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_item", sa.Text(), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=True),
        sa.Column("provider_department", sa.String(100), nullable=True),
        sa.Column("data_source", sa.String(200), nullable=True),
        sa.Column("request_status", sa.String(20), default="pending", nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["exit_audit_projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_ea_dr_project", "exit_audit_data_requests", ["project_id"])

    op.create_table(
        "exit_audit_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_category", sa.String(20), nullable=False),
        sa.Column("finding_code", sa.String(50), nullable=False),
        sa.Column("finding_description", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(10), nullable=True),
        sa.Column("related_evidence", postgresql.JSONB(), nullable=True),
        sa.Column("improvement_suggestion", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("confirmed_by", sa.String(50), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finding_code"),
        sa.ForeignKeyConstraint(["project_id"], ["exit_audit_projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_ea_finding_project", "exit_audit_findings", ["project_id"])

    op.create_table(
        "exit_audit_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.String(30), nullable=False),
        sa.Column("report_path", sa.String(500), nullable=True),
        sa.Column("storage_bucket", sa.String(100), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("is_final", sa.Boolean(), default=False),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["exit_audit_projects.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_ea_report_project", "exit_audit_reports", ["project_id"])

    # ═══════════════════════════════════════════════════════════════
    # 商业秘密 (Trade Secret) — 补充 3 张表
    # ═══════════════════════════════════════════════════════════════

    op.create_table(
        "trade_secret_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("review_code", sa.String(50), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_organization", sa.String(100), nullable=True),
        sa.Column("review_period", sa.String(50), nullable=True),
        sa.Column("review_workflow_id", sa.String(50), nullable=True),
        sa.Column("review_result", postgresql.JSONB(), nullable=True),
        sa.Column("reviewer_id", sa.String(50), nullable=True),
        sa.Column("review_status", sa.String(20), default="pending", nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_code"),
        sa.ForeignKeyConstraint(["item_id"], ["trade_secret_items.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_ts_review_item", "trade_secret_reviews", ["item_id"])

    op.create_table(
        "trade_secret_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suggestion_type", sa.String(30), nullable=False),
        sa.Column("pre_review_report_path", sa.String(500), nullable=True),
        sa.Column("suggestion_content", postgresql.JSONB(), nullable=True),
        sa.Column("keeper_feedback", sa.String(20), nullable=True),
        sa.Column("keeper_feedback_detail", sa.Text(), nullable=True),
        sa.Column("feedback_status", sa.String(20), default="pending", nullable=False),
        sa.Column("storage_bucket", sa.String(100), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["item_id"], ["trade_secret_items.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_ts_sugg_item", "trade_secret_suggestions", ["item_id"])

    op.create_table(
        "trade_secret_management_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("report_period", sa.String(20), nullable=False),
        sa.Column("report_scope", sa.String(100), nullable=False),
        sa.Column("report_type", sa.String(30), default="monthly", nullable=False),
        sa.Column("report_path", sa.String(500), nullable=True),
        sa.Column("storage_bucket", sa.String(100), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("statistics_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ═══════════════════════════════════════════════════════════════
    # 行为风险 (Behavioral Risk) — 补充 1 张表
    # ═══════════════════════════════════════════════════════════════

    op.create_table(
        "behavior_risk_management_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("report_period", sa.String(20), nullable=False),
        sa.Column("report_scope", sa.String(100), nullable=False),
        sa.Column("report_type", sa.String(30), default="monthly", nullable=False),
        sa.Column("monitoring_systems_coverage", postgresql.JSONB(), nullable=True),
        sa.Column("missing_coverage", postgresql.JSONB(), nullable=True),
        sa.Column("data_quality_assessment", postgresql.JSONB(), nullable=True),
        sa.Column("high_risk_behaviors", postgresql.JSONB(), nullable=True),
        sa.Column("high_frequency_behaviors", postgresql.JSONB(), nullable=True),
        sa.Column("optimization_suggestions", sa.Text(), nullable=True),
        sa.Column("report_path", sa.String(500), nullable=True),
        sa.Column("storage_bucket", sa.String(100), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ═══════════════════════════════════════════════════════════════
    # 持续改善 (Continuous Improvement) — 补充 4 张表
    # ═══════════════════════════════════════════════════════════════

    op.create_table(
        "improvement_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_description", sa.Text(), nullable=False),
        sa.Column("attachment_paths", postgresql.JSONB(), nullable=True),
        sa.Column("submitted_by", sa.String(100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ai_first_review_opinion", sa.Text(), nullable=True),
        sa.Column("audit_review_opinion", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(20), default="pending", nullable=False),
        sa.Column("reviewed_by", sa.String(100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["issue_id"], ["improvement_issues.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_imp_plan_issue", "improvement_plans", ["issue_id"])

    op.create_table(
        "improvement_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_name", sa.String(200), nullable=False),
        sa.Column("task_description", sa.Text(), nullable=True),
        sa.Column("assignee_id", sa.String(50), nullable=True),
        sa.Column("assignee_name", sa.String(100), nullable=True),
        sa.Column("assignee_department", sa.String(100), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False),
        sa.Column("push_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["issue_id"], ["improvement_issues.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_imp_task_issue", "improvement_tasks", ["issue_id"])

    op.create_table(
        "improvement_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(50), nullable=True),
        sa.Column("evidence_description", sa.Text(), nullable=True),
        sa.Column("attachment_paths", postgresql.JSONB(), nullable=True),
        sa.Column("storage_bucket", sa.String(100), nullable=True),
        sa.Column("storage_keys", postgresql.JSONB(), nullable=True),
        sa.Column("submitted_by", sa.String(100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["issue_id"], ["improvement_issues.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_imp_evid_issue", "improvement_evidence", ["issue_id"])

    op.create_table(
        "improvement_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_type", sa.String(20), nullable=False),
        sa.Column("review_result", sa.String(20), nullable=False),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("return_reason", sa.Text(), nullable=True),
        sa.Column("reviewer_id", sa.String(100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["issue_id"], ["improvement_issues.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_imp_review_issue", "improvement_reviews", ["issue_id"])


def downgrade() -> None:
    """Drop all added tables and indexes in reverse dependency order"""
    # B. 删除新增表
    op.drop_table("improvement_reviews")
    op.drop_table("improvement_evidence")
    op.drop_table("improvement_tasks")
    op.drop_table("improvement_plans")
    op.drop_table("behavior_risk_management_reports")
    op.drop_table("trade_secret_management_reports")
    op.drop_table("trade_secret_suggestions")
    op.drop_table("trade_secret_reviews")
    op.drop_table("exit_audit_reports")
    op.drop_table("exit_audit_findings")
    op.drop_table("exit_audit_data_requests")
    op.drop_table("exit_audit_questionnaires")
    op.drop_table("exit_audit_plans")
    op.drop_table("audit_reports")
    op.drop_table("audit_checklists")
    op.drop_table("audit_interviews")
    op.drop_table("audit_plans")
    op.drop_table("ic_evaluation_reports")
    op.drop_table("ic_score_records")
    op.drop_table("ic_execution_defects")
    op.drop_table("ic_design_defects")
    op.drop_table("ic_control_matrices")

    # A. 删除新增索引（对应 001 缺失的索引）
    op.drop_index("idx_generated_documents_case", table_name="generated_documents")
    op.drop_index("idx_human_approvals_case", table_name="human_approvals")
    op.drop_index("idx_case_stages_case", table_name="case_stages")
    op.drop_index("idx_cases_status", table_name="cases")
    op.drop_index("idx_cases_current_stage", table_name="cases")
    op.drop_index("idx_cases_risk_control_case", table_name="cases")
    op.drop_index("idx_cases_client", table_name="cases")
    op.drop_index("idx_kb_type", table_name="knowledge_documents")
