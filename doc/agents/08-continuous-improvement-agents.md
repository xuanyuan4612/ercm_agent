# 持续改善模块 — Agent 详细设计文档

> **所属系统**：赫尔墨斯（Hermes）风险控制 AI 智能体  
> **模块编号**：08  
> **模块名称**：持续改善（整改跟踪）  
> **依赖文档**：[Agent 架构总则](00-agent-architecture.md) | [系统架构设计](../architecture-design.md) | [模块需求](../modules/08-continuous-improvement.md)  
> **文档版本**：v1.0  
> **最后更新**：2026-06-11

---

## 一、模块 Agent 架构判断

持续改善是上游问题清单的统一承接模块，不设置自主决策型主 Agent。模块主控为 `continuous-improvement-graph`，负责问题接收、任务下发、计划审批、证据复核、退回重改、关闭验收和归档。

本模块使用 `continuous-improvement-agent-profile` 约束 Agent 只做整改材料初审、证据充分性判断、催办建议和经验沉淀。问题下发、关闭、作废、归档必须由人工或确定性 workflow 规则确认。

---

## 二、Agent 清单

| Agent ID | 名称 | 阶段 | 主要职责 | HITL |
|----------|------|------|----------|------|
| `improvement-issue-ingest-agent` | 问题录入校验 Agent | 问题待推送 | 校验上游问题字段完整性、重复问题、责任部门和证据引用 | 是 |
| `rectification-plan-review-agent` | 整改计划初审 Agent | 计划待审批 | 初审整改计划是否对准问题、措施是否可执行、时间是否合理 | 是 |
| `rectification-evidence-review-agent` | 整改证据复核 Agent | 已整改待复核 | 初审整改证据真实性、完整性、前后对比和闭环充分性 | 是 |
| `reminder-escalation-agent` | 催办升级建议 Agent | 整改跟踪 | 生成催办话术、升级建议和风险提示 | 可选 |
| `closure-acceptance-agent` | 关闭验收 Agent | 整改完成前 | 汇总计划、证据、复核意见，建议是否允许关闭 | 是 |
| `improvement-knowledge-agent` | 经验沉淀 Agent | 问题归档 | 抽取制度缺陷、流程改进点、相似问题标签和知识库候选条目 | 是 |

---

## 三、工作流位置

```text
上游模块问题清单 / 手工导入
  ↓
improvement-issue-ingest-agent
  ↓ HITL 组长确认下发
rectification-plan-review-agent
  ↓ HITL 审计跟进人审批
整改责任人提交证据
  ↓
rectification-evidence-review-agent
  ↓ HITL 复核通过或退回重改
closure-acceptance-agent
  ↓ HITL 关闭确认
improvement-knowledge-agent
  ↓ HITL 知识沉淀确认
归档
```

---

## 四、Module Agent Profile

```yaml
profile_id: continuous-improvement-agent-profile
module: continuous_improvement
module_graph: continuous-improvement-graph
knowledge_scopes:
  - kb_improvement_case
  - kb_rectification_template
  - kb_audit_issue_history
  - kb_policy_and_process
allowed_tools:
  - issue_deduplicate
  - evidence_search
  - rag_search
  - doc_parse
  - image_compare
  - notification_draft
  - doc_generate
quality_gates:
  require_issue_source: true
  require_rectification_mapping: true
  require_evidence_sufficiency: true
  require_human_review: true
```

---

## 五、阶段 Agent 设计

| 阶段 | Agent | 输入 | 输出 | 工具权限 | 质量门禁 |
|------|-------|------|------|----------|----------|
| 问题录入校验 | `improvement-issue-ingest-agent` | 上游问题清单、附件、责任部门、证据引用 | 字段校验结果、重复问题提示、责任建议、待补充项 | 问题去重、证据检索 | 来源不明或证据缺失必须阻断下发 |
| 整改计划初审 | `rectification-plan-review-agent` | 问题描述、原因分析、整改计划、责任人、完成时间 | 初审意见、风险点、修改建议 | RAG、模板检索 | 措施必须对应问题根因和验收标准 |
| 整改证据复核 | `rectification-evidence-review-agent` | 整改说明、证据文件、前后对比、计划要求 | 证据充分性建议、退回原因、补充材料清单 | 文档解析、OCR、图像对比、证据检索 | 证据不足必须输出退回重改建议 |
| 催办升级建议 | `reminder-escalation-agent` | 逾期状态、责任人、历史催办、风险等级 | 催办文案、升级路径建议 | 通知草稿、历史任务查询 | 不能直接发送高风险升级通知 |
| 关闭验收 | `closure-acceptance-agent` | 问题、计划、证据、复核记录、整改效果 | 是否建议关闭、保留风险、后续跟踪建议 | RAG、证据汇总 | 关闭必须由审计跟进人确认 |
| 经验沉淀 | `improvement-knowledge-agent` | 已闭环问题、根因、整改措施、效果评价 | 知识库候选条目、规则优化建议、相似问题标签 | RAG、知识候选生成 | 入库必须经过业务 owner 审核 |

---

## 六、输出约束

- Agent 不能直接关闭整改问题，不能作废问题，不能自动归档。
- Agent 可以建议退回重改，但退回动作必须由审计复核人确认。
- 催办和升级通知必须由 workflow 根据规则触发，Agent 只生成文案和建议。
- 知识库沉淀必须经过业务 owner 审核后入库。

