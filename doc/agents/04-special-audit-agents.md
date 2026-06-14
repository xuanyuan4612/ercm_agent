# 专项审计模块 — Agent 详细设计文档

> **所属系统**：赫尔墨斯（Hermes）风险控制 AI 智能体  
> **模块编号**：04  
> **模块名称**：专项审计（专项检查）  
> **依赖文档**：[Agent 架构总则](00-agent-architecture.md) | [系统架构设计](../architecture-design.md) | [模块需求](../modules/04-special-audit.md)  
> **文档版本**：v1.0  
> **最后更新**：2026-06-11

---

## 一、模块 Agent 架构判断

专项审计不需要一个自主决策型“模块主 Agent”。生产主控为 `special-audit-graph`，负责 5 阶段流程推进、HITL、退回重跑、问题确认和报告归档。

本模块需要一个 `special-audit-agent-profile`，用于定义专项审计场景下的知识库、工具权限、模板、模型路由和质量门禁。具体 AI 能力由阶段 Agent 执行。

| 项目 | 设计 |
|------|------|
| 模块主控 | `special-audit-graph` |
| Agent 配置入口 | `special-audit-agent-profile` |
| 自主主 Agent | 不设置 |
| 共享 Agent | `audit-plan-agent`、`interview-agent`、`audit-check-agent` |
| 专项 Agent | `special-issue-confirm-agent`、`special-audit-report-agent` |

---

## 二、Agent 清单

| Agent ID | 名称 | 阶段 | 主要职责 | HITL |
|----------|------|------|----------|------|
| `audit-plan-agent` | 审计方案 Agent | 审计方案生成 | 基于审计目的、重点、范围、历史方案生成专项审计方案和抽样建议 | 是 |
| `interview-agent` | 访谈 Agent | 访谈作业 | 生成访谈对象、访谈计划、访谈问卷和访谈摘要 | 是 |
| `audit-check-agent` | 审计检查 Agent | 检查作业 | 生成资料检查计划，分析资料、底稿和数据，形成审计发现草稿 | 是 |
| `special-issue-confirm-agent` | 问题确认 Agent | 问题确认 | 汇总被审计单位反馈，判断问题是否成立、证据是否充分、整改建议是否合理 | 是 |
| `special-audit-report-agent` | 专项审计报告 Agent | 出具报告 | 生成审计报告初稿、整改建议和问题清单摘要 | 是 |

---

## 三、工作流位置

```text
专项审计立项
  ↓
audit-plan-agent
  ↓ HITL 审计方案确认
interview-agent
  ↓ HITL 访谈计划/问卷确认
audit-check-agent
  ↓ HITL 审计发现确认
special-issue-confirm-agent
  ↓ HITL 问题成立性确认
special-audit-report-agent
  ↓ HITL 报告定稿
归档 / 问题汇入持续改善
```

---

## 四、Module Agent Profile

```yaml
profile_id: special-audit-agent-profile
module: special_audit
module_graph: special-audit-graph
knowledge_scopes:
  - kb_special_audit_plan
  - kb_special_audit_history
  - kb_audit_workpaper_template
  - kb_interview_template
  - kb_improvement_suggestion
allowed_tools:
  - rag_search
  - evidence_search
  - interview_plan_generate
  - sql_analyze_readonly
  - doc_generate
  - issue_deduplicate
quality_gates:
  require_citations: true
  require_issue_evidence_mapping: true
  require_human_review: true
```

---

## 五、阶段 Agent 设计

| 阶段 | Agent | 输入 | 输出 | 工具权限 | 质量门禁 |
|------|-------|------|------|----------|----------|
| 审计方案生成 | `audit-plan-agent` | 审计目的、审计重点、被审计单位、期间、项目成员、历史方案 | 专项审计方案、抽样建议、资料需求初稿 | RAG、历史方案检索、抽样计算、文档生成 | 审计范围、重点、程序、样本策略必须完整 |
| 访谈作业 | `interview-agent` | 审计方案、组织架构、岗位职责、访谈问题库 | 访谈名单、访谈计划、问卷、访谈纪要摘要 | 组织架构检索、问卷生成、ASR 结果查询 | 访谈对象与审计重点必须可解释 |
| 检查作业 | `audit-check-agent` | 审计方案、资料清单、业务数据、上传资料、访谈结论 | 审计底稿、检查记录、问题草稿、证据引用 | 只读 SQL、证据检索、OCR/文档解析结果查询 | 每个问题必须绑定证据和判断依据 |
| 问题确认 | `special-issue-confirm-agent` | 问题草稿、被审计单位反馈、补充证据、制度依据 | 问题成立性建议、调整建议、待补充材料 | 证据检索、制度检索、问题去重 | 不充分证据必须标记为待补充 |
| 出具审计报告 | `special-audit-report-agent` | 已确认问题、整改建议、审计底稿、项目资料 | 报告初稿、问题清单、整改建议 | 文档生成、RAG、模板填充 | 报告结论不得超出已确认问题范围 |

---

## 六、输出约束

- Agent 可以生成审计建议和报告初稿，但不能直接认定最终审计结论。
- 问题成立、问题关闭、问题下发整改必须经过审计人员 HITL。
- SQL 工具只允许只读查询，不允许 DDL/DML。
- 问题清单推送持续改善必须由 `special-audit-graph` 写 Outbox 事件。

