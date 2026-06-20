# Conversation Gateway Agent 集成设计

> **状态**：已确认  
> **依赖**：[09-conversation-gateway-agent.md](../../agents/09-conversation-gateway-agent.md)、[01b-integrity-supervision-architecture-analysis.md](../../agents/01b-integrity-supervision-architecture-analysis.md)、[02b-risk-monitoring-architecture-analysis.md](../../agents/02b-risk-monitoring-architecture-analysis.md)  
> **日期**：2026-06-20

---

## 一、决策汇总

| 决策点 | 选择 |
|--------|------|
| 集成方案 | 独立路由 + 共享基础设施（方案 A） |
| 集成深度 | 工作流触发 + 上下文共享，两者都要 |
| MVP 范围 | 同步覆盖 Integrity + Risk Monitoring（6 种意图） |
| 工作流交互 | 读写分离：写走 REST API，读走 Workflow Manager |
| 会话存储 | 数据库持久化（3 张表）+ Alembic 迁移 |
| 架构兼容性 | 与现有架构约束完全一致 |

---

## 二、架构

### 组件分层

```
前端 (Copilot 面板 / 守门助手 / 案件详情助手)
  │
  ▼
API 层 (hermes/api/v1/copilot.py)
  │ 会话 CRUD、消息发送、确认动作
  │ 接入 AuditMiddleware + LangfuseTraceMiddleware
  │
  ▼
Agent 层 (hermes/agents/conversation_gateway/)
  │ 继承 BaseAgent，复用 _invoke_llm
  │ 意图识别 → 字段抽取 → 权限预检 → 路由决策
  │
  ├─ 读 ──→ Workflow Managers (get_workflow_state)
  └─ 写 ──→ 现有 REST API (cases / approval / knowledge / risk_monitor)
```

### 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `hermes/schemas/agents/conversation_gateway.py` | 新建 | I/O Schema + 枚举 |
| `hermes/agents/conversation_gateway/__init__.py` | 新建 | 包初始化 |
| `hermes/agents/conversation_gateway/gateway_agent.py` | 新建 | Agent 主逻辑 |
| `hermes/db/models/conversation.py` | 新建 | 3 张表 ORM 模型 |
| `hermes/db/models/__init__.py` | 修改 | 注册新模型 |
| `alembic/versions/005_add_conversation_gateway_tables.py` | 新建 | DDL 迁移 |
| `hermes/api/v1/copilot.py` | 新建 | REST API 端点 |
| `hermes/api/v1/router.py` | 修改 | 注册 copilot router |
| `hermes/agents/profiles.py` | 修改 | 新增 CONVERSATION_GATEWAY_PROFILE |

---

## 三、数据模型

### `conversation_sessions`

| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | gen_random_uuid() |
| user_id | UUID FK→users | 用户 |
| client_scope | JSONB | 权限范围快照 |
| status | VARCHAR(20) | active/completed/cancelled/expired |
| related_case_id | UUID | 可选关联案件 |
| related_module | VARCHAR(50) | 关联模块 |
| context_snapshot | JSONB | 创建时的页面快照 |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### `conversation_messages`

| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | |
| session_id | UUID FK→sessions | CASCADE 删除 |
| role | VARCHAR(10) | user/assistant/system |
| content | TEXT | 消息内容 |
| page_context | JSONB | 发送时的页面快照 |
| attachment_refs | JSONB | 附件引用 |
| created_at | TIMESTAMPTZ | |

### `intent_decisions`

| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | |
| session_id | UUID FK→sessions | |
| message_id | UUID FK→messages | |
| intent_type | VARCHAR(30) | operation/stage/knowledge/document |
| operation | VARCHAR(50) | create_case/query_risk/... |
| module | VARCHAR(50) | integrity_supervision/risk_monitoring/... |
| confidence | NUMERIC(4,3) | 0.000-1.000 |
| slots | JSONB | 抽取的字段 |
| missing_fields | JSONB | 缺失字段 |
| permission_result | VARCHAR(10) | allowed/denied |
| denied_reason | VARCHAR(50) | |
| requires_confirmation | BOOLEAN | |
| risk_level | VARCHAR(10) | low/medium/high |
| confirmed_at | TIMESTAMPTZ | |
| executed_action_ref | VARCHAR(200) | 下游动作引用 |

---

## 四、Agent 设计

### 意图分类（MVP 6 种）

| 操作 | 类型 | 目标 | 是否需要确认 |
|------|------|------|-------------|
| `create_case` | operation | POST /api/v1/cases | 是 |
| `query_case_status` | operation | Workflow Manager (读) | 否 |
| `query_risk` | operation | Workflow Manager (读) | 否 |
| `knowledge_qa` | knowledge | RAG Orchestrator | 否 |
| `approval_assist` | stage | POST /api/v1/approval | 是 |
| `document_rewrite_draft` | document | Document Tool | 是 |

### 置信度策略

| 置信度 | 行为 |
|--------|------|
| >= 0.85 | 生成结构化意图，进入确认/执行预检 |
| 0.60-0.85 | 追问关键字段，让用户确认理解 |
| < 0.60 | 不做路由，说明不确定，给出可选建议 |

### 路由决策

```
RouteDecision
├── ask_user                # 信息不足，追问
├── answer_with_rag         # 知识问答
├── preview_action          # 展示动作草案，等待确认
├── handoff_to_api          # 用户已确认，API 执行
├── handoff_to_workflow     # 用户已确认，Workflow Runtime 执行
├── handoff_to_stage_agent  # 阶段内重生成或解释
├── deny                    # 越权或不允许
└── human_intervention      # 风险过高，转人工
```

### 读写分离

- **读**：`query_case_status` / `query_risk` → 直接调用 `WorkflowManager.get_workflow_state()`，不产生副作用
- **写**：`create_case` / `approval_assist` → 调 REST API，经过 AuditMiddleware、RateLimitMiddleware、权限校验

---

## 五、API 设计

### `POST /api/v1/copilot/sessions`

创建会话。返回 `session_id`。

### `POST /api/v1/copilot/sessions/{id}/messages`

发送消息。请求体包含 `message`、`page_context`、`draft_context`、`attachment_refs`。返回 `reply` + `intent` + `proposed_action`。

### `POST /api/v1/copilot/sessions/{id}/confirm`

确认动作。请求体包含 `message_id`、`action_id`、`confirm`。确认后由服务层调用对应 API 或 Workflow Runtime。

### WebSocket 频道

- `copilot:user:{user_id}`
- `copilot:session:{session_id}`

事件：`copilot.intent_detected`、`copilot.clarification_required`、`copilot.action_preview`、`copilot.action_confirmed`、`copilot.handoff_started`、`copilot.handoff_completed`、`copilot.denied`

---

## 六、安全设计

### 权限预检

每次意图识别前校验：
1. 用户认证状态
2. 角色是否允许该操作
3. 目标 client 数据权限
4. 当前页面/案件状态是否允许该动作
5. 是否涉及高风险 Tool

### Prompt 注入防护

拒绝覆盖系统指令、越权访问、绕过 HITL、伪造身份、数据泄露的输入。拒绝回复简洁明确并审计留痕。

### 高安全动作清单

以下必须用户确认且通常需要 HITL：
- 审批通过/驳回/修改后通过
- 启动/恢复/关闭工作流
- 推送 OA/MDM/A2A
- 导出敏感文档
- 生成处罚公告等正式文书

### 禁止能力

- 直接推进 workflow 阶段
- 直接提交高风险审批通过
- 直接外发 A2A/OA/MDM
- 跨租户检索
- 执行自由 SQL
- 输出无来源的正式结论

---

## 七、错误处理

| 场景 | 处理 |
|------|------|
| LLM 返回不可解析 JSON | Pydantic 校验失败 → 重试一次 → 转人工 |
| 意图置信度 < 0.60 | 不路由，列出可选操作，让用户明确选择 |
| 字段缺失 | 生成追问回复，列出缺失字段 |
| 权限拒绝 | 明确说明原因，给出替代操作建议 |
| 外部 API 超时/失败 | 返回错误信息，不吞掉异常 |
| 会话过期 | 返回 404 或 410，引导用户创建新会话 |

---

## 八、测试策略

| 层级 | 内容 | 数量 |
|------|------|------|
| Schema 单元测试 | Pydantic 输入输出校验 | 10+ |
| Agent 单元测试 | Mock LLM 返回，验证路由决策逻辑 | 20+ |
| API 集成测试 | 完整会话流程 (创建→发消息→确认) | 5+ |
| 安全测试 | Prompt 注入、越权、缺少必填字段 | 15+ |
| Golden Test Set | 创建案件/查询状态/审批辅助/知识问答/风险查询/拒绝 | 100 条 |
