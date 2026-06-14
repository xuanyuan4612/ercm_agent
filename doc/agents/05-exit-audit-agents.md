# 离任审计模块 — Agent 详细设计文档

> **所属系统**：赫尔墨斯（Hermes）风险控制 AI 智能体  
> **模块编号**：05  
> **模块名称**：离任审计（离职审查）  
> **依赖文档**：[Agent 架构总则](00-agent-architecture.md) | [系统架构设计](../architecture-design.md) | [模块需求](../modules/05-exit-audit.md)  
> **文档版本**：v1.0  
> **最后更新**：2026-06-11

---

## 一、模块 Agent 架构判断

离任审计不设置自主决策型模块主 Agent。模块主控为 `exit-audit-graph`，负责离任审计期间计算、阶段推进、HITL、问题分流、报告定稿和归档。

本模块使用 `exit-audit-agent-profile` 作为 AI 能力入口。审计方案、访谈和检查能力复用内控评价中的共享 Agent，并通过 `audit_type=exit_audit` 注入离任审计差异化参数。

---

## 二、Agent 清单

| Agent ID | 名称 | 阶段 | 主要职责 | HITL |
|----------|------|------|----------|------|
| `audit-plan-agent` | 离任审计方案 Agent | 审计方案生成 | 根据被审计人岗位职责、任职期间、风险预警生成离任审计方案 | 是 |
| `interview-agent` | 访谈问卷 Agent | 访谈问卷 | 生成被审计人、上级、下属、协同部门访谈问卷 | 是 |
| `exit-material-agent` | 资料清单 Agent | 资料清单 | 生成资料需求清单，标记系统取数和人工上传责任 | 是 |
| `exit-issue-agent` | 问题清单 Agent | 问题清单生成 | 识别个人问题和业务问题，形成问题草稿和证据链 | 是 |
| `exit-issue-confirm-agent` | 问题确认 Agent | 问题确认 | 汇总反馈并判断问题成立性、责任归属和整改方向 | 是 |
| `exit-report-agent` | 离任审计报告 Agent | 出具报告 | 生成离任审计报告初稿和问题汇总 | 是 |

---

## 三、工作流位置

```text
离任审计立项 / OA-BPM 同步
  ↓
audit-plan-agent
  ↓ HITL 审计方案确认
interview-agent
  ↓ HITL 问卷确认
exit-material-agent
  ↓ HITL 资料清单确认
exit-issue-agent
  ↓ HITL 问题清单初审
exit-issue-confirm-agent
  ↓ HITL 问题确认
exit-report-agent
  ↓ HITL 报告定稿
归档 / 问题汇入持续改善
```

---

## 四、Module Agent Profile

```yaml
profile_id: exit-audit-agent-profile
module: exit_audit
module_graph: exit-audit-graph
knowledge_scopes:
  - kb_exit_audit_plan
  - kb_position_duty
  - kb_personal_risk_case
  - kb_business_audit_case
  - kb_behavioral_risk_history
allowed_tools:
  - rag_search
  - hr_profile_read
  - behavior_risk_summary_read
  - finance_voucher_readonly
  - evidence_search
  - doc_generate
quality_gates:
  require_tenure_rule_check: true
  require_issue_category: personal_or_business
  require_citations: true
  require_human_review: true
```

---

## 五、阶段 Agent 设计

| 阶段 | Agent | 输入 | 输出 | 工具权限 | 质量门禁 |
|------|-------|------|------|----------|----------|
| 审计方案生成 | `audit-plan-agent` | 被审计人信息、岗位职责、任职期间、离任原因、历史风险、行为风险预警 | 离任审计方案、审计期间、重点检查事项 | HR 只读、RAG、岗位职责匹配 | 审计期间必须符合任职年限规则 |
| 访谈问卷 | `interview-agent` | 审计方案、岗位职责、组织关系、风险点 | 分角色问卷、访谈对象建议 | 组织架构检索、问卷模板 | 问卷问题必须映射到审计重点 |
| 资料清单 | `exit-material-agent` | 审计方案、职责范围、系统清单、风险预警 | 资料需求清单、取数系统、责任人、截止时间 | 系统元数据、模板生成 | 缺失系统必须标记人工补充 |
| 问题清单生成 | `exit-issue-agent` | 资料、访谈纪要、报销凭证、行为风险结果、业务数据 | 个人问题清单、业务问题清单、证据摘要 | 只读 SQL、证据检索、OCR | 问题必须分类为个人/业务/待确认 |
| 问题确认 | `exit-issue-confirm-agent` | 问题草稿、反馈、补充证据 | 成立性建议、责任边界、整改建议 | RAG、证据检索 | 责任归属不清时必须输出不确定点 |
| 出具报告 | `exit-report-agent` | 确认问题、审计方案、底稿、整改建议 | 离任审计报告初稿 | 文档生成、模板填充 | 报告不得包含未经确认的问题结论 |

---

## 六、输出约束

- Agent 不得直接形成离任结论、处罚建议或外部通报。
- 涉及个人信息和行为数据时必须按最小必要原则注入上下文。
- 行为风险结果只能作为审计线索和证据参考，不能单独作为问题成立依据。
- 所有问题下发持续改善必须由 `exit-audit-graph` 触发 Outbox。

