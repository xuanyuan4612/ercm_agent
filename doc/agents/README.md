# Hermes Agent 详细设计文档索引

> 本目录保存各业务模块的 Agent 详细设计。Agent 设计以 [00-agent-architecture.md](00-agent-architecture.md) 为统一生产约束：模块主控是 Module Graph，不是自主决策型主 Agent；每个模块通过 Module Agent Profile 管理知识范围、工具权限、Prompt、模型路由和输出 schema。

## 文档索引

| 模块 | 文档 | 说明 |
|------|------|------|
| 通用 | [00-agent-architecture.md](00-agent-architecture.md) | Agent 架构总则、Module Graph/Profile/Stage Agent 边界、统一输入输出契约 |
| 01 廉洁监察 | [01-integrity-supervision-agents.md](01-integrity-supervision-agents.md) | 初筛、调查方案、分析报告、处置分流、处罚执行、报案协助 |
| 02 风险监控 | [02-risk-monitoring-agents.md](02-risk-monitoring-agents.md) | 风险规则、异常初核、主体合并、风险定性、误报回流 |
| 03 内控评价 | [03-internal-control-evaluation-agents.md](03-internal-control-evaluation-agents.md) | 审计方案、访谈、审计检查等共享 Agent 权威设计 |
| 04 专项审计 | [04-special-audit-agents.md](04-special-audit-agents.md) | 方案、访谈、检查、问题确认、报告 |
| 05 离任审计 | [05-exit-audit-agents.md](05-exit-audit-agents.md) | 离任方案、访谈问卷、资料清单、问题清单、报告 |
| 06 商业秘密 | [06-trade-secrets-agents.md](06-trade-secrets-agents.md) | 定密预审、制度比对、定密评审、管理报告 |
| 07 行为风险 | [07-behavioral-risk-agents.md](07-behavioral-risk-agents.md) | 数据质量、异常识别、风险报告、管理报告 |
| 08 持续改善 | [08-continuous-improvement-agents.md](08-continuous-improvement-agents.md) | 问题录入、计划初审、证据复核、关闭验收、经验沉淀 |

## 统一落地原则

- 每个模块必须有 `Module Graph`，作为流程和状态主控。
- 每个模块可以有 `Module Agent Profile`，作为 Agent Runtime 的配置入口。
- 每个关键阶段使用 `Stage Agent`，输出结构化建议和证据引用。
- 不设置拥有自主状态跳转权的“模块主 Agent”。
- 高风险动作必须经过 HITL 和 Workflow Runtime 裁决。

