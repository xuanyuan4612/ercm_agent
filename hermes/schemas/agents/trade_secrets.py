"""
商业秘密模块 — Agent 输入/输出 Schemas

Agent: secret-precheck-agent, secret-policy-compare-agent,
       secret-review-agent, secret-management-report-agent

参照: doc/agents/06-trade-secrets-agents.md
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from hermes.schemas.agents.common import Confidence


class ReviewType(StrEnum):
    PRE_REVIEW = "pre_review"
    FORMAL_REVIEW = "formal_review"


class SecrecyReviewAgentInput(BaseModel):
    """定密评审 Agent 输入"""
    task_id: str
    review_type: ReviewType = ReviewType.PRE_REVIEW
    secrecy_info_table: dict = Field(default_factory=dict, description="《商业秘密信息表》")
    classified_file_list: list[str] = Field(default_factory=list)
    previous_reviews: list[dict] | None = None
    internal_control_policy_refs: list[str] | None = None
    peer_department_reviews: list[dict] | None = None


class SecrecyPrecheckOutput(BaseModel):
    """定密预审输出"""
    pre_review_report: dict = Field(default_factory=dict)
    completeness_check: dict = Field(default_factory=dict)
    suggested_secrecy_level: str = ""
    suggested_secrecy_scope: str = ""
    suggested_duration: str = ""
    missing_items: list[str] = Field(default_factory=list)
    policy_basis: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class SecrecyPolicyCompareOutput(BaseModel):
    """制度比对输出"""
    compliance_result: str = ""  # compliant/partial_conflict/conflict
    conflicts: list[dict] = Field(default_factory=list)
    inconsistencies: list[dict] = Field(default_factory=list)
    pending_human_review: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class SecrecyReviewAgentOutput(BaseModel):
    """定密评审 Agent 输出"""
    pre_review_report: SecrecyPrecheckOutput | None = None
    formal_review_report: dict | None = None
    completeness_score: float = 0.0
    rationality_score: float = 0.0
    lateral_comparison: dict | None = None
    recommendations: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


class MonthlySecrecyReport(BaseModel):
    """商业秘密月度管理报告"""
    report_period: str = ""
    report_scope: str = ""
    total_secrecy_orgs: int = 0
    classified_orgs: int = 0
    classification_rate: float = 0.0
    total_secrecy_processes_cumulative: int = 0
    total_secrecy_items_cumulative: int = 0
    period_processes: int = 0
    period_items: int = 0
    period_new_orgs: int = 0
    trend_direction: str = "持平"
    avg_review_pass_rate: float = 0.0
    common_issues: list[str] = Field(default_factory=list)
    data_charts: list[str] = Field(default_factory=list)
    previous_reports: list[str] = Field(default_factory=list)
    generated_at: str = ""
    generated_by: str = "secret-management-report-agent"


class SecretManagementReportOutput(BaseModel):
    """管理报告 Agent 输出"""
    monthly_report: MonthlySecrecyReport = Field(default_factory=MonthlySecrecyReport)
    risk_alerts: list[dict] = Field(default_factory=list)
    optimization_suggestions: list[str] = Field(default_factory=list)
    report_doc_id: str | None = None
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0
