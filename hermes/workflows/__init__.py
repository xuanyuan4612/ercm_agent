"""
Hermes LangGraph Workflows

每个模块有独立的 LangGraph StateGraph 定义和 WorkflowManager。

模块主控是 Module Graph，不是 Agent。Graph 负责：
- 阶段路由
- HITL (interrupt/resume)
- 重试、恢复
- 人工接管
- 下游事件触发

8 个模块:
  integrity/              — 01 廉洁监察 (已实现)
  risk_monitoring/        — 02 风险监控
  ic_evaluation/          — 03 内控评价
  special_audit/          — 04 专项审计
  exit_audit/             — 05 离任审计
  trade_secrets/          — 06 商业秘密
  behavioral_risk/        — 07 行为风险
  continuous_improvement/ — 08 持续改善
"""
