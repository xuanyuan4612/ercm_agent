# 行为风险模块 — Agent 详细设计文档

> **所属系统**：赫尔墨斯（Hermes）风险控制 AI 智能体  
> **模块编号**：07  
> **模块名称**：行为风险（员工行为分析）  
> **依赖文档**：[Agent 架构总则](00-agent-architecture.md) | [系统架构设计](../architecture-design.md) | [模块需求](../modules/07-behavioral-risk.md)  
> **文档版本**：v1.0  
> **最后更新**：2026-06-11

---

## 一、模块 Agent 架构判断

行为风险模块不设置自主主 Agent。模块主控为 `behavioral-risk-graph`，负责分析范围确认、数据拉取、异常分析、HITL、报告归档和向风险监控/离任审计推送事件。

本模块处理员工行为、岗位、账号、通讯方式、涉密文件等敏感数据，Agent 只能在授权范围内做异常解释和报告初稿，不得直接输出处罚、问责或劳动关系处置结论。

---

## 二、Agent 清单

| Agent ID | 名称 | 阶段 | 主要职责 | HITL |
|----------|------|------|----------|------|
| `behavior-data-quality-agent` | 数据质量 Agent | 分析准备 | 检查监管系统覆盖范围、字段完整性、数据缺失和口径冲突 | 是 |
| `behavior-anomaly-agent` | 行为异常识别 Agent | 行为风险分析 | 识别异常行为、关联人员/系统/时间线，生成风险解释 | 是 |
| `behavior-risk-report-agent` | 行为风险报告 Agent | 行为风险分析 | 生成个人/组织维度行为风险分析报告 | 是 |
| `behavior-management-report-agent` | 管理情况报告 Agent | 月度管理报告 | 生成覆盖率、数据质量、高风险行为和优化建议报告 | 是 |

---

## 三、工作流位置

```text
用户选择分析范围 / 周期任务
  ↓
behavior-data-quality-agent
  ↓ HITL 范围和数据缺口确认
behavior-anomaly-agent
  ↓ HITL 异常解释确认
behavior-risk-report-agent
  ↓ HITL 报告确认
Outbox 推送风险监控 / 离任审计

月度任务
  ↓
behavior-management-report-agent
  ↓ HITL 管理报告确认
归档 / 分发
```

---

## 四、Module Agent Profile

```yaml
profile_id: behavioral-risk-agent-profile
module: behavioral_risk
module_graph: behavioral-risk-graph
knowledge_scopes:
  - kb_behavior_policy
  - kb_employee_lifecycle
  - kb_trade_secret_policy
  - kb_law_and_regulation
  - kb_historical_behavior_analysis
allowed_tools:
  - behavior_log_query_readonly
  - hr_profile_read
  - mDM_org_read
  - rag_search
  - evidence_search
  - doc_generate
quality_gates:
  require_data_scope_confirmation: true
  require_privacy_minimization: true
  require_uncertainty: true
  require_human_review: true
```

---

## 五、阶段 Agent 设计

| 阶段 | Agent | 输入 | 输出 | 工具权限 | 质量门禁 |
|------|-------|------|------|----------|----------|
| 分析准备 | `behavior-data-quality-agent` | 分析范围、监管系统清单、员工/组织范围、数据期间 | 数据覆盖报告、缺失字段、口径冲突、是否可分析建议 | 行为日志只读、HR/MDM 只读 | 数据缺失影响结论时必须阻断或人工确认 |
| 异常识别 | `behavior-anomaly-agent` | 行为日志、员工生命周期、岗位职责、涉密信息、历史结果 | 异常清单、风险解释、时间线、关联证据 | 行为日志查询、RAG、证据检索 | 异常必须可解释，不允许只给黑箱分数 |
| 分析报告 | `behavior-risk-report-agent` | 异常清单、证据、风险解释、历史对比 | 行为风险分析报告、推送建议、人工关注点 | 文档生成、RAG | 报告不能直接建议处罚或劳动关系处理 |
| 管理报告 | `behavior-management-report-agent` | 月度分析结果、覆盖率、数据质量、历史趋势 | 行为风险管理情况报告、优化建议 | 统计查询、文档生成 | 统计口径和数据来源必须可追溯 |

---

## 六、输出约束

- 行为风险 Agent 输出的是风险线索和解释，不是员工违规事实认定。
- 任何对个人不利的结论必须进入人工复核。
- 分析上下文必须按最小必要原则注入，不得把全量员工行为明细暴露给无关阶段。
- 向离任审计或风险监控推送只能通过 Outbox 事件，由目标模块 Graph 接收并确认。

