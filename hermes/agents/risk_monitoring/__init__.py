"""
风险监控 (Risk Monitoring) 模块 Agent

Agent: risk-rule-agent, risk-scan-agent, risk-merge-agent, risk-classify-agent

架构: 确定性 Pipeline + 智能异常处理层（哨兵机制）
  - risk-rule-agent      → [6.1] 规则生成 + SQL校验
  - risk-scan-agent      → [6.2] SQL执行 + AI初核异常
  - risk-merge-agent     → [6.3] 主体识别与合并去重
  - risk-classify-agent  → [6.4] 风险类型/等级/处置建议判定

risk-analysis-agent 保留为向后兼容的外观类，内部委托给上述 3 个 Agent。

参照:
  - doc/agents/02-risk-monitoring-agents.md (详细设计)
  - doc/agents/02b-risk-monitoring-architecture-analysis.md (架构分析)
"""

from hermes.agents.risk_monitoring.risk_analysis_agent import RiskAnalysisAgent
from hermes.agents.risk_monitoring.risk_classify_agent import RiskClassifyAgent
from hermes.agents.risk_monitoring.risk_merge_agent import RiskMergeAgent
from hermes.agents.risk_monitoring.risk_rule_agent import RiskRuleAgent
from hermes.agents.risk_monitoring.risk_scan_agent import RiskScanAgent

__all__ = [
    "RiskRuleAgent",
    "RiskScanAgent",
    "RiskMergeAgent",
    "RiskClassifyAgent",
    "RiskAnalysisAgent",  # 向后兼容
]
