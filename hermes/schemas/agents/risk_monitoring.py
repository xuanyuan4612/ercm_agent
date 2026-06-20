"""
风险监控模块 — Agent 输入/输出 Schemas

Agent: risk-rule-agent, risk-scan-agent, risk-merge-agent, risk-classify-agent

参照:
  - doc/agents/02-risk-monitoring-agents.md (详细设计)
  - doc/agents/02b-risk-monitoring-architecture-analysis.md (架构分析)
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from hermes.schemas.agents.common import Confidence


class RuleGenerationMode(StrEnum):
    BATCH_UPLOAD = "batch_upload"
    MANUAL_INPUT = "manual_input"


class RiskRuleAgentInput(BaseModel):
    """风险规则 Agent 输入"""
    task_id: str
    mode: RuleGenerationMode

    uploaded_rules: list[dict] | None = Field(None, description="已上传的风险场景清单")
    manual_scenario: str | None = Field(None, description="人工自定义场景描述")
    target_business_cycle: str | None = Field(None, description="目标业务循环")
    target_department: str | None = Field(None, description="目标部门/事业部")

    db_schema_context: dict = Field(default_factory=dict, description="数据库字段及含义")
    historical_cases: list[dict] = Field(default_factory=list, description="历史案例参考")


class RiskRule(BaseModel):
    """单条风险规则"""
    business_unit: str
    channel: str | None = None
    business_format: str | None = None
    business_cycle: str
    department: str
    position: str | None = None
    personnel_info: str | None = None
    level1_scenario: str
    level2_scenario: str
    level3_scenario: str
    sql_statement: str
    risk_level: str = "中"
    threshold: str | None = None
    monitor_frequency: str = "daily"
    monitor_business_unit: str
    use_external_data: bool = False


class RiskRuleAgentOutput(BaseModel):
    """风险规则 Agent 输出"""
    rules: list[RiskRule]
    sql_validation_results: list[dict] = Field(default_factory=list)
    generation_rationale: str = ""
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


class RiskExecutionMode(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class RiskAnalysisAgentInput(BaseModel):
    """风险分析 Agent 输入"""
    task_id: str
    execution_mode: RiskExecutionMode = RiskExecutionMode.SCHEDULED

    risk_rules: list[RiskRule] = Field(default_factory=list, description="已审核通过的风险规则清单")
    business_data_sources: list[str] = Field(default_factory=list)
    external_data_sources: list[str] = Field(default_factory=list)

    target_business_units: list[str] = Field(default_factory=list)
    execution_date_range: dict | None = Field(None, description="手动指定日期范围")


class AnomalyRecord(BaseModel):
    """异常数据记录"""
    rule_id: str
    rule_level3_scenario: str
    anomaly_detail: dict = Field(default_factory=dict)
    ai_initial_judgment: str = "uncertain"  # normal/abnormal/uncertain
    ai_judgment_reason: str = ""
    anomaly_score: float = 0.0


class MergedEntityRisk(BaseModel):
    """合并后的主体风险"""
    entity_id: str
    entity_type: str  # employee/supplier/dealer/contact
    anomaly_count: int = 0
    anomaly_records: list[AnomalyRecord] = Field(default_factory=list)
    involved_indicators: list[str] = Field(default_factory=list)


class RiskClassification(BaseModel):
    """风险分类"""
    risk_type: str  # 合规风险/舞弊风险/商业秘密风险/其他
    risk_level: str  # 高/中/低
    severity: str = ""
    scope: str = ""
    impact_assessment: dict = Field(default_factory=dict)
    disposal_suggestion: str = ""
    push_targets: list[str] = Field(default_factory=list)


class RiskAnalysisAgentOutput(BaseModel):
    """风险分析 Agent 输出（向后兼容，内部委托给 3 个独立 Agent）"""
    anomaly_records: list[AnomalyRecord] = Field(default_factory=list)
    anomaly_summary: dict = Field(default_factory=dict)
    anomaly_pivot_table_doc_id: str | None = None
    anomaly_analysis_report_doc_id: str | None = None
    ai_filter_removed_count: int = 0

    merged_entities: list[MergedEntityRisk] = Field(default_factory=list)
    entity_merge_rationale: str = ""
    merged_pivot_table_doc_id: str | None = None
    single_entity_reports: list[dict] = Field(default_factory=list)

    risk_classifications: list[RiskClassification] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


# ═══════════════════════════════════════════════════════════════
# risk-scan-agent — [6.2] SQL执行 + AI初核异常
# ═══════════════════════════════════════════════════════════════

class RiskScanAgentInput(BaseModel):
    """风险扫描 Agent 输入"""
    task_id: str
    execution_mode: RiskExecutionMode = RiskExecutionMode.SCHEDULED

    risk_rules: list[RiskRule] = Field(default_factory=list, description="已审核通过的风险规则清单")
    business_data_sources: list[str] = Field(default_factory=list)
    external_data_sources: list[str] = Field(default_factory=list)

    target_business_units: list[str] = Field(default_factory=list)
    execution_date_range: dict | None = Field(None, description="手动指定日期范围")


class RiskScanAgentOutput(BaseModel):
    """风险扫描 Agent 输出"""
    anomaly_records: list[AnomalyRecord] = Field(default_factory=list)
    anomaly_summary: dict = Field(default_factory=dict)
    ai_filter_removed_count: int = 0
    sql_execution_summary: dict = Field(default_factory=dict)
    sentinel_flags: dict = Field(
        default_factory=lambda: {
            "schema_adaptation_needed": False,
            "deep_analysis_needed": False,
        }
    )
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


# ═══════════════════════════════════════════════════════════════
# risk-merge-agent — [6.3] 主体识别与合并去重
# ═══════════════════════════════════════════════════════════════

class RiskMergeAgentInput(BaseModel):
    """风险合并 Agent 输入"""
    task_id: str
    anomaly_records: list[AnomalyRecord] = Field(default_factory=list, description="AI初核后的异常记录")
    merge_config: dict = Field(
        default_factory=lambda: {
            "contact_match": True,
            "name_fuzzy_match": True,
            "address_match": True,
        }
    )


class RiskMergeAgentOutput(BaseModel):
    """风险合并 Agent 输出"""
    merged_entities: list[MergedEntityRisk] = Field(default_factory=list)
    entity_merge_rationale: str = ""
    merged_pivot_table_doc_id: str | None = None
    single_entity_reports: list[dict] = Field(default_factory=list)
    sentinel_flags: dict = Field(
        default_factory=lambda: {
            "merge_issues_detected": False,
        }
    )
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


# ═══════════════════════════════════════════════════════════════
# risk-classify-agent — [6.4] 风险类型/等级/处置建议判定
# ═══════════════════════════════════════════════════════════════

class RiskClassifyAgentInput(BaseModel):
    """风险定性 Agent 输入"""
    task_id: str
    merged_entities: list[MergedEntityRisk] = Field(default_factory=list, description="合并后的主体风险列表")
    anomaly_summary: dict = Field(default_factory=dict, description="上游扫描汇总（用于上下文）")
    rule_optimization_signal: bool = Field(
        default=False,
        description="来自回流分析的规则优化信号（跨扫描累积）",
    )


class RiskClassifyAgentOutput(BaseModel):
    """风险定性 Agent 输出"""
    risk_classifications: list[RiskClassification] = Field(default_factory=list)
    classification_summary: dict = Field(default_factory=dict)
    sentinel_flags: dict = Field(
        default_factory=lambda: {
            "rule_optimization_needed": False,
            "novel_risk_detected": False,
            "novel_risk_description": "",
        }
    )
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0
