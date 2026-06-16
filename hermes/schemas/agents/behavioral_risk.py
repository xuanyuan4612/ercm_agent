"""
行为风险模块 — Agent 输入/输出 Schemas

Agent: behavior-data-quality-agent, behavior-anomaly-agent,
       behavior-risk-report-agent, behavior-management-report-agent

参照: doc/agents/07-behavioral-risk-agents.md
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from hermes.schemas.agents.common import Confidence


class BehavioralRiskAgentInput(BaseModel):
    """行为风险分析 Agent 输入"""
    task_id: str
    analysis_scope: dict = Field(default_factory=dict)  # {business_unit, department, position, person, role, period}
    behavioral_data_sources: list[str] = Field(default_factory=list)
    employee_lifecycle_info: dict | None = None
    conflict_of_interest_info: dict | None = None
    trade_secret_info: dict | None = None
    historical_analyses: list[dict] | None = None


class BehaviorDataQualityOutput(BaseModel):
    """数据质量检查输出"""
    coverage_report: dict = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    data_integrity_score: float = 0.0
    timeliness_score: float = 0.0
    accuracy_score: float = 0.0
    caliber_conflicts: list[dict] = Field(default_factory=list)
    can_proceed: bool = True
    blocking_reasons: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class BehaviorAnomalyOutput(BaseModel):
    """行为异常识别输出"""
    # [{behavior_type, employee, severity, evidence, related_systems}]
    anomaly_behaviors: list[dict] = Field(default_factory=list)
    anomaly_explanations: list[dict] = Field(default_factory=list)
    correlation_findings: list[dict] = Field(default_factory=list)
    time_line_analysis: dict | None = None
    confidence: Confidence = Confidence.MEDIUM


class BehavioralRiskReportOutput(BaseModel):
    """行为风险分析报告输出"""
    anomaly_findings: list[dict] = Field(default_factory=list)
    risk_level_assessment: dict = Field(default_factory=dict)  # {overall_risk, per_employee_risks, trend}
    correlation_analysis: str = ""
    push_recommendations: list[dict] = Field(default_factory=list)  # 推送到离任审计/风险监控的建议
    human_attention_points: list[str] = Field(default_factory=list)
    report_doc_id: str | None = None
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


class BehaviorManagementReportOutput(BaseModel):
    """管理情况报告输出"""
    coverage_summary: dict = Field(default_factory=dict)
    data_quality_assessment: dict = Field(default_factory=dict)
    high_risk_behaviors_summary: list[dict] = Field(default_factory=list)
    high_frequency_issues: list[dict] = Field(default_factory=list)
    coverage_gap_analysis: dict = Field(default_factory=dict)
    optimization_suggestions: list[str] = Field(default_factory=list)
    report_doc_id: str | None = None
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0
