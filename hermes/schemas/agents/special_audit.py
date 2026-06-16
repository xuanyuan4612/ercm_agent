"""
专项审计模块 — Agent 输入/输出 Schemas

Agent: special-issue-confirm-agent, special-audit-report-agent

共享 Agent 的 Schema 见 ic_evaluation.py (audit-plan-agent, audit-check-agent, interview-agent)

参照: doc/agents/04-special-audit-agents.md
"""

from __future__ import annotations

from typing import Optional, List

from pydantic import BaseModel, Field

from hermes.schemas.agents.common import Confidence


class SpecialIssueConfirmInput(BaseModel):
    """问题确认 Agent 输入"""
    task_id: str
    audit_objective: str = ""
    issue_drafts: List[dict] = Field(default_factory=list, description="问题草稿列表")
    auditee_feedback: List[dict] = Field(default_factory=list, description="被审计单位反馈")
    supplementary_evidence: List[str] = Field(default_factory=list)
    policy_basis: List[dict] = Field(default_factory=list)


class ConfirmedIssue(BaseModel):
    """已确认问题"""
    issue_id: str
    title: str
    description: str
    is_confirmed: bool
    evidence_ids: List[str] = Field(default_factory=list)
    policy_refs: List[str] = Field(default_factory=list)
    severity: str = "中"
    suggested_remediation: str = ""
    responsible_dept: str = ""
    pending_materials: List[str] = Field(default_factory=list)


class SpecialIssueConfirmOutput(BaseModel):
    """问题确认 Agent 输出"""
    confirmed_issues: List[ConfirmedIssue] = Field(default_factory=list)
    rejected_issues: List[dict] = Field(default_factory=list)  # 反馈合理，不成立
    uncertain_issues: List[dict] = Field(default_factory=list)  # 需进一步核实
    adjustment_summary: str = ""
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


class SpecialAuditReportInput(BaseModel):
    """专项审计报告 Agent 输入"""
    task_id: str
    audit_objective: str = ""
    confirmed_issues: List[ConfirmedIssue] = Field(default_factory=list)
    audit_plan_summary: str = ""
    audit_workpapers: List[str] = Field(default_factory=list)
    project_info: dict = Field(default_factory=dict)


class SpecialAuditReportOutput(BaseModel):
    """专项审计报告 Agent 输出"""
    report_title: str = ""
    report_content: dict = Field(default_factory=dict)
    issue_summary_list: List[dict] = Field(default_factory=list)  # 问题清单摘要
    remediation_suggestions: List[dict] = Field(default_factory=list)
    report_doc_id: Optional[str] = None
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0
