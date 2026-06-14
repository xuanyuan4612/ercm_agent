# 商业秘密模块 — Agent 详细设计文档

> **所属系统**：赫尔墨斯（Hermes）风险控制 AI 智能体  
> **模块编号**：06  
> **模块名称**：商业秘密保护（保密管理）  
> **依赖文档**：[Agent 架构总则](00-agent-architecture.md) | [系统架构设计](../architecture-design.md) | [模块需求](../modules/06-trade-secrets.md)  
> **文档版本**：v1.0  
> **最后更新**：2026-06-11

---

## 一、模块 Agent 架构判断

商业秘密模块不设置自主主 Agent。模块主控为 `trade-secrets-graph`，负责定密预审、正式评审、管理报告、HITL 和风控系统回写。

本模块使用 `trade-secrets-agent-profile` 控制定密知识库、外部法规案例、制度文件、行为风险结果和工具权限。定密结论属于高风险合规判断，Agent 只能给出建议和依据，最终密级、范围、变更和下架必须由人工评审确认。

---

## 二、Agent 清单

| Agent ID | 名称 | 阶段 | 主要职责 | HITL |
|----------|------|------|----------|------|
| `secret-precheck-agent` | 定密预审 Agent | 保密员定密建议/预审 | 检查定密材料完整性，生成预审建议和补充项 | 是 |
| `secret-policy-compare-agent` | 制度比对 Agent | 预审/评审共用 | 比对内部制度、保密规则、知识产权制度和历史定密口径 | 是 |
| `secret-review-agent` | 定密评审 Agent | 定密信息评审 | 综合法规、案例、制度、历史评审，生成评审建议 | 是 |
| `secret-management-report-agent` | 管理报告 Agent | 月度/周期报告 | 生成商业秘密管理情况报告、统计分析和风险提示 | 是 |

---

## 三、工作流位置

```text
定密申请 / 风控系统按钮
  ↓
secret-precheck-agent
  ↓ HITL 保密员确认或补充
secret-policy-compare-agent
  ↓
secret-review-agent
  ↓ HITL 评审小组确认密级、范围、期限
风控系统回写 / 归档

周期任务
  ↓
secret-management-report-agent
  ↓ HITL 管理报告确认
归档 / 分发
```

---

## 四、Module Agent Profile

```yaml
profile_id: trade-secrets-agent-profile
module: trade_secrets
module_graph: trade-secrets-graph
knowledge_scopes:
  - kb_trade_secret_policy
  - kb_ip_policy
  - kb_trade_secret_law
  - kb_trade_secret_cases
  - kb_historical_secret_review
  - kb_internal_control_policy
allowed_tools:
  - rag_search
  - policy_compare
  - historical_review_search
  - behavior_risk_summary_read
  - doc_generate
  - sensitivity_classifier
quality_gates:
  require_policy_basis: true
  require_legal_case_reference: true
  require_uncertainty: true
  require_human_review: true
```

---

## 五、阶段 Agent 设计

| 阶段 | Agent | 输入 | 输出 | 工具权限 | 质量门禁 |
|------|-------|------|------|----------|----------|
| 定密预审 | `secret-precheck-agent` | 定密信息表、项目/部门信息、涉密材料、历史定密记录 | 预审报告、材料缺失项、建议密级和依据 | RAG、历史评审检索、敏感分类 | 建议密级必须给出制度或案例依据 |
| 制度比对 | `secret-policy-compare-agent` | 定密材料、制度文件、内控评价制度库 | 合规性比对结果、冲突项、待人工确认项 | 制度检索、条款比对 | 制度冲突不得自动裁决 |
| 定密评审 | `secret-review-agent` | 预审报告、制度比对、法规案例、横向对比、行为风险结果 | 评审建议、密级/范围/期限建议、风险说明 | 法规案例检索、RAG、行为风险摘要只读 | 最终密级必须由评审小组确认 |
| 管理报告 | `secret-management-report-agent` | 定密台账、历史评审、变更记录、部门统计 | 管理报告初稿、风险趋势、待整改建议 | 统计查询、文档生成 | 报告统计口径必须可追溯 |

---

## 六、输出约束

- Agent 不能最终确认密级，不能直接修改风控系统商业秘密台账。
- 涉密文件只能通过短期预签名 URL 访问，Agent 输入应使用脱敏摘要和引用 ID。
- 外部法规和案例不可用时，必须标记“外部依据不足”。
- 行为风险结果只能作为辅助风险线索，不能作为定密唯一依据。

