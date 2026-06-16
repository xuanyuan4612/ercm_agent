"""
内控评价 (Internal Control Evaluation) 模块 Agent

包含 3 个跨模块共享 Agent:
  audit-plan-agent  — 审计方案 Agent ⭐ (内控评价 + 专项审计 + 离任审计)
  audit-check-agent — 审计检查 Agent ⭐ (内控评价 + 专项审计 + 离任审计)
  interview-agent   — 访谈 Agent ⭐ (内控评价 + 专项审计 + 离任审计 + 廉洁监察)

⭐ = 跨模块共享，本文档为权威设计来源
"""
