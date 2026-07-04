# Hermes Agent 架构总则

> **所属系统**：赫尔墨斯（Hermes）风险控制 AI 智能体  
> **适用范围**：8 个业务模块全部 Agent 设计文档  
> **依赖文档**：[系统架构设计](../architecture-design.md)  
> **文档版本**：v1.0  
> **最后更新**：2026-06-28

---

## 一、核心结论

Hermes 不采用“每个模块一个自主决策型主 Agent”的架构。每个模块需要的是：

1. **一个 Module Graph**：模块内确定性流程主控，负责阶段推进、HITL、恢复、重试、事件触发和归档。
2. **一个 Module Agent Profile**：模块级 AI 能力配置，定义 Prompt 包、知识范围、Skill 权限、工具权限、输出 schema、模型路由和质量门禁。
3. **多个 Agent Skill**：把业务任务封装为可授权、可观测、可降级的能力包，内部编排 Prompt、上下文、工具链、校验规则、HITL 要求和降级策略。
4. **多个 Stage Agent**：每个关键业务阶段一个或多个 Agent，负责选择并执行授权 Skill，生成结构化建议、证据摘要、报告初稿、风险判断和人工关注点。

生产上的主控权属于 `LangGraph Workflow Runtime`，不是 Agent。Agent 只在 workflow 指定阶段内执行授权任务，不直接修改业务终态，不直接跳转阶段，不绕过人工守门。

---

## 二、落地架构

```text
API / 业务应用层
  ↓ 创建业务命令或 workflow 实例
Module Graph
  ↓ 根据状态机进入阶段节点
Agent Runtime
  ↓ 加载 Module Agent Profile
Stage Agent
  ↓ 选择并执行授权 Agent Skill
Agent Skill
  ↓ 编排 Prompt / Context / RAG / Text2SQL / Tool / Model Gateway
结构化 stage_output
  ↓
LangGraph interrupt / HITL
  ↓ 人工审批、修改、驳回或恢复
Module Graph 继续推进
```

| 架构元素 | 是否使用 LLM | 生产职责 | 不允许做的事 |
|----------|--------------|----------|--------------|
| **Module Graph** | 否，主要是确定性逻辑 | 模块流程主控、状态推进、条件路由、HITL、checkpoint、resume | 不生成自由文本业务结论 |
| **Module Agent Profile** | 否，配置对象 | 绑定模块知识范围、Skill 权限、工具权限、Prompt 包、模型路由和输出 schema | 不自行决策案件状态 |
| **Agent Runtime** | 否，服务层 | 装配上下文、调用模型、校验 schema、记录 trace、处理重试和降级 | 不承载业务阶段语义 |
| **Stage Agent** | 是 | 在单一阶段内选择授权 Skill，生成结构化建议和证据引用 | 不直接执行处罚、扣款、移交、外部写入 |
| **Agent Skill** | 视能力而定 | 封装业务能力、工具链、上下文装配、返回校验、降级和 HITL 规则 | 不绕过 Profile 授权，不直接推进 workflow 阶段 |
| **Shared Tool/Agent** | 视能力而定 | OCR、ASR、RAG、Text2SQL、报告生成、审计方案、访谈、检查等复用能力 | 不越权访问其它模块数据 |

---

## 三、Module Agent Profile 规范

每个模块必须维护一个 Profile，但 Profile 不是主 Agent。它是 Agent Runtime 的配置入口。

```yaml
module: integrity_supervision
module_graph: integrity-supervision-graph
profile_id: integrity-supervision-agent-profile
schema_version: "1.0"
knowledge_scopes:
  - kb_integrity_policy
  - kb_integrity_cases
  - kb_law_and_regulation
allowed_skills:
  - integrity-intake-triage-skill
  - integrity-evidence-profiling-skill
  - integrity-investigation-plan-skill
  - integrity-multi-source-analysis-skill
  - integrity-disposition-reasoning-skill
  - integrity-enforcement-coordination-skill
allowed_tools:
  - rag_search
  - evidence_search
  - doc_generate
  - a2a_send
  - text2sql_generate
  - text2sql_validate
  - text2sql_execute_readonly
model_routing_policy:
  primary: deepseek-provider
  fallback: qwen-provider
  sensitive_fallback: private-model-provider
quality_gates:
  require_citations: true
  require_confidence: true
  require_uncertainties: true
  human_review_required: true
```

Profile 的生产要求：

- 知识库 scope 必须按模块、租户、密级和阶段隔离。
- Skill 权限必须按模块、阶段和角色授权，Stage Agent 默认只能调用当前阶段必要 Skill。
- Tool 权限必须按 Skill、角色、模块、阶段授权，默认最小权限；Stage Agent 不应绕过 Skill 直接拼接工具链。
- 高风险 Tool 只能由授权 Skill 生成建议或 Outbox 事件，不允许 Agent 直接执行外部系统写入。
- 模型调用必须经过 Model Gateway，不能在 Agent 代码或 Prompt 中硬编码模型版本。
- 检索必须经过 RAG Orchestrator，默认使用 Elasticsearch/OpenSearch + Milvus + metadata filter + rerank。

### 3.1 Agent Skill 规范

Agent Skill 是介于 Stage Agent 和 Tool 之间的业务能力层。它不是独立主控 Agent，也不拥有 workflow 阶段推进权；它负责把一个可复用业务任务封装成稳定契约。

每个 Skill 必须定义：

| 字段 | 说明 |
|------|------|
| `skill_id` | 全局唯一 ID，推荐格式：`{module}-{capability}-skill` |
| `owner_module` | 所属模块；跨模块复用时标记为 `shared` 并声明租户隔离规则 |
| `used_by_agents` | 可调用该 Skill 的 Stage Agent 列表 |
| `input_schema` / `output_schema` | 结构化输入输出契约，必须可 Pydantic 校验 |
| `prompt_refs` | 使用的 System Prompt、few-shot 和模板版本 |
| `context_policy` | 上下文装配规则、token 预算、记忆层和证据引用策略 |
| `tool_chain` | 内部可调用 Tool、执行顺序、并行/串行关系、超时、重试和熔断 |
| `quality_gates` | 引用完整性、证据链、置信度、法条校验、输出格式等质量门禁 |
| `hitl_policy` | 是否需要人工审批、双签、驳回重跑、修改后采纳 |
| `fallback_policy` | 检索为空、LLM 不可用、Tool 失败、输出不合规时的降级行为 |
| `observability` | `skill_run_id`、trace、指标、审计字段和成本归集 |

Skill 和 Tool 的边界：

| 层级 | 粒度 | 例子 | 主要约束 |
|------|------|------|----------|
| Tool | 原子接口 | `kb_search`、`text2sql_execute_readonly`、`doc_generate`、`a2a_send` | 只做单一系统能力，受权限、租户和 PII 策略控制 |
| Skill | 业务能力包 | `integrity-multi-source-analysis-skill`、`audit-interview-skill` | 编排多个 Tool 和 Prompt，输出结构化业务结果，必须记录 `skill_runs` |
| Stage Agent | 阶段执行者 | `analysis-agent`、`disposition-agent` | 只能调用 Profile 授权 Skill，并把结果交给 HITL / Workflow |

---

## 四、Stage Agent 统一输入输出契约

### 4.1 输入契约

```json
{
  "case_id": "uuid",
  "module": "integrity_supervision",
  "stage": "investigation_plan",
  "workflow_thread_id": "wf-thread-id",
  "workflow_state_version": 12,
  "business_context": {},
  "human_modified_context": {},
  "evidence_refs": [],
  "knowledge_scope": [],
  "allowed_skills": [],
  "allowed_tools": [],
  "tenant_scope": {
    "client": "group|ecovacs|tineco",
    "org_ids": []
  },
  "schema_version": "1.0",
  "trace_id": "otel-trace-id"
}
```

### 4.2 输出契约

```json
{
  "stage_output": {},
  "conclusion": "",
  "risk_level": "low|medium|high|critical|unknown",
  "confidence": 0.82,
  "evidence_refs": [],
  "knowledge_refs": [],
  "uncertainties": [],
  "recommended_actions": [],
  "human_review_required": true,
  "skill_runs": [],
  "tool_calls": [],
  "model_usage": {
    "provider": "",
    "model": "",
    "prompt_version": "",
    "tokens": 0,
    "latency_ms": 0
  }
}
```

所有 Stage Agent 输出都必须可结构化校验。自由文本只能作为报告正文或说明字段，不能作为下游状态判断的唯一依据。

---

## 五、8 个模块 Agent 设计总览

| 模块 | 模块主控 | 是否需要自主主 Agent | Module Agent Profile | Stage Agent 设计 |
|------|----------|----------------------|----------------------|------------------|
| 廉洁监察 | `integrity-supervision-graph` | 不需要 | `integrity-supervision-agent-profile` | 初筛、调查方案、分析报告、处置分流、处罚执行、报案协助 |
| 风险监控 | `risk-monitoring-graph` | 不需要 | `risk-monitoring-agent-profile` | 风险规则、异常初核、主体合并、风险定性、误报分析 |
| 内控评价 | `internal-control-evaluation-graph` | 不需要 | `internal-control-evaluation-agent-profile` | 审计方案、访谈、风控矩阵、设计缺陷、执行缺陷、评分、报告 |
| 专项审计 | `special-audit-graph` | 不需要 | `special-audit-agent-profile` | 审计方案、访谈作业、检查作业、问题确认、报告 |
| 离任审计 | `exit-audit-graph` | 不需要 | `exit-audit-agent-profile` | 离任方案、访谈问卷、资料清单、问题清单、问题确认、报告 |
| 商业秘密 | `trade-secrets-graph` | 不需要 | `trade-secrets-agent-profile` | 定密预审、制度比对、定密评审、管理报告 |
| 行为风险 | `behavioral-risk-graph` | 不需要 | `behavioral-risk-agent-profile` | 数据质量、异常识别、风险解释、分析报告、管理报告 |
| 持续改善 | `continuous-improvement-graph` | 不需要 | `continuous-improvement-agent-profile` | 问题录入校验、计划初审、证据复核、催办建议、关闭验收、经验沉淀 |

---

## 六、共享 Agent 复用规则

| 共享能力 | 权威设计文档 | 使用模块 | 复用方式 |
|----------|--------------|----------|----------|
| 审计方案 Agent | [03-internal-control-evaluation-agents.md](03-internal-control-evaluation-agents.md) | 内控评价、专项审计、离任审计 | 通过 `audit_type` 和 Profile 参数区分模板、知识库和输出结构 |
| 审计检查 Agent | [03-internal-control-evaluation-agents.md](03-internal-control-evaluation-agents.md) | 内控评价、专项审计、离任审计 | 共享检查逻辑，按模块配置检查目标和证据类型 |
| 访谈 Agent | [03-internal-control-evaluation-agents.md](03-internal-control-evaluation-agents.md) | 廉洁监察、内控评价、专项审计、离任审计 | 共享人员匹配、问卷生成、纪要摘要能力 |
| RAG Orchestrator | 系统架构设计 | 全部模块 | 统一检索、过滤、重排、引用追溯 |
| Text2SQL Orchestrator | [11-text2sql-shared-agent.md](11-text2sql-shared-agent.md) | 全部模块 | 统一自然语言数仓查询、Doris SQL 生成、AST 安全校验、HITL 门禁、只读执行和数据引用 |
| Agent Skill Library | 本文档 + 各模块 Agent 设计文档 | 全部模块 | 统一登记 `skill_id`、输入输出 schema、内部工具链、HITL 与降级策略 |
| 文档生成 Tool | 系统架构设计 | 全部模块 | 通过模板 ID 和输出 schema 生成 Word/Excel/PDF |
| A2A Adapter | 系统架构设计 | 廉洁监察、风险监控、商业秘密、行为风险、持续改善 | 外部任务统一走 Outbox/Inbox、签名、幂等和回调确认 |

---

## 七、设计约束

- **不得新增万能主 Agent**：跨阶段流程、状态跳转和失败恢复只能由 Module Graph 管理。
- **不得让 Agent 拥有全模块 Skill/工具权限**：每个 Stage Agent 只拿当前阶段必要 Skill；Tool 权限收敛到 Skill 内部。
- **不得绕过 Skill 直接拼工具链**：除健康检查、schema 校验等平台能力外，业务任务应优先由授权 Skill 承载。
- **不得让 Agent 输出直接成为业务终态**：必须经过 schema 校验、规则校验和人工守门。
- **不得由 Worker 推进业务阶段**：Worker 只写任务结果和完成事件，由 Workflow Runtime resume。
- **不得在 Prompt 中隐藏审批规则**：审批、驳回、重跑、转交、关闭必须是显式 workflow 规则。
- **不得编造知识依据**：检索不足时输出 `knowledge_insufficient`，进入人工接管或补充材料。

---

## 八、生产验收场景

| 场景 | 验收要求 |
|------|----------|
| 模块 Profile 生效 | 同一 Stage Agent 在不同模块下使用不同知识范围、工具权限和输出 schema |
| Skill 授权生效 | Stage Agent 调用未授权 Skill 时被 Agent Runtime 拒绝并记录审计 |
| 人工修改传递 | HITL 修改后的 stage_output 必须覆盖原始 AI 输出并进入下游 Agent 输入 |
| 工具越权拦截 | Stage Agent 调用未授权 Tool 时被 Agent Runtime 拒绝并记录审计 |
| Skill 可观测 | 每次 Skill 执行都有 `skill_run_id`、输入摘要、输出摘要、内部 Tool 调用、耗时、成本和降级原因 |
| 检索不可用 | Search 或 Milvus 不可用时 Agent 输出知识不足，不得编造结论 |
| 模型切换 | 主 provider 不可用时由 Model Gateway 熔断并切换备用 provider |
| 幂等重试 | 同一 `case_id + stage + idempotency_key` 重试不会产生重复报告或重复外发任务 |
| trace 贯穿 | API、Workflow、Agent、Tool、LLM、RAG、Text2SQL、Worker、外部回调能通过同一 trace_id 串联 |
