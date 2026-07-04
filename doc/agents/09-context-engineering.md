# Hermes 上下文工程架构设计文档

> **所属系统**：赫尔墨斯（Hermes）风险控制 AI 智能体  
> **设计范围**：Agent Runtime、Context Builder、Module Agent Profile、Stage Agent 输入装配、上下文快照、审计回放  
> **依赖文档**：[Agent 架构总则](00-agent-architecture.md) | [系统架构设计](../architecture-design.md)  
> **文档版本**：v1.2  
> **最后更新**：2026-07-03

---

## 一、设计结论

Hermes 的上下文工程不是 Prompt 拼接，也不是给所有 Agent 建一个共享 Memory 池。真实生产环境中，上下文工程要解决的是：

```text
在每次 Stage Agent 执行前，
系统如何确定性地装配“当前 Agent 在当前阶段、当前权限、当前版本下应该看到什么”，
并保证这份上下文可裁剪、可追溯、可审计、可回放、可降级。
```

最终设计结论：

| 设计问题 | 生产口径 |
|----------|----------|
| Agent 是否共享上下文 | 需要共享，但只能共享结构化、授权、版本化后的上下文 |
| 是否做全局共享 Memory | 不做。全局 Memory 会导致越权、污染、不可审计和 token 失控 |
| 谁负责装配上下文 | `Context Builder`，属于 Agent Runtime 的确定性组件 |
| Agent 是否能自己读取全量上下文 | 不能。Agent 只消费 `Context Envelope` |
| 上下文权威来源 | Workflow checkpoint、PostgreSQL 业务事实、approval 定稿版本、evidence/knowledge 引用 |
| 下游 Agent 使用哪个版本 | 默认只使用人工确认后的 `approved_version` |
| 大文件/长文本怎么处理 | 共享引用和摘要，按需通过 Tool 读取授权片段 |
| 每次调用如何审计 | 生成 `context_snapshot_id`，记录本次 Agent 实际看到的上下文引用和版本 |

核心原则：

```text
让 Agent 在正确的阶段、看到正确版本、正确权限、正确粒度的上下文。
```

---

## 二、架构位置

上下文工程不单独形成新的系统分层，它位于 **Agent 与模型能力层** 内部，是 Agent Runtime 的核心能力。

```text
Agent Runtime
  ├── Context Builder              # 上下文装配核心
  ├── Context Policy Resolver      # 解析 Module Agent Profile + Stage 规则
  ├── Context Retriever            # 读取业务事实、阶段产物、证据、知识引用
  ├── Context Redactor             # 脱敏、密级控制、字段裁剪
  ├── Context Compressor           # 摘要压缩、token budget 控制
  ├── Prompt Manager               # Prompt 模板与版本
  ├── Tool Registry                # 工具授权与调用边界
  ├── Model Gateway Client         # 模型路由、熔断、灰度
  ├── Output Schema Validator      # 输出结构校验
  └── Agent Run Logger             # trace、成本、质量、审计记录
```

### 2.1 与 Workflow Runtime 的关系

`Workflow Runtime` 决定什么时候进入某个阶段、是否暂停、是否恢复、是否重跑。  
`Context Builder` 只负责在这个阶段执行前装配上下文，不决定流程状态。

```text
Workflow Runtime = 流程秩序
Context Builder = 输入装配
Stage Agent = 阶段分析
```

### 2.2 与 Module Agent Profile 的关系

每个模块的 `Module Agent Profile` 必须声明该模块可见的知识范围、工具权限、上下文策略和质量门禁。Context Builder 根据 Profile 生成实际上下文。

```text
Module Agent Profile 决定“理论上能看什么”
Context Builder 决定“本次实际装配什么”
Context Snapshot 记录“当时确实看了什么”
```

---

## 三、整体运行链路

```text
Module Graph 进入 Stage Node
  ↓
Workflow Runtime 读取 workflow state
  ↓
Agent Runtime 加载 Module Agent Profile
  ↓
Context Policy Resolver 解析当前 stage 的上下文规则
  ↓
Context Builder 读取业务事实、审批版本、证据引用、知识引用
  ↓
Context Redactor 做权限过滤、租户过滤、密级过滤、脱敏
  ↓
Context Retriever 调 RAG Orchestrator 召回必要知识与证据片段
  ↓
Context Compressor 做摘要、排序、token budget 裁剪
  ↓
生成 Context Envelope
  ↓
写入 Context Snapshot
  ↓
Stage Agent 执行
  ↓
Output Schema Validator 校验 stage_output
  ↓
Workflow 保存草稿输出并进入 HITL
  ↓
人工确认 / 修改 / 驳回
  ↓
approved_version 成为下游默认上下文
```

### 3.1 L1-L4 上下文与记忆生命周期

Hermes 的 L1-L4 不是四个独立的 Agent 私有 Memory，也不是四个平行的“记忆模块”。它描述的是上下文和记忆从一次调用到组织知识的生命周期：

```text
调用上下文
  ↓
阶段交互
  ↓
案件事实
  ↓
组织知识沉淀
```

数据不是自动按 L1 → L2 → L3 → L4 单向流动。每次 Agent 调用时，`Context Builder` 会按需从 L2、L3、L4 读取授权、有效、已审批的引用，重新组装本次 L1 `Context Envelope`。只有在 HITL 通过、案件闭环、知识审核等门槛满足后，数据才会受控提升到更长期的层级。被驳回的 AI 草稿、人工删除的结论、未授权 SQL 明细、高敏原文和无效知识版本，不得默认进入下游上下文或长期知识。

| 层级  | 准确名称                                    | 运行时职责                                                                                                                | 写入 / 固化条件                                  | 最终数据归宿                                                                                                                                                            |
| --- | --------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| L1  | 调用上下文 Invocation Context                | `Context Builder` 在单次 Agent 调用前临时组装 `Context Envelope`，包含当前用户输入、页面/案件字段、附件摘要、OCR/ASR、RAG 片段、Text2SQL 摘要、Prompt 和阶段规则 | 单次调用即时生成，用后释放；只保留可审计引用                     | 不保存完整上下文全文；将 `context_snapshot_id`、引用、版本、脱敏、排序、token 裁剪结果写入 `context_snapshots` / `context_snapshot_refs`                                                         |
| L2  | 阶段交互记忆 Stage Interaction Memory         | 保存当前阶段内的多轮交互、追问、驳回原因、人工修改、重新生成意见和临时 Tool 结果                                                                          | 阶段运行中产生；阶段完成或人工守门结束后压缩归档                   | 热数据在 Redis / checkpoint / session state；最终只将摘要、人工修改、审批意见和必要对话引用写入 `human_approvals`、`audit_log` 和阶段上下文                                                            |
| L3  | 案件事实记忆 Case Record Memory               | 保存单个案件全生命周期的 workflow state、approved stage_output、证据引用、知识引用、数据引用、生成文档、审批链和 A2A 回调                                    | Stage Agent `COMPLETE` 且 HITL 审批通过；案件闭环后归档 | PostgreSQL 业务表，如 `cases`、`case_stages`、`human_approvals`、`generated_documents`、`a2a_tasks`、`external_sync_logs`、`audit_log`；文件本体进入 MinIO / NAS；上下文引用进入 snapshot 表 |
| L4  | 组织知识记忆 Curated Organizational Knowledge | 保存可跨案件复用的制度、历史案例、模板、处罚先例、整改经验、规则和指标口径                                                                                | 案件闭环后生成候选知识；高风险、涉刑、重大金额或高敏材料必须人工审核、脱敏和版本化  | `knowledge_documents` / knowledge metadata；向量索引进入 pgvector 或 Milvus；全文索引进入 Elasticsearch / OpenSearch；规则、指标和处罚先例进入规则库、案例库、指标库                                     |

因此，“记忆最终去了哪里”要按数据形态拆分：

| 数据形态 | 最终归宿 | 说明 |
|----------|----------|------|
| 业务事实 | PostgreSQL 业务表 | 案件、项目、问题、人员、组织、阶段状态等权威事实 |
| 阶段产物 | `case_stages`、stage output 表、approval 定稿版本 | 只把人工确认后的 `approved_version` 作为下游默认事实 |
| 人工守门 | `human_approvals`、`audit_log` | 记录审批动作、修改内容、驳回原因、签名和操作人 |
| 上下文快照 | `context_snapshots`、`context_snapshot_refs` | 记录 Agent 当时实际看见的引用、版本、脱敏策略和裁剪结果 |
| 证据和附件 | MinIO / NAS + evidence metadata + Search/Milvus 索引 | 原件不默认进入 Prompt；上下文只注入摘要、片段和引用 |
| 生成文档 | MinIO / NAS + `generated_documents` | 报告、公告、协议、报案材料等保存对象路径、版本和确认状态 |
| 结构化查询结果 | Text2SQL query log / data_refs / diagnostics | 不把未审批 SQL 和高敏明细原文作为默认上下文，只保存摘要、引用和诊断 |
| 组织知识 | `knowledge_documents`、knowledge metadata、pgvector/Milvus、ES/OpenSearch | 闭环案件经验经审核、脱敏和版本化后进入长期知识库 |

以廉洁监察为例，数据流转如下：

```text
用户提交举报线索、案件字段、附件
  ↓
L1: Context Builder 临时组装 intake-agent 输入
  - 案件基础字段
  - 附件摘要、OCR/ASR
  - 组织制度、相似案例、证据引用
  ↓
intake-agent 输出初判草稿
  ↓
L2: 本阶段追问、人工修改、驳回原因留在会话/checkpoint
  ↓
HITL 审批通过或修改后通过
  ↓
L3: approved 初判写入 case_stages / human_approvals / audit_log / context_snapshot_refs
  ↓
investigation-agent 只读取 approved 初判生成调查方案
  ↓
analysis-agent 读取 approved 初判、approved 调查方案、证据片段、访谈转录、Text2SQL 摘要和 data_refs
  ↓
disposition-agent 读取 approved 案件结论和制度/处罚先例
  ↓
enforcement-agent 读取 approved 追责方案，生成公告、协议、Outbox/A2A 任务
  ↓
案件闭环
  ↓
L4: 调查报告、处置经验、缺陷模式、处罚先例经审核后进入知识库、规则库、案例库和检索索引
```

关键规则：

- L1 是调用上下文，不是持久记忆；不长期保存“模型完整输入全文”，只保存可回放引用和快照元数据。
- L2 是阶段交互，不是案件事实；只有人工采纳、修改或审批后的内容才能进入 L3。
- L3 是案件事实和决策链，承载业务闭环、审计追溯和后续阶段输入。
- L4 是组织知识沉淀，必须经过脱敏、审核、版本化和知识库入库流程。
- L1-L4 的运行关系是“按需召回 + 受控提升”，不是无条件单向复制。
- 下游 Agent 默认只读 `approved_version`，不得把 `agent_raw_output`、被驳回草稿或人工删除结论作为事实。

---

## 四、上下文分类

### 4.1 Workflow Context

**权威来源**：LangGraph durable checkpoint  
**用途**：告诉 Agent 当前处于哪个流程阶段，以及本次执行的流程背景。

典型字段：

| 字段 | 说明 |
|------|------|
| `workflow_thread_id` | LangGraph thread id |
| `current_stage` | 当前阶段 |
| `state_version` | workflow state 版本 |
| `retry_count` | 当前节点重试次数 |
| `pending_approval_stage` | 等待人工守门的阶段 |
| `event_waiting_status` | 是否等待 Worker 或外部回调 |
| `previous_stage_outputs` | 上游已确认阶段产物引用 |

约束：

- Agent 只读 workflow context。
- Agent 不能修改 `current_stage`。
- Agent 不能决定是否跳过 HITL。

### 4.2 Business Context

**权威来源**：PostgreSQL 业务事实库  
**用途**：提供案件、项目、问题、人员、组织、状态等业务事实。

典型字段：

| 字段 | 说明 |
|------|------|
| `case_id` / `project_id` / `issue_id` | 业务对象 ID |
| `module` | 所属模块 |
| `client` | group/ecovacs/tineco |
| `org_ids` | 授权组织范围 |
| `security_level` | 数据密级 |
| `business_subjects` | 涉及人员、供应商、部门、项目 |
| `case_summary` | 当前业务摘要 |
| `current_business_status` | 业务状态 |

约束：

- Agent 不能直接修改业务事实。
- 业务事实必须经过租户、组织、角色、密级过滤。
- 高敏字段默认以脱敏摘要进入上下文。

### 4.3 Stage Context

**权威来源**：workflow state + stage_output 表 + approval 定稿版本  
**用途**：给下游 Agent 提供上游阶段已经确认的结论和产物。

版本优先级：

```text
人工审批后的 approved_version
  >
人工修改草稿 human_edited_version
  >
Agent 最新草稿 agent_draft_version
  >
Agent 原始输出 agent_raw_output
```

生产规则：

- 下游默认只读取 `approved_version`。
- 被人工驳回的版本不得作为下游事实。
- Agent 原始输出只用于质量评估、审计回放，不默认注入业务推理。

### 4.4 Evidence Context

**权威来源**：evidence 表、MinIO、OCR/ASR/文档解析结果、Search/Milvus 索引  
**用途**：提供证据引用、证据摘要和授权片段。

默认注入：

| 内容 | 是否注入 |
|------|----------|
| `evidence_id` | 是 |
| 证据类型、来源、hash | 是 |
| 证据摘要 | 是 |
| 高相关片段 | 按阶段注入 |
| 原始全文 | 默认不注入 |
| 原始文件 URL | 不注入，仅通过短期授权 Tool 获取 |

生产规则：

- 共享证据引用，不共享无限原文。
- 证据原件不可被 Agent 修改。
- 大文件只注入摘要和片段，原件由授权 Tool 按需读取。

### 4.5 Knowledge Context

**权威来源**：knowledge metadata、Search Adapter、Milvus、RAG Orchestrator  
**用途**：注入制度、法规、历史案例、模板、规则、整改经验。

召回链路：

```text
query rewrite
  ↓
metadata filter
  ↓
Elasticsearch/OpenSearch 全文召回
  ↓
Milvus 向量召回
  ↓
merge + deduplicate
  ↓
rerank
  ↓
citation packaging
```

必须过滤：

| 过滤维度 | 说明 |
|----------|------|
| 模块 | 只检索当前模块或被授权共享知识 |
| 租户 | group/ecovacs/tineco 范围 |
| 组织 | org_ids |
| 密级 | 不超过当前用户和阶段授权密级 |
| 生效日期 | 失效制度不得作为高置信依据 |
| 知识版本 | 输出记录生成时使用的版本 |
| 文档状态 | 草稿、下架、失效文档不得默认召回 |

### 4.6 Human Context

**权威来源**：approval、audit_log、人工修改记录  
**用途**：让下游 Agent 知道人类确认了什么、修改了什么、为什么驳回。

典型字段：

| 字段 | 说明 |
|------|------|
| `approval_result` | approved / approved_with_edits / rejected |
| `approved_by` | 审批人 |
| `approved_version` | 定稿版本 |
| `human_edits_ref` | 人工修改引用 |
| `review_comments` | 审批意见 |
| `rejected_reason` | 驳回原因 |

生产规则：

- 人工修改优先于 AI 原始输出。
- 驳回原因必须进入重跑上下文。
- 审批意见不可被 Agent 覆盖。

### 4.7 Tool Context

**权威来源**：Module Agent Profile + RBAC + Stage policy  
**用途**：声明当前 Agent 可用和禁用工具。

典型字段：

| 字段 | 说明 |
|------|------|
| `allowed_tools` | 当前阶段允许调用的工具 |
| `forbidden_tools` | 禁止调用的工具 |
| `tool_scope` | 数据范围、密级、只读/写入模式 |
| `idempotency_key` | 工具调用幂等键 |

生产规则：

- Agent 不得自行扩权。
- 高风险工具只能生成 Outbox 事件，不直接执行外部写入。
- SQL 工具默认只读，写操作禁止。

---

## 五、Context Envelope 规范

每次 Agent 调用前，Context Builder 生成统一的 `Context Envelope`。

```json
{
  "trace_id": "otel-trace-id",
  "context_snapshot_id": "ctx-uuid",
  "case_id": "case-uuid",
  "module": "integrity_supervision",
  "stage": "analysis",
  "agent_id": "analysis-agent",
  "tenant_scope": {
    "client": "group",
    "org_ids": ["org-001"],
    "security_level": "confidential"
  },
  "workflow_context": {
    "thread_id": "wf-thread-id",
    "current_stage": "analysis",
    "state_version": 12,
    "retry_count": 0,
    "previous_stage_outputs": [
      {
        "stage": "intake",
        "output_ref": "stage-output-intake-v2",
        "approved_version": 2
      },
      {
        "stage": "investigation_plan",
        "output_ref": "stage-output-plan-v1",
        "approved_version": 1
      }
    ]
  },
  "business_context": {
    "case_summary": "...",
    "subjects": [],
    "risk_type": "fraud",
    "key_facts": []
  },
  "stage_context": {
    "approved_outputs": [],
    "human_edits": [],
    "excluded_outputs": []
  },
  "evidence_context": {
    "evidence_refs": [],
    "relevant_snippets": []
  },
  "knowledge_context": {
    "knowledge_refs": []
  },
  "human_context": {
    "approval_result": "approved_with_edits",
    "human_edits_ref": "approval-edit-id",
    "review_comments": "..."
  },
  "tool_context": {
    "allowed_tools": ["rag_search", "evidence_search", "doc_generate"],
    "forbidden_tools": ["external_write", "punishment_execute"]
  },
  "token_budget": {
    "max_input_tokens": 32000,
    "reserved_output_tokens": 4096
  },
  "context_quality": {
    "knowledge_sufficient": true,
    "evidence_sufficient": true,
    "missing_items": [],
    "redaction_applied": true
  }
}
```

约束：

- Envelope 是 Agent 的唯一标准输入载体。
- Envelope 内必须包含 `context_snapshot_id`。
- Envelope 不能包含未授权原文、未审批结论、已失效知识。

---

## 六、Context Policy 设计

每个 `Module Agent Profile` 必须增加 `context_policy`。

### 6.1 通用结构

```yaml
context_policy:
  default_token_budget: 32000
  reserved_output_tokens: 4096
  include_previous_approved_outputs: true
  include_agent_raw_outputs: false
  include_human_edits: true
  evidence_mode: refs_plus_relevant_snippets
  knowledge_mode: hybrid_rag
  pii_redaction: role_based
  snapshot_required: true
  fail_on_policy_violation: true

stage_context_rules:
  stage_name:
    include:
      - case_basic_info
      - approved_previous_outputs
      - evidence_refs
      - knowledge_refs
    exclude:
      - agent_raw_outputs
      - unauthorized_org_data
      - external_write_tools
    retrieval:
      top_k_knowledge: 8
      top_k_evidence: 12
      rerank: true
    token_budget:
      max_input_tokens: 32000
      reserved_output_tokens: 4096
```

### 6.2 廉洁监察示例

```yaml
profile_id: integrity-supervision-agent-profile

context_policy:
  default_token_budget: 32000
  include_previous_approved_outputs: true
  include_agent_raw_outputs: false
  include_human_edits: true
  evidence_mode: refs_plus_relevant_snippets
  knowledge_mode: hybrid_rag
  snapshot_required: true

stage_context_rules:
  intake:
    include:
      - case_basic_info
      - reporter_material_summary
      - uploaded_evidence_summary
      - org_policy
      - similar_cases
    exclude:
      - punishment_templates
      - external_write_tools

  investigation_plan:
    include:
      - approved_intake_output
      - case_basic_info
      - evidence_refs
      - historical_investigation_cases
      - interview_templates

  analysis:
    include:
      - approved_intake_output
      - approved_investigation_plan
      - evidence_refs
      - transcript_snippets
      - text2sql_summary
      - data_refs
      - text2sql_diagnostics
      - similar_case_refs

  enforcement:
    include:
      - approved_disposition_output
      - approved_penalty_plan
      - template_refs
    exclude:
      - unconfirmed_case_conclusion
```

---

## 七、Context Builder 实现逻辑

### 7.1 核心流程

``` text
build_context(request):
  1. 校验 workflow thread、module、stage、agent_id
  2. 加载 Module Agent Profile 和 profile_version
  3. 解析 stage_context_rules
  4. 读取 workflow checkpoint
  5. 读取 PostgreSQL 业务事实
  6. 读取 approval 后的阶段产物
  7. 读取人工修改和驳回意见
  8. 解析 evidence_refs 和 knowledge_scope
  9. 做 RBAC、RLS、租户、组织、密级过滤
  10. 调 RAG Orchestrator 召回知识与证据片段
  11. 脱敏敏感字段
  12. 标记 must_keep / compressible / lazy_load / drop_candidate
  13. 对长文本做结构化摘要、排序和 token budget 裁剪
  14. 执行 ContextCompressionGate
  15. 生成 Context Envelope
  16. 写入 context_snapshot 和 context_snapshot_refs
  17. 返回 Envelope 给 Agent Runtime
```

### 7.2 伪代码

```python
class ContextBuilder:
    async def build(self, request: ContextBuildRequest) -> ContextEnvelope:
        profile = await self.profile_repo.get(
            module=request.module,
            version=request.profile_version,
        )
        stage_rule = profile.context_policy.stage_context_rules[request.stage]

        workflow_state = await self.workflow_store.get_state(
            thread_id=request.workflow_thread_id,
        )
        business_context = await self.business_repo.get_context(
            case_id=request.case_id,
            tenant_scope=request.tenant_scope,
        )
        approved_outputs = await self.stage_output_repo.get_approved_outputs(
            case_id=request.case_id,
            stages=stage_rule.required_previous_stages,
        )
        human_context = await self.approval_repo.get_latest_approval_context(
            case_id=request.case_id,
            stage=request.stage,
        )

        policy_scope = self.policy_resolver.resolve(
            profile=profile,
            stage_rule=stage_rule,
            user=request.user,
            tenant_scope=request.tenant_scope,
        )

        evidence_refs = await self.evidence_repo.find_refs(
            case_id=request.case_id,
            scope=policy_scope,
        )
        knowledge_refs = await self.rag.retrieve(
            query=self.query_builder.build(request, business_context, approved_outputs),
            scope=policy_scope.knowledge_scope,
            top_k=stage_rule.retrieval.top_k_knowledge,
            rerank=stage_rule.retrieval.rerank,
        )

        redacted_context = self.redactor.apply(
            business_context=business_context,
            evidence_refs=evidence_refs,
            knowledge_refs=knowledge_refs,
            policy=policy_scope.redaction_policy,
        )
        compressed_context = await self.compressor.fit_budget(
            context=redacted_context,
            approved_outputs=approved_outputs,
            human_context=human_context,
            token_budget=stage_rule.token_budget,
        )
        gate_result = self.compression_gate.validate(
            compressed_context=compressed_context,
            stage_rule=stage_rule,
            human_context=human_context,
        )
        if not gate_result.passed:
            await self.snapshot_repo.save_failed_build(
                request=request,
                quality=gate_result.context_quality,
                refs=compressed_context.refs,
                reason=gate_result.reason,
            )
            raise ContextInsufficientError(
                reason=gate_result.reason,
                missing_items=gate_result.missing_items,
                required_action="human_select_materials",
            )

        envelope = ContextEnvelope(
            trace_id=request.trace_id,
            context_snapshot_id=new_context_id(),
            module=request.module,
            stage=request.stage,
            agent_id=request.agent_id,
            workflow_context=workflow_state.to_context(),
            business_context=compressed_context.business,
            stage_context=approved_outputs,
            evidence_context=compressed_context.evidence,
            knowledge_context=compressed_context.knowledge,
            human_context=human_context,
            tool_context=policy_scope.tool_context,
            token_budget=stage_rule.token_budget,
            context_quality=compressed_context.quality,
        )

        await self.snapshot_repo.save(
            envelope=envelope,
            refs=compressed_context.refs,
            dropped_refs=compressed_context.dropped_refs,
            compression_quality=compressed_context.quality,
        )
        return envelope
```

### 7.3 失败处理

| 失败点 | 处理方式 |
|--------|----------|
| Profile 不存在 | 阻断 Agent 执行，进入系统异常 |
| stage rule 不存在 | 阻断执行，不允许默认放宽 |
| 权限校验失败 | 阻断执行并写安全审计 |
| 业务事实缺失 | 标记 `missing_business_context`，按阶段决定阻断或人工补充 |
| 上游 approved output 缺失 | 阻断下游执行，回到 workflow 补充/审批节点 |
| Search Adapter 不可用 | 标记全文检索降级，保留 workflow 状态 |
| Milvus 不可用 | 标记向量召回降级，Agent 输出知识不足或进入人工接管 |
| token 超预算 | 按裁剪优先级压缩，仍超预算则阻断并要求人工选择材料 |
| 压缩门禁失败 | 写入失败快照和 `dropped_refs`，返回 `context_insufficient`，不调用 Stage Agent |
| 脱敏失败 | 阻断执行，写安全审计 |

---

## 八、Token Budget 与裁剪策略

### 8.1 按 Agent 类型设预算

| Agent 类型 | 输入预算 | 输出预算 | 上下文策略 |
|------------|----------|----------|------------|
| 初筛类 | 16K-24K | 2K-4K | 少量材料摘要 + 关键制度 + 相似案例 |
| 方案类 | 24K-32K | 4K-8K | 上游定稿 + 模板 + 历史方案 + 组织职责 |
| 分析判断类 | 32K-64K | 4K-8K | 多证据片段 + 工具结果 + 制度依据 + 人工意见 |
| 报告类 | 32K-64K | 8K-16K | 已确认结论 + 模板 + 证据引用 |
| 整改复核类 | 24K-32K | 4K | 原问题 + 整改计划 + 证据摘要 + 验收标准 |

### 8.2 裁剪优先级

裁剪不是按时间顺序从后往前删除，而是按业务、证据和审计价值分级处理。Context Compressor 必须先标记 `must_keep`、`compressible`、`lazy_load` 和 `drop_candidate`，再执行 token budget 控制。

| 优先级 | 内容 | 处理要求 |
|--------|------|----------|
| P0 | System Prompt、安全策略、当前阶段任务、输出 Schema | 不可裁剪；超预算时应阻断而不是删除 |
| P0 | 人工确认结果、人工驳回原因、人工修改意见 | 不可静默裁剪；长说明可压缩，但结论、责任人、时间和审批动作必须保留 |
| P0 | 当前阶段必填输入、HITL 通过的上游 `stage_output` | 不可静默裁剪；缺失时返回 `context_insufficient` |
| P0 | 支撑结论的 `evidence_refs`、`data_refs`、`knowledge_refs` | 原文可按需读取，但引用 ID、版本、来源、证据角色必须保留 |
| P1 | 关键证据片段、访谈关键 Q&A、异常数据样本 | 优先保留原文关键句或结构化片段；不足时保留摘要 + ref |
| P1 | 生效制度依据、处罚规则、历史处理先例 | 制度/法规关键条款和版本必须保留；历史案例可摘要 |
| P2 | 上游阶段摘要、阶段内多轮沟通摘要 | 可结构化压缩；必须保留决策、待办、分歧和人工确认状态 |
| P3 | 历史相似案例、低相关 RAG 片段、重复工具输出 | 可压缩或延迟召回；被排除时写入 `dropped_refs` |
| P4 | 原始对话长文本、大附件全文、低置信召回结果 | 默认不全文注入；仅保留摘要、片段和可授权读取的 ref |

以下内容禁止静默丢弃：

- 已审批结论、人工修改、人工驳回和补充意见。
- 与结论直接相关的证据引用、数据引用、制度引用。
- 金额、主体、时间、组织、供应商、合同、付款、审批链等关键案件要素。
- 事实冲突、证据缺口、低置信标记和待人工确认事项。
- Text2SQL 的查询口径、数据范围、脱敏摘要、diagnostics 和 `data_refs`。
- RAG 命中的生效制度条款、版本、适用范围和废止状态。

### 8.3 摘要压缩规则

| 内容类型           | 压缩策略                  |
| -------------- | --------------------- |
| ASR 全文         | 保留说话人、时间戳、关键问答、风险相关段落 |
| OCR 全文         | 保留表格、金额、日期、主体、签章、异常字段 |
| PDF/Office 长文档 | 先按章节切块，再按 query 相关度召回 |
| 历史案例           | 保留案件类型、关键事实、处理结论、引用编号 |
| 审批意见           | 不压缩关键结论，只压缩说明性长文本     |

摘要压缩必须输出结构化结果，而不是只有一段自然语言概括。

```json
{
  "summary_id": "ctx-summary-uuid",
  "source_refs": [
    {
      "ref_type": "evidence",
      "ref_id": "ev-001",
      "ref_version": "v3",
      "source_hash": "sha256:...",
      "included": true,
      "compression_action": "extract_key_span"
    }
  ],
  "confirmed_facts": [
    {
      "fact_id": "fact-001",
      "subject": "采购员张三",
      "predicate": "经办供应商A采购订单",
      "object": "2025Q3订单",
      "time_range": "2025-07-01/2025-09-30",
      "supporting_refs": ["ev-001", "data-ref-006"],
      "confidence": "high"
    }
  ],
  "disputed_facts": [
    {
      "description": "供应商A是否与张三亲属存在实际控制关系仍待核验",
      "supporting_refs": ["ev-003"],
      "opposing_refs": ["interview-002"],
      "required_action": "补充工商关系核验"
    }
  ],
  "decisions": [
    {
      "decision": "进入调查方案生成",
      "approved_by": "user-id",
      "approved_at": "2026-07-03T10:30:00+08:00",
      "approval_ref": "approval-001"
    }
  ],
  "human_edits": [
    {
      "edit_ref": "approval-001",
      "field": "risk_level",
      "before": "medium",
      "after": "high",
      "reason": "涉及供应商围标和亲属账户收款"
    }
  ],
  "evidence_refs": ["ev-001", "ev-003"],
  "data_refs": ["data-ref-006"],
  "knowledge_refs": ["kb-policy-009:v4:article-12"],
  "missing_items": ["供应商A工商关联关系证明"],
  "dropped_refs": [
    {
      "ref_id": "case-similar-021",
      "reason": "低相关历史案例，token budget 超限",
      "can_lazy_load": true
    }
  ],
  "compression_quality": {
    "source_token_count": 42800,
    "compressed_token_count": 6800,
    "truncation_ratio": 0.84,
    "critical_items_dropped": false,
    "evidence_coverage": 1.0,
    "human_edit_preserved": true
  }
}
```

### 8.4 压缩防丢失门禁

Context Compressor 输出后必须经过 `ContextCompressionGate` 校验，校验未通过时不得继续调用 Stage Agent。

| 门禁 | 校验规则 | 失败处理 |
|------|----------|----------|
| 事实保真 | 压缩后的 `confirmed_facts` 必须能回溯到 `source_refs` | 返回 `context_insufficient`，要求补充或选择材料 |
| 引用覆盖 | 每个高风险结论必须至少关联一个 `evidence_ref`、`data_ref` 或 `knowledge_ref` | 降低置信度；定性、处分、移交阶段直接阻断 |
| 人工意见保留 | `human_approvals` 中的审批、驳回、修改必须进入摘要或引用 | 阻断并记录 `human_edit_missing` |
| 冲突保留 | 原始材料中的关键矛盾不得在摘要中被抹平 | 标记 `disputed_facts`，要求 Agent 显式说明 |
| 数据口径保留 | Text2SQL 结果必须保留 query_id、sql_hash、时间范围、过滤条件和 diagnostics | 阻断数据分析型结论 |
| 制度有效性 | 制度/法规引用必须保留版本、生效时间、废止状态 | 返回 `knowledge_insufficient` |
| 裁剪比例 | `truncation_ratio` 超过策略阈值且存在 P0/P1 材料未注入 | 阻断并要求人工选择证据包 |

`context_quality` 至少包含：

```json
{
  "knowledge_sufficient": true,
  "evidence_sufficient": true,
  "data_sufficient": true,
  "human_edit_preserved": true,
  "critical_items_dropped": false,
  "missing_items": [],
  "dropped_refs": [],
  "truncation_ratio": 0.32,
  "compression_gate_passed": true
}
```

### 8.5 超预算处理流程

```text
统计 token
  -> 标记 P0/P1/P2/P3/P4
  -> P4 延迟召回
  -> P3 压缩或剔除，写 dropped_refs
  -> P2 结构化摘要
  -> P1 保留关键片段 + ref
  -> P0 原样保留或最小化结构保留
  -> 执行 ContextCompressionGate
  -> 仍超预算或门禁失败
      -> status=context_insufficient
      -> required_action=human_select_materials
      -> 不调用 Stage Agent 生成业务结论
```

### 8.6 廉洁监察压缩示例

`analysis-agent` 通常是上下文压力最大的节点。它不能把访谈、流水和制度条款简单压成一段故事，而应按以下方式处理：

| 输入材料 | 压缩方式 | 必保留信息 |
|----------|----------|------------|
| 举报正文 | 标准化为结构化案件事实，不作为最终事实源 | 被举报人、供应商、金额、时间、事项、原始举报 `evidence_ref` |
| 访谈转录 | 提取关键 Q&A、矛盾点、时间戳和说话人 | 问题、回答、说话人、时间戳、访谈 `evidence_ref` |
| 附件/OCR | 保留合同、发票、审批流、签章、金额、日期相关片段 | 文件 ID、页码/区域、金额、主体、日期、签章状态 |
| Text2SQL 结果 | 注入脱敏聚合摘要、异常样本和 `data_refs` | query_id、sql_hash、数据范围、返回行数、diagnostics |
| 制度条款 | 保留适用条款、版本、生效时间和适用条件 | `knowledge_ref`、条款号、版本、是否废止 |
| 历史案例 | 保留相似点、差异点、处理结论和引用 | 案例类型、适用边界、脱敏状态、案例 ref |

若供应商名称、交易金额、关键时间、人工审批意见或任一结论支撑引用缺失，`analysis-agent` 必须收到 `context_insufficient`，而不是继续生成调查分析结论。

---

## 九、上下文快照与审计回放

每次 Agent 调用必须生成 `context_snapshot`。

### 9.1 表设计建议

#### context_snapshots

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | context_snapshot_id |
| `trace_id` | TEXT | OpenTelemetry trace id |
| `case_id` | UUID | 案件/项目/问题 ID |
| `module` | TEXT | 模块 |
| `stage` | TEXT | 阶段 |
| `agent_id` | TEXT | Agent ID |
| `workflow_thread_id` | TEXT | LangGraph thread |
| `workflow_state_version` | INTEGER | workflow state 版本 |
| `profile_id` | TEXT | Module Agent Profile |
| `profile_version` | TEXT | Profile 版本 |
| `prompt_version` | TEXT | Prompt 版本 |
| `token_budget` | JSONB | token 分配 |
| `redaction_policy` | JSONB | 脱敏策略 |
| `context_quality` | JSONB | 上下文质量标记 |
| `created_by` | UUID | 触发人/系统 |
| `created_at` | TIMESTAMPTZ | 创建时间 |

#### context_snapshot_refs

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `snapshot_id` | UUID | 关联 context_snapshots |
| `ref_type` | TEXT | approved_output / evidence / knowledge / tool_result / human_edit |
| `ref_id` | TEXT | 引用 ID |
| `ref_version` | TEXT | 引用版本 |
| `included` | BOOLEAN | 是否实际注入 |
| `redacted` | BOOLEAN | 是否脱敏 |
| `rank` | INTEGER | 注入排序 |
| `score` | NUMERIC | 检索或相关性分数 |
| `must_keep` | BOOLEAN | 是否属于 P0/P1 必保留材料 |
| `compression_action` | TEXT | include_full / extract_key_span / summarize / lazy_load / drop |
| `token_count_before` | INTEGER | 压缩前 token 估算 |
| `token_count_after` | INTEGER | 压缩后 token 估算 |
| `exclusion_reason` | TEXT | 未注入原因，如 permission_denied / budget_exceeded / low_relevance |
| `source_hash` | TEXT | 原始片段 hash，用于回放和篡改校验 |

### 9.2 审计回放要求

通过 `context_snapshot_id` 必须能回答：

- Agent 当时看到了哪些业务事实？
- 用的是哪个 workflow state 版本？
- 上游阶段产物是否为人工确认版本？
- 引用了哪些证据和知识？
- 知识库版本是否有效？
- 哪些字段被脱敏？
- 哪些材料因权限、密级、token 预算被排除？
- 使用了哪个 Prompt 版本和模型 provider？
- 输出结论是否超出上下文依据？

### 9.3 压缩回放要求

压缩后的上下文必须能同时回放“Agent 看到的内容”和“Agent 没看到但被排除的内容”。回放服务至少支持三类视图：

| 视图 | 用途 | 数据来源 |
|------|------|----------|
| Agent View | 复现当次 LLM 输入 | `context_snapshots` + `included=true` refs |
| Evidence View | 检查摘要是否遗漏关键证据 | `context_snapshot_refs` + evidence metadata + MinIO/NAS 原件 |
| Omission View | 解释为什么某些材料未注入 | `included=false` refs + `exclusion_reason` + token budget |

生产排障时，如果业务结论被质疑，必须能够沿 `trace_id -> context_snapshot_id -> context_snapshot_refs -> source object` 还原完整链路，判断问题来自检索缺失、权限过滤、压缩遗漏、人工未审批还是 Agent 推理偏差。

---

## 十、跨模块上下文共享

跨模块不共享完整 workflow state，也不传递完整 Agent 上下文。跨模块只共享事件和引用。

### 10.1 事件信封

```json
{
  "event_type": "risk_alert_confirmed",
  "source_module": "risk_monitoring",
  "target_module": "integrity_supervision",
  "business_ref": "risk-alert-id",
  "summary": "...",
  "risk_level": "high",
  "evidence_refs": ["ev-001", "ev-002"],
  "knowledge_refs": ["kb-001"],
  "approved_by": "user-id",
  "schema_version": "1.0",
  "idempotency_key": "...",
  "trace_id": "..."
}
```

目标模块收到事件后：

```text
写入 Inbox
  ↓
验签、去重、审计
  ↓
由目标 Module Graph 创建或恢复流程
  ↓
目标模块 Context Builder 根据本模块 Profile 重新装配上下文
```

### 10.2 禁止事项

- 风险监控不得把完整 workflow state 直接传给廉洁监察。
- 行为风险不得把全量员工行为日志直接传给离任审计。
- 商业秘密不得把涉密原文直接注入其它模块。
- 持续改善不得把上游模块未确认问题草稿作为整改事实。

---

## 十一、各模块上下文策略

### 11.1 廉洁监察

| Stage Agent | 必须上下文 | 禁止/限制上下文 |
|-------------|------------|----------------|
| `intake-agent` | 举报材料摘要、证据引用、组织制度、相似案例 | 处罚模板、外部写入工具 |
| `investigation-agent` | 已确认初判、案件基础信息、证据引用、历史调查方案 | 未审批初判草稿 |
| `analysis-agent` | 已确认初判、已确认调查方案、证据片段、访谈转录、Text2SQL 摘要、`data_refs`、diagnostics | 被人工删除的 AI 结论、未审批 SQL 或高敏明细原文 |
| `disposition-agent` | 已确认案件结论、制度依据、处罚先例 | 未确认事实 |
| `enforcement-agent` | 已确认追责方案、模板、外部系统任务配置 | 重新判断案件事实 |
| `post-report-agent` | 已确认案件结论、已确认报案/处置材料、外部问题清单、资料引用 | 未审批补充材料、无权限原始明细 |
| `investigation-advisor` | 已确认调查方案、证据缺口、时间线、已采纳/未采纳建议状态 | 直接修改主干 stage_output、读取无关案件 |
| `case-complexity-assessor` | 初筛案件要素、金额/人数/组织/证据类型、租户和密级范围 | 处罚模板、外部写入工具、未经授权组织数据 |

### 11.2 风险监控

| Stage Agent | 必须上下文 | 禁止/限制上下文 |
|-------------|------------|----------------|
| `risk-rule-agent` | 数据库 schema、历史规则、风险案例、业务场景 | 生产库写权限 |
| `risk-analysis-agent` | 已审核规则、扫描结果、主体信息、历史误报反馈 | 未审核 SQL 直接执行 |
| 误报优化能力 | 处置回流、人工复核意见、规则版本 | 未确认处置结论 |

### 11.3 内控评价

| Stage Agent | 必须上下文 | 禁止/限制上下文 |
|-------------|------------|----------------|
| `audit-plan-agent` | 业务循环、控制活动、制度、历史方案 | 无关业务循环材料 |
| `interview-agent` | 审计方案、岗位职责、组织架构、访谈模板 | 无关人员敏感信息 |
| `audit-check-agent` | 底稿、测试样本、制度条款、评分标准 | 未授权业务数据 |
| 报告生成能力 | 已确认缺陷、评分结果、整改安排 | 未确认缺陷草稿 |

### 11.4 专项审计

| Stage Agent | 必须上下文 | 禁止/限制上下文 |
|-------------|------------|----------------|
| `audit-plan-agent` | 审计目的、重点、历史方案、项目成员 | 无关项目资料 |
| `audit-check-agent` | 检查资料、访谈结论、底稿、证据引用 | 未授权数据源 |
| `special-issue-confirm-agent` | 问题草稿、反馈、补充证据 | 已驳回问题作为事实 |
| `special-audit-report-agent` | 已确认问题、整改建议、报告模板 | 新增未经确认问题结论 |

### 11.5 离任审计

| Stage Agent | 必须上下文 | 禁止/限制上下文 |
|-------------|------------|----------------|
| `audit-plan-agent` | 被审计人职责、任职期间、历史风险 | 全量无关个人信息 |
| `exit-material-agent` | 职责范围、系统清单、风险预警 | 超出审计期间的数据 |
| `exit-issue-agent` | 资料、访谈、行为风险摘要、业务证据 | 行为风险单独作为问题成立依据 |
| `exit-report-agent` | 已确认问题、责任边界、报告模板 | 未确认个人责任结论 |

### 11.6 商业秘密

| Stage Agent | 必须上下文 | 禁止/限制上下文 |
|-------------|------------|----------------|
| `secret-precheck-agent` | 定密材料摘要、历史定密、制度依据 | 涉密原文默认注入 |
| `secret-policy-compare-agent` | 内控制度、保密制度、知识产权制度 | 失效制度作为高置信依据 |
| `secret-review-agent` | 预审报告、法规案例、横向对比、行为风险摘要 | Agent 自动确定最终密级 |
| `secret-management-report-agent` | 台账、统计口径、历史趋势 | 未脱敏涉密明细 |

### 11.7 行为风险

| Stage Agent | 必须上下文 | 禁止/限制上下文 |
|-------------|------------|----------------|
| `behavior-data-quality-agent` | 数据范围、系统覆盖、字段口径 | 非授权组织数据 |
| `behavior-anomaly-agent` | 行为日志摘要、岗位职责、员工生命周期、涉密范围 | 全量员工行为明细默认注入 |
| `behavior-risk-report-agent` | 异常解释、证据引用、历史趋势 | 直接输出处罚或违规事实认定 |
| `behavior-management-report-agent` | 覆盖率、数据质量、趋势统计 | 个人敏感明细 |

### 11.8 持续改善

| Stage Agent | 必须上下文 | 禁止/限制上下文 |
|-------------|------------|----------------|
| `improvement-issue-ingest-agent` | 上游已确认问题、证据引用、责任部门 | 上游未确认问题草稿 |
| `rectification-plan-review-agent` | 原问题、根因、整改计划、验收标准 | 无关历史整改明细 |
| `rectification-evidence-review-agent` | 整改证据、前后对比、计划要求 | 原始文件无限全文 |
| `closure-acceptance-agent` | 问题、计划、证据、复核记录 | Agent 直接关闭问题 |
| `improvement-knowledge-agent` | 已闭环问题、根因、措施、效果 | 未审核知识条目直接入库 |

---

## 十二、安全与合规控制

| 控制点 | 设计要求 |
|--------|----------|
| 租户隔离 | Context Builder 必须传入 `tenant_scope`，所有业务、证据、知识查询都带 metadata filter |
| 组织隔离 | 使用应用层过滤 + PostgreSQL RLS 双重控制 |
| 密级控制 | Agent 上下文不得超过用户、阶段、模块允许密级 |
| PII 脱敏 | 手机号、身份证、邮箱、员工敏感字段按角色脱敏 |
| 涉密文件 | 默认只注入摘要和引用，不注入原文 |
| Tool 权限 | Tool Registry 按模块、阶段、角色授权 |
| 审计日志 | 每次上下文装配和 Agent 调用都写 audit_log/agent_run_log |
| 不可篡改 | context_snapshot append-only，不允许业务服务 UPDATE/DELETE |

---

## 十三、可观测性与质量指标

### 13.1 技术指标

| 指标 | 说明 |
|------|------|
| `context_build_latency_ms` | 上下文装配耗时 |
| `context_token_count` | 实际输入 token 数 |
| `context_truncation_ratio` | 被裁剪比例 |
| `context_compression_ratio` | 压缩前后 token 比例 |
| `critical_ref_drop_count` | P0/P1 引用被排除次数 |
| `compression_gate_fail_count` | 压缩门禁失败次数 |
| `context_insufficient_count` | 因上下文不足阻断 Agent 次数 |
| `retrieval_hit_rate` | RAG 命中率 |
| `knowledge_ref_count` | 注入知识引用数量 |
| `evidence_ref_count` | 注入证据引用数量 |
| `redaction_count` | 脱敏字段数量 |
| `context_policy_violation_count` | 上下文策略违规次数 |

### 13.2 质量指标

| 指标 | 说明 |
|------|------|
| `approved_output_usage_rate` | 下游使用人工确认版本比例 |
| `citation_validity_rate` | 引用有效率 |
| `human_correction_rate` | 人工修改率 |
| `knowledge_insufficient_rate` | 知识不足率 |
| `evidence_insufficient_rate` | 证据不足率 |
| `data_insufficient_rate` | 结构化数据不足率 |
| `fact_preservation_rate` | 压缩摘要保留关键事实比例 |
| `citation_preservation_rate` | 压缩后引用链保留比例 |
| `human_edit_preservation_rate` | 人工修改在下游上下文中保留比例 |
| `contradiction_preservation_rate` | 冲突事实在摘要中保留比例 |
| `context_replay_success_rate` | 上下文快照可回放成功率 |

---

## 十四、生产验收场景

| 场景 | 验收标准 |
|------|----------|
| 人工修改传递 | 上游人工修改后，下游 Agent 只能读取 approved_version |
| 未审批草稿隔离 | Agent 原始草稿不得进入下游默认上下文 |
| 跨模块事件共享 | 只传事件和引用，目标模块重新装配上下文 |
| 知识库失效过滤 | 失效制度不得作为高置信依据 |
| 证据全文控制 | 大文件不默认注入全文，只注入摘要和片段 |
| 权限越权拦截 | Agent 请求未授权证据或 Tool 时被拒绝并记录安全审计 |
| 检索降级 | Search/Milvus 不可用时 workflow 不丢状态，Agent 输出知识不足或人工接管 |
| 上下文回放 | 通过 context_snapshot_id 能复现当时输入引用、版本、脱敏策略和 token 裁剪 |
| Token 超预算 | 按优先级裁剪，仍超预算则阻断并要求人工选择材料 |
| 摘要压缩防丢失 | 压缩后 P0/P1 材料不得丢失；摘要必须保留引用链、人工意见、冲突事实和 `dropped_refs` |
| 压缩门禁 | `ContextCompressionGate` 失败时不调用 Stage Agent，返回 `context_insufficient` / `knowledge_insufficient` / `evidence_insufficient` |
| Prompt/模型追踪 | 每次 Agent 调用能关联 prompt_version、profile_version、provider、model 和 trace_id |

---

## 十五、实现对象清单

| 对象 | 类型 | 职责 |
|------|------|------|
| `ContextPolicy` | 配置对象 | 定义模块和阶段上下文规则 |
| `ContextEnvelope` | 输入对象 | Agent 标准输入载体 |
| `ContextSnapshot` | 持久化对象 | 审计回放和可复现依据 |
| `ContextBuilder` | 服务 | 装配上下文 |
| `ContextPolicyResolver` | 服务 | 解析 Profile、RBAC、Stage Rule |
| `ContextRetriever` | 服务 | 获取业务、阶段、证据、知识上下文 |
| `ContextRedactor` | 服务 | 脱敏和密级裁剪 |
| `ContextCompressor` | 服务 | 摘要和 token budget 控制 |
| `ContextCompressionGate` | 服务 | 校验压缩后事实、引用、人工意见和冲突信息是否保留 |
| `ContextValidator` | 服务 | 校验上下文完整性和策略合规 |
| `ContextReplayService` | 服务 | 基于 snapshot 回放 Agent 输入 |

---

## 十六、设计边界

上下文工程必须坚持以下边界：

- 不让 Agent 自己拼接全局上下文。
- 不让 Agent 自己决定能看哪些数据。
- 不把上游未审批草稿作为下游事实。
- 不把大文件全文默认注入 Prompt。
- 不把跨模块 workflow state 直接传递。
- 不把 Memory 当作 Agent 私有记忆。
- 不在 Prompt 里隐藏权限规则和审批规则。

最终生产设计应落在这句话上：

```text
上下文是系统治理下的结构化资产，不是 Agent 的自由记忆。
```
