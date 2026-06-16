"""
风险监控模块 — Agent 输入/输出 Schemas

Agent: risk-rule-agent, risk-analysis-agent

参照: doc/agents/02-risk-monitoring-agents.md
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from hermes.schemas.agents.common import Confidence


class RuleGenerationMode(str, Enum):
    BATCH_UPLOAD = "batch_upload"
    MANUAL_INPUT = "manual_input"


class RiskRuleAgentInput(BaseModel):
    """风险规则 Agent 输入"""
    task_id: str
    mode: RuleGenerationMode

    uploaded_rules: Optional[List[dict]] = Field(None, description="已上传的风险场景清单")
    manual_scenario: Optional[str] = Field(None, description="人工自定义场景描述")
    target_business_cycle: Optional[str] = Field(None, description="目标业务循环")
    target_department: Optional[str] = Field(None, description="目标部门/事业部")

    db_schema_context: dict = Field(default_factory=dict, description="数据库字段及含义")
    historical_cases: List[dict] = Field(default_factory=list, description="历史案例参考")


class RiskRule(BaseModel):
    """单条风险规则"""
    business_unit: str
    channel: Optional[str] = None
    business_format: Optional[str] = None
    business_cycle: str
    department: str
    position: Optional[str] = None
    personnel_info: Optional[str] = None
    level1_scenario: str
    level2_scenario: str
    level3_scenario: str
    sql_statement: str
    risk_level: str = "中"
    threshold: Optional[str] = None
    monitor_frequency: str = "daily"
    monitor_business_unit: str
    use_external_data: bool = False


class RiskRuleAgentOutput(BaseModel):
    """风险规则 Agent 输出"""
    rules: List[RiskRule]
    sql_validation_results: List[dict] = Field(default_factory=list)
    generation_rationale: str = ""
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0


class RiskExecutionMode(str, Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class RiskAnalysisAgentInput(BaseModel):
    """风险分析 Agent 输入"""
    task_id: str
    execution_mode: RiskExecutionMode = RiskExecutionMode.SCHEDULED

    risk_rules: List[RiskRule] = Field(default_factory=list, description="已审核通过的风险规则清单")
    business_data_sources: List[str] = Field(default_factory=list)
    external_data_sources: List[str] = Field(default_factory=list)

    target_business_units: List[str] = Field(default_factory=list)
    execution_date_range: Optional[dict] = Field(None, description="手动指定日期范围")


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
    anomaly_records: List[AnomalyRecord] = Field(default_factory=list)
    involved_indicators: List[str] = Field(default_factory=list)


class RiskClassification(BaseModel):
    """风险分类"""
    risk_type: str  # 合规风险/舞弊风险/商业秘密风险/其他
    risk_level: str  # 高/中/低
    severity: str = ""
    scope: str = ""
    impact_assessment: dict = Field(default_factory=dict)
    disposal_suggestion: str = ""
    push_targets: List[str] = Field(default_factory=list)


class RiskAnalysisAgentOutput(BaseModel):
    """风险分析 Agent 输出"""
    anomaly_records: List[AnomalyRecord] = Field(default_factory=list)
    anomaly_summary: dict = Field(default_factory=dict)
    anomaly_pivot_table_doc_id: Optional[str] = None
    anomaly_analysis_report_doc_id: Optional[str] = None
    ai_filter_removed_count: int = 0

    merged_entities: List[MergedEntityRisk] = Field(default_factory=list)
    entity_merge_rationale: str = ""
    merged_pivot_table_doc_id: Optional[str] = None
    single_entity_reports: List[dict] = Field(default_factory=list)

    risk_classifications: List[RiskClassification] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    processing_time_ms: int = 0
