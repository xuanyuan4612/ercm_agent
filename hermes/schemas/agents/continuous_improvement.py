"""
持续改善模块 — Agent 输入/输出 Schemas

Agent: improvement-issue-ingest-agent, rectification-plan-review-agent,
       rectification-evidence-review-agent, reminder-escalation-agent,
       closure-acceptance-agent, improvement-knowledge-agent

统一问题数据契约: RemediationIssueRecord (36字段)

参照: doc/agents/08-continuous-improvement-agents.md
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from hermes.schemas.agents.common import Confidence, IssueStatus


class RemediationOperation(StrEnum):
    PLAN_REVIEW = "plan_review"
    EVIDENCE_REVIEW = "evidence_review"
    OVERDUE_CHECK = "overdue_check"


# ═══════════════════════════════════════════════════════════════
# 统一问题数据契约 (36字段)
# ═══════════════════════════════════════════════════════════════

class RemediationIssueRecord(BaseModel):
    """全模块统一的问题数据结构（36字段）"""
    # 基础标识 (5字段)
    issue_sequence: int = 0
    project_year: str = ""
    business_unit: str = ""
    issue_source: str = ""
    audit_project_id: str = ""

    # 问题描述 (6字段)
    audit_project_name: str = ""
    audit_finding_id: str = ""
    audit_finding_desc: str = ""
    business_cycle: str | None = None
    improvement_suggestion: str | None = None
    direct_loss_amount: float | None = None

    # 责任分配 (4字段)
    project_leader: str | None = None
    risk_control_follower: str | None = None
    responsible_dept: str = ""
    responsible_person: str = ""

    # 整改计划 (6字段)
    remediation_plan: str | None = None
    planned_completion_date: str = ""
    ai_plan_review_date: str | None = None
    ai_plan_review_opinion: str | None = None
    auditor_plan_review_opinion: str | None = None
    auditor_plan_review_date: str | None = None

    # 执行跟踪 (4字段)
    actual_completion_date: str | None = None
    is_overdue: bool = False
    overdue_days: int = 0
    remediation_response_count: int = 0

    # 复核 (6字段)
    ai_review_opinion: str | None = None
    ai_review_date: str | None = None
    auditor_review_opinion: str | None = None
    reviewer_name: str | None = None
    ai_evidence_review_date: str | None = None
    ai_evidence_review_opinion: str | None = None

    # 状态与归档 (5字段)
    auditor_evidence_review_date: str | None = None
    status: IssueStatus = IssueStatus.PENDING_PUSH
    indirect_loss_amount: float | None = None
    personnel_disposition: str | None = None
    operation_log: list[dict] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# Agent 输入/输出
# ═══════════════════════════════════════════════════════════════

class RemediationAgentInput(BaseModel):
    """整改跟踪 Agent 输入"""
    task_id: str
    operation: RemediationOperation = RemediationOperation.PLAN_REVIEW
    issue_source: str = ""
    issue_data: dict = Field(default_factory=dict, description="30+字段的问题数据")
    remediation_plan: str | None = None
    remediation_evidence: list[str] | None = None
    plan_deadline: str | None = None
    previous_review_count: int = 0


class RemediationAgentOutput(BaseModel):
    """整改跟踪 Agent 输出"""
    ai_plan_review: dict | None = None  # {feasibility, timeline_reasonability, completeness, suggestions}
    ai_evidence_review: dict | None = None  # {plan_consistency, evidence_sufficiency, quality_assessment}
    overdue_risk: bool = False
    overdue_days: int | None = None
    suggested_actions: list[str] = Field(default_factory=list)
    escalation_needed: bool = False
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


class IssueIngestOutput(BaseModel):
    """问题录入校验输出"""
    field_issues: list[dict] = Field(default_factory=list)
    duplicate_issues: list[dict] = Field(default_factory=list)
    completeness_score: float = 0.0
    suggested_responsibility: dict = Field(default_factory=dict)
    missing_items: list[str] = Field(default_factory=list)
    can_dispatch: bool = True
    blocking_reasons: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class PlanReviewOutput(BaseModel):
    """整改计划初审输出"""
    feasibility_assessment: str = ""
    timeline_reasonability: str = ""
    completeness: str = ""
    risk_points: list[str] = Field(default_factory=list)
    modification_suggestions: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class EvidenceReviewOutput(BaseModel):
    """整改证据复核输出"""
    plan_consistency: str = ""  # 证据是否与计划一致
    evidence_sufficiency: str = ""  # sufficient/partial/insufficient
    quality_assessment: str = ""
    before_after_comparison: str = ""
    return_reasons: list[str] = Field(default_factory=list)
    supplementary_materials: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class ReminderEscalationOutput(BaseModel):
    """催办升级建议输出"""
    reminder_text: str = ""
    escalation_path: str = ""
    risk_alert: bool = False
    suggested_actions: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class ClosureAcceptanceOutput(BaseModel):
    """关闭验收输出"""
    can_close: bool = False
    remaining_risks: list[str] = Field(default_factory=list)
    follow_up_suggestions: list[str] = Field(default_factory=list)
    acceptance_summary: str = ""
    confidence: Confidence = Confidence.MEDIUM


class KnowledgePrecipitationOutput(BaseModel):
    """经验沉淀输出"""
    knowledge_candidates: list[dict] = Field(default_factory=list)
    rule_optimization_suggestions: list[dict] = Field(default_factory=list)
    similarity_tags: list[str] = Field(default_factory=list)
    process_improvement_points: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
