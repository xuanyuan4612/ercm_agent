"""
内控评价模块 — Agent 输入/输出 Schemas（含跨模块共享 Agent Schema）

共享 Agent: audit-plan-agent, audit-check-agent, interview-agent

参照: doc/agents/03-internal-control-evaluation-agents.md
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from hermes.schemas.agents.common import AuditType, Client, Confidence

# ═══════════════════════════════════════════════════════════════
# 审计方案 Agent (audit-plan-agent) — 共享
# ═══════════════════════════════════════════════════════════════

class AuditPlanAgentInput(BaseModel):
    """审计方案 Agent 统一输入接口"""
    task_id: str
    audit_type: AuditType
    client: Client

    # 通用参数
    audit_objective: str
    audit_focus: list[str] = Field(default_factory=list)
    audit_period: str = ""
    audited_entity: str = ""
    project_leader: str = ""
    project_members: list[str] = Field(default_factory=list)

    # 内控评价专用
    business_cycles: list[str] | None = None
    control_activities: list[dict] | None = None
    evaluation_criteria: str | None = None

    # 专项审计专用
    audit_method_preference: str | None = None
    sampling_requirements: str | None = None

    # 离任审计专用
    departing_person_info: dict | None = None
    position_duties: list[str] | None = None
    tenure_years: float | None = None

    context_version: str = "1.0"


class AuditPlan(BaseModel):
    """审计方案统一输出结构"""
    project_basic_info: dict = Field(default_factory=dict)
    evaluation_basis: list[str] = Field(default_factory=list)
    audit_scope: dict = Field(default_factory=dict)
    audit_implementation_rules: list[dict] = Field(default_factory=list)
    deficiency_criteria: dict = Field(default_factory=dict)

    sampling_strategy: dict | None = None
    timeline: dict = Field(default_factory=dict)
    personnel_assignment: dict = Field(default_factory=dict)

    referenced_historical_plans: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class AuditPlanAgentOutput(BaseModel):
    """审计方案 Agent 输出"""
    audit_plan: AuditPlan
    plan_rationale: str = ""
    similar_plans_referenced: list[dict] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    plan_doc_id: str | None = None
    processing_time_ms: int = 0
    kb_sources: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 审计检查 Agent (audit-check-agent) — 共享
# ═══════════════════════════════════════════════════════════════

class CheckType(StrEnum):
    DESIGN = "design"
    EXECUTION = "execution"


class AuditCheckAgentInput(BaseModel):
    """审计检查 Agent 输入"""
    task_id: str
    audit_type: AuditType
    check_type: CheckType

    audit_plan: AuditPlan

    # 设计缺陷评估专用
    design_test_matrix: list[dict] | None = None
    policy_documents: list[str] | None = None
    historical_design_deficiencies: list[dict] | None = None

    # 执行缺陷评估专用
    execution_test_results: list[dict] | None = None
    manual_upload_data: list[dict] | None = None
    historical_execution_deficiencies: list[dict] | None = None

    # 评分标准
    scoring_criteria: dict = Field(default_factory=dict)


class Deficiency(BaseModel):
    """缺陷记录"""
    deficiency_id: str
    deficiency_type: str  # 设计缺陷/执行缺陷
    deficiency_category: str = ""
    description: str
    related_policy: str | None = None
    related_control: str = ""
    business_cycle: str = ""
    severity_score: float = 0.0
    impact_assessment: str = ""
    suggestion: str = ""
    responsible_dept: str = ""


class AuditCheckAgentOutput(BaseModel):
    """审计检查 Agent 输出"""
    deficiencies: list[Deficiency] = Field(default_factory=list)
    total_score: float = 0.0
    score_breakdown: dict = Field(default_factory=dict)
    working_paper_doc_id: str | None = None
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


# ═══════════════════════════════════════════════════════════════
# 访谈 Agent (interview-agent) — 共享
# ═══════════════════════════════════════════════════════════════

class InterviewAgentInput(BaseModel):
    """访谈 Agent 输入"""
    task_id: str
    calling_module: str  # ic_evaluation/special_audit/exit_audit/integrity

    audit_plan_summary: str = ""
    previous_findings: list[str] | None = None

    target_departments: list[str] = Field(default_factory=list)
    target_positions: list[str] = Field(default_factory=list)
    personnel_pool: list[dict] | None = None

    question_focus_areas: list[str] = Field(default_factory=list)


class InterviewQuestionnaire(BaseModel):
    """访谈问卷"""
    target_person: str
    position: str
    department: str
    interview_strategy: str = ""
    questions: list[dict] = Field(default_factory=list)  # [{order, question, purpose, expected_info}]
    estimated_duration_min: int = 30


class InterviewAgentOutput(BaseModel):
    """访谈 Agent 输出"""
    interview_plan: dict = Field(default_factory=dict)
    questionnaires: list[InterviewQuestionnaire] = Field(default_factory=list)
    interview_conclusion_analysis: str | None = None
    need_follow_up: bool | None = None
    follow_up_questions: list[str] | None = None
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0
