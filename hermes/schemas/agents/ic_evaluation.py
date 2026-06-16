"""
内控评价模块 — Agent 输入/输出 Schemas（含跨模块共享 Agent Schema）

共享 Agent: audit-plan-agent, audit-check-agent, interview-agent

参照: doc/agents/03-internal-control-evaluation-agents.md
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, List, Dict, Any

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
    audit_focus: List[str] = Field(default_factory=list)
    audit_period: str = ""
    audited_entity: str = ""
    project_leader: str = ""
    project_members: List[str] = Field(default_factory=list)

    # 内控评价专用
    business_cycles: Optional[List[str]] = None
    control_activities: Optional[List[dict]] = None
    evaluation_criteria: Optional[str] = None

    # 专项审计专用
    audit_method_preference: Optional[str] = None
    sampling_requirements: Optional[str] = None

    # 离任审计专用
    departing_person_info: Optional[dict] = None
    position_duties: Optional[List[str]] = None
    tenure_years: Optional[float] = None

    context_version: str = "1.0"


class AuditPlan(BaseModel):
    """审计方案统一输出结构"""
    project_basic_info: dict = Field(default_factory=dict)
    evaluation_basis: List[str] = Field(default_factory=list)
    audit_scope: dict = Field(default_factory=dict)
    audit_implementation_rules: List[dict] = Field(default_factory=list)
    deficiency_criteria: dict = Field(default_factory=dict)

    sampling_strategy: Optional[dict] = None
    timeline: dict = Field(default_factory=dict)
    personnel_assignment: dict = Field(default_factory=dict)

    referenced_historical_plans: List[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class AuditPlanAgentOutput(BaseModel):
    """审计方案 Agent 输出"""
    audit_plan: AuditPlan
    plan_rationale: str = ""
    similar_plans_referenced: List[dict] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    plan_doc_id: Optional[str] = None
    processing_time_ms: int = 0
    kb_sources: List[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 审计检查 Agent (audit-check-agent) — 共享
# ═══════════════════════════════════════════════════════════════

class CheckType(str, Enum):
    DESIGN = "design"
    EXECUTION = "execution"


class AuditCheckAgentInput(BaseModel):
    """审计检查 Agent 输入"""
    task_id: str
    audit_type: AuditType
    check_type: CheckType

    audit_plan: AuditPlan

    # 设计缺陷评估专用
    design_test_matrix: Optional[List[dict]] = None
    policy_documents: Optional[List[str]] = None
    historical_design_deficiencies: Optional[List[dict]] = None

    # 执行缺陷评估专用
    execution_test_results: Optional[List[dict]] = None
    manual_upload_data: Optional[List[dict]] = None
    historical_execution_deficiencies: Optional[List[dict]] = None

    # 评分标准
    scoring_criteria: dict = Field(default_factory=dict)


class Deficiency(BaseModel):
    """缺陷记录"""
    deficiency_id: str
    deficiency_type: str  # 设计缺陷/执行缺陷
    deficiency_category: str = ""
    description: str
    related_policy: Optional[str] = None
    related_control: str = ""
    business_cycle: str = ""
    severity_score: float = 0.0
    impact_assessment: str = ""
    suggestion: str = ""
    responsible_dept: str = ""


class AuditCheckAgentOutput(BaseModel):
    """审计检查 Agent 输出"""
    deficiencies: List[Deficiency] = Field(default_factory=list)
    total_score: float = 0.0
    score_breakdown: dict = Field(default_factory=dict)
    working_paper_doc_id: Optional[str] = None
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
    previous_findings: Optional[List[str]] = None

    target_departments: List[str] = Field(default_factory=list)
    target_positions: List[str] = Field(default_factory=list)
    personnel_pool: Optional[List[dict]] = None

    question_focus_areas: List[str] = Field(default_factory=list)


class InterviewQuestionnaire(BaseModel):
    """访谈问卷"""
    target_person: str
    position: str
    department: str
    interview_strategy: str = ""
    questions: List[dict] = Field(default_factory=list)  # [{order, question, purpose, expected_info}]
    estimated_duration_min: int = 30


class InterviewAgentOutput(BaseModel):
    """访谈 Agent 输出"""
    interview_plan: dict = Field(default_factory=dict)
    questionnaires: List[InterviewQuestionnaire] = Field(default_factory=list)
    interview_conclusion_analysis: Optional[str] = None
    need_follow_up: Optional[bool] = None
    follow_up_questions: Optional[List[str]] = None
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0
