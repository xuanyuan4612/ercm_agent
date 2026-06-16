"""
离任审计模块 — Agent 输入/输出 Schemas

Agent: exit-material-agent, exit-issue-agent, exit-issue-confirm-agent, exit-report-agent

共享 Agent (audit-plan-agent, interview-agent) Schema 见 ic_evaluation.py

参照: doc/agents/05-exit-audit-agents.md
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from hermes.schemas.agents.common import Confidence


class ExitAuditAgentInput(BaseModel):
    """离任审计 Agent 输入（公共）"""
    task_id: str
    business_unit: str = ""
    departing_person_name: str
    departing_person_id: str
    position: str = ""
    department: str = ""
    hire_date: str = ""
    last_working_day: str = ""
    position_duties: list[str] = Field(default_factory=list)
    tenure_years: float = 0.0
    audit_period_years: int = 1


class ExitMaterialAgentOutput(BaseModel):
    """资料清单 Agent 输出"""
    material_requirements: list[dict] = Field(default_factory=list)  # [{name, source_system, responsible, deadline}]
    system_data_requests: list[dict] = Field(default_factory=list)
    manual_upload_items: list[dict] = Field(default_factory=list)
    missing_systems_flag: bool = False
    missing_system_notes: str = ""
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


class ExitIssueItem(BaseModel):
    """离任审计问题项"""
    issue_type: str  # personal(个人问题) / business(业务问题)
    issue_category: str  # 商业秘密泄露/个人报销/样机使用/关联公司/流程漏洞/制度缺陷/经济损失
    description: str
    severity: str = "中"
    evidence_ids: list[str] = Field(default_factory=list)
    is_personal: bool = False


class ExitIssueAgentOutput(BaseModel):
    """问题清单 Agent 输出"""
    personal_issues: list[ExitIssueItem] = Field(default_factory=list)
    business_issues: list[ExitIssueItem] = Field(default_factory=list)
    total_personal_issue_count: int = 0
    total_business_issue_count: int = 0
    audit_opinion_table: dict = Field(default_factory=dict)
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


class ExitIssueConfirmOutput(BaseModel):
    """问题确认 Agent 输出"""
    confirmed_issues: list[ExitIssueItem] = Field(default_factory=list)
    issue_confirmations: list[dict] = Field(default_factory=list)  # [{issue_id, is_confirmed, reason}]
    responsibility_assessment: dict = Field(default_factory=dict)
    remediation_directions: list[dict] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


class ExitReportAgentOutput(BaseModel):
    """离任审计报告 Agent 输出"""
    report_title: str = ""
    personal_issue_summary: str = ""
    business_issue_summary: str = ""
    overall_assessment: str = ""
    report_doc_id: str | None = None
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0
