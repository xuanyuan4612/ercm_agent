# 赫尔墨斯（Hermes）后端开发文档

> 版本：v1.0 | 更新日期：2026-06-08 | 适用模块：廉洁监察

---

## 一、项目概述

**赫尔墨斯（Hermes）** 是面向科沃斯集团的风险控制 AI 智能体系统，基于 FastAPI + LangGraph + PostgreSQL + Redis + RabbitMQ 技术栈构建。

部署口径遵循 `doc/architecture-design.md`：P1 为正式生产 K8s 高可用架构；D0 Docker Compose 仅用于本地开发、测试、PoC 和容量验证。后端实现不得把 D0 的 `.env`、单节点依赖或测试账号作为生产默认。

### 1.1 技术栈

| 组件 | 选型 | 版本 |
|------|------|------|
| Web 框架 | FastAPI | ≥0.115 |
| 工作流引擎 | LangGraph | ≥0.2 |
| LLM 适配 | LangChain | ≥0.3 |
| ORM | SQLAlchemy 2.0 (async) | ≥2.0 |
| 数据库 | PostgreSQL 16 + pgvector | 16 / 0.7+ |
| 缓存 | Redis 7 | 7.x |
| 消息队列 | RabbitMQ + Celery | 3.13+ / 5.4+ |
| 全文搜索 | Elasticsearch | 8.x |
| 对象存储 | MinIO | RELEASE.2025+ |
| 包管理 | uv (Rust) | latest |
| 数据库迁移 | Alembic | ≥1.14 |

### 1.2 项目结构

```
hermes/
├── main.py                    # FastAPI 应用入口
├── celery_app.py              # Celery 任务应用
├── core/                      # 核心模块
│   ├── config.py             # 全局配置 (Pydantic Settings)
│   ├── exceptions.py         # 自定义异常
│   ├── logging.py            # 结构化日志
│   ├── response.py           # 统一响应格式
│   └── security.py           # JWT/加密/签名
├── db/                        # 数据层
│   ├── session.py            # 数据库连接会话
│   └── models/               # SQLAlchemy 模型
│       ├── base.py           # 基类 (UUID/Timestamp/SoftDelete)
│       ├── integrity.py      # 廉洁监察模型
│       ├── knowledge.py      # 知识库模型
│       ├── shared.py         # 共享模型 (User/AuditLog)
│       └── ...
├── agents/                    # AI Agent 层
│   ├── llm_adapter.py        # LLM 调用适配器
│   ├── prompt_manager.py     # Prompt 模板管理
│   ├── rag_engine.py         # RAG 检索增强引擎
│   ├── tool_system.py        # 工具注册系统
│   └── integrity/            # 廉洁监察 Agents
│       ├── schemas.py        # Agent 输入/输出 Schema
│       ├── intake_agent.py   # 初筛 Agent
│       ├── investigation_agent.py  # 调查方案 Agent
│       ├── analysis_agent.py      # 分析报告 Agent
│       ├── disposition_agent.py   # 处置分流 Agent
│       └── enforcement_agent.py   # 处罚执行 Agent
├── api/                       # API 层
│   ├── dependencies.py       # 认证/权限依赖注入
│   └── v1/
│       ├── router.py         # 路由聚合
│       ├── auth.py           # 认证接口
│       ├── cases.py          # 案件管理接口
│       ├── workflow.py       # 工作流接口
│       ├── approval.py       # 守门审批接口
│       ├── documents.py      # 文档管理接口
│       ├── knowledge.py      # 知识库接口
│       ├── webhooks.py       # 外部系统回调
│       ├── websocket.py      # WebSocket 推送
│       └── admin.py          # 管理后台接口
├── workflows/                 # LangGraph 工作流
│   └── integrity/
│       └── graph.py          # 廉洁监察 6 阶段工作流定义
├── integrations/              # 外部系统集成
│   ├── a2a.py                # A2A 智能体通信
│   └── risk_control.py       # 风控系统适配器
├── middleware/                 # 中间件
│   ├── audit.py              # 审计日志中间件
│   └── rate_limit.py         # 速率限制中间件
├── services/                  # 业务服务层
│   └── case_service.py       # 案件管理服务
├── tasks/                     # Celery 异步任务
│   └── processing.py         # 多模态处理任务
└── schemas/                   # Pydantic Schema
    ├── auth.py               # 认证 Schema
    ├── case.py               # 案件 Schema
    └── workflow.py           # 工作流 Schema
```

---

## 二、快速开始

### 2.1 环境准备

```bash
# 安装 Python 3.11+
python --version  # >= 3.11

# 安装 uv 包管理器
pip install uv

# 克隆项目
cd ercm_agent

# 创建虚拟环境并安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置数据库、LLM API Key 等
```

### 2.2 数据库初始化

```bash
# 确保 PostgreSQL 16 已运行
# 创建数据库
createdb -h localhost -U hermes hermes

# 运行数据库迁移
uv run alembic upgrade head

# 初始化种子数据（可选）
uv run python -m hermes.scripts.seed
```

### 2.3 启动服务

```bash
# 开发模式（热重载）
uv run uvicorn hermes.main:app --host 0.0.0.0 --port 8000 --reload

# 访问 API 文档
# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc

# 启动 Celery Worker（可选，异步任务处理）
uv run celery -A hermes.celery_app worker -Q hermes.audio,hermes.image,hermes.doc,hermes.report,hermes.llm --loglevel=info
```

---

## 三、核心架构

### 3.1 廉洁监察工作流（6 阶段）

```
案件录入 → [4.1] 材料初判+分流 (intake-agent)
                    ↓ 立案
         → [4.2] 调查方案 (investigation-agent)
                    ↓
         → [4.3] 多维分析+报告 (analysis-agent)
                    ↓
         → [4.4] 处置分流+追责 (disposition-agent)
                    ↓ 内部追责
         → [4.5] 处罚执行 (enforcement-agent)
                    ↓
         → [4.6] 报案协助 (post-report-agent)
                    ↓
                  闭环
```

每个阶段执行后，LangGraph 在 `interrupt_before` 处挂起，等待碳基守门（HITL）。

### 3.2 请求处理流程

```
HTTP Request → Nginx → FastAPI Router Pool
    → 中间件链 (Audit → RateLimit → CORS → JWT Auth)
    → API Handler (cases/workflow/approval)
    → Service Layer (CaseService)
    → DB Session (SQLAlchemy AsyncSession)
    → Response (ORJSON)
```

### 3.3 异步处理流程

```
用户上传文件 → MinIO → RabbitMQ 事件 → Celery Worker
    → 多模态处理 (Whisper/PaddleOCR/CLIP/unstructured.io)
    → 结果写入 ES + PGVector + PostgreSQL
    → WebSocket 推送完成通知
```

---

## 四、数据库模型

### 4.1 廉洁监察核心表

#### cases（案件主表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| task_id | VARCHAR(30) | 案件编号，全局唯一。格式：{来源缩写}{年月日}{序号} |
| fraud_source | VARCHAR(30) | 来源：manual/phone/email/wechat/agent |
| client | VARCHAR(20) | 事业部：ecovacs/tineco/group |
| fraud_event_detail | TEXT | 舞弊事件详情 |
| reported_staff_encrypted | BYTEA | 员工姓名（AES-256-GCM 加密） |
| risk_control_case_id | VARCHAR(50) | 风控系统案件ID（暂未接入） |
| current_stage | VARCHAR(50) | 当前工作流阶段 |
| workflow_state | JSONB | LangGraph 完整状态 |
| langgraph_thread_id | VARCHAR(64) | LangGraph 线程ID |
| status | VARCHAR(20) | 状态：pending/investigating/disposing/enforcing/closed |
| is_deleted | BOOLEAN | 软删除标记 |

#### case_stages（阶段流转记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| case_id | UUID FK | 关联案件 |
| stage_name | VARCHAR(50) | 阶段名称 |
| ai_input | JSONB | AI 输入数据 |
| ai_output | JSONB | AI 输出数据 |
| status | VARCHAR(20) | pending/approved/rejected |
| retry_count | SMALLINT | 重试次数 |

#### human_approvals（碳基守门记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| case_id | UUID FK | 关联案件 |
| stage_name | VARCHAR(50) | 阶段名称 |
| reviewer_id | VARCHAR(50) | 审核人 |
| action | VARCHAR(20) | approved/rejected/modified |
| signature | VARCHAR(512) | 数字签名（不可篡改） |

#### generated_documents（生成文档）

| 字段 | 类型 | 说明 |
|------|------|------|
| case_id | UUID FK | 关联案件 |
| doc_type | VARCHAR(50) | 文档类型 |
| file_format | VARCHAR(10) | 文件格式 |
| storage_bucket | VARCHAR(100) | MinIO bucket |
| storage_key | VARCHAR(500) | MinIO object key |

---

## 五、API 接口

### 5.1 基础规范

- **Base URL**: `http://host:8000/api/v1`
- **认证方式**: Bearer Token (JWT)
- **响应格式**: `{"code": 0, "data": {...}, "message": "ok"}`
- **分页格式**: `{"code": 0, "data": {"items": [...], "total": N, "page": 1, "page_size": 20}}`
- **错误码范围**: `40000` 客户端错误, `50000` 服务端错误

**生产治理实现要求**：

| 领域 | 后端实现要求 |
|------|--------------|
| 请求链路 | 中间件生成/透传 `X-Request-Id` 与 `X-Correlation-Id`，写入 structlog、Trace、audit_log、Celery headers |
| 幂等 | 写入类接口读取 `Idempotency-Key`；服务层以业务键 + payload hash 去重，重复请求返回首次结果或 `409 duplicate_request` |
| Webhook | 所有外部回调校验 `X-Hermes-Signature`、`X-Hermes-Timestamp`、来源 IP 白名单和 `idempotency_key` |
| 消息一致性 | 业务状态变更与消息发布使用 `event_outbox`；消费者使用 `event_inbox` 长期去重；RabbitMQ 生产队列使用 quorum queues |
| 租户隔离 | 所有查询必须自动注入 `client` 过滤；P1 同时依赖 PostgreSQL RLS 兜底 |
| AI 安全 | Tool 调用按角色/阶段授权；Prompt 注入和 RAG 越权检测失败时进入人工复核 |
| 密钥 | P1 使用 Vault/External Secrets 注入；D0 `.env` 仅限测试，不得复用生产密钥 |

### 5.2 接口列表

#### 认证

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/auth/login` | 用户登录 | 无需 |
| POST | `/auth/logout` | 用户登出 | 登录用户 |
| GET | `/auth/me` | 获取当前用户信息 | 登录用户 |

#### 案件管理

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/cases` | 创建案件 | 登录用户 |
| GET | `/cases` | 案件列表（分页+筛选） | 登录用户 |
| GET | `/cases/{id}` | 案件详情 | 登录用户 |
| PUT | `/cases/{id}` | 更新案件（仅 pending 状态） | 登录用户 |
| DELETE | `/cases/{id}` | 软删除案件 | 登录用户 |

#### 工作流

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/cases/{id}/workflow/start` | 启动工作流 | 登录用户 |
| POST | `/cases/{id}/workflow/resume` | 恢复工作流（守门后） | 登录用户 |
| GET | `/cases/{id}/workflow/status` | 查询工作流状态 | 登录用户 |
| GET | `/cases/{id}/workflow/history` | 查询工作流历史 | 登录用户 |
| POST | `/cases/{id}/workflow/interrupt` | 中断工作流 | 集团角色 |

#### 守门审批

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/cases/{id}/approval/pending` | 查询待审批内容 | 登录用户 |
| POST | `/cases/{id}/approval/{stage}` | 提交审批决定 | 登录用户 |
| POST | `/cases/{id}/approval/{stage}/regenerate` | 划词调整重新生成 | 登录用户 |
| GET | `/cases/{id}/approval/history` | 守门历史记录 | 登录用户 |

#### 文档与知识库

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/cases/{id}/documents` | 案件文档列表 | 登录用户 |
| GET | `/documents/{id}/download` | 下载文档 | 登录用户 |
| POST | `/cases/{id}/speech-to-text` | 上传音频转文字 | 登录用户 |
| GET | `/knowledge-bases/search` | 知识库搜索 | 登录用户 |

#### 管理后台

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/admin/users` | 用户列表 | 集团角色 |
| POST | `/admin/users` | 创建用户 | 集团角色 |
| PATCH | `/admin/users/{id}/status` | 启用/禁用用户 | 集团角色 |
| GET | `/admin/audit-logs` | 审计日志查询 | 集团角色 |

---

## 六、开发指南

### 6.1 添加新的 Agent

```python
# 1. 在 hermes/agents/integrity/schemas.py 定义输入/输出 Schema
class NewAgentInput(BaseModel):
    task_id: str
    # ... 其他字段

class NewAgentOutput(BaseModel):
    result: str
    confidence: Confidence
    processing_time_ms: int

# 2. 创建 Agent 实现
# hermes/agents/integrity/new_agent.py
class NewAgent:
    def __init__(self):
        self.agent_id = "new-agent"

    async def run(self, agent_input: NewAgentInput) -> NewAgentOutput:
        # 1. 构建 Prompt
        # 2. 调用 LLM
        # 3. 解析输出
        pass

# 3. 在 workflow graph 中添加节点
# hermes/workflows/integrity/graph.py
async def new_stage_node(state: IntegrityState) -> IntegrityState:
    agent = NewAgent()
    result = await agent.run(...)
    state["new_output"] = result.model_dump()
    return state

# 4. 注册到工作流图
workflow.add_node("new_stage", new_stage_node)
workflow.add_edge("previous_stage", "new_stage")
```

### 6.2 添加新的 API 路由

```python
# hermes/api/v1/new_module.py
from fastapi import APIRouter, Depends
from hermes.api.dependencies import CurrentUser

router = APIRouter(prefix="/new-module")

@router.get("")
async def list_items(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    # 实现业务逻辑
    return success(items)

# 注册到路由聚合器
# hermes/api/v1/router.py
from hermes.api.v1.new_module import router as new_module_router
api_router.include_router(new_module_router)
```

### 6.3 数据库迁移

```bash
# 创建新迁移
uv run alembic revision --autogenerate -m "描述变更内容"

# 执行迁移
uv run alembic upgrade head

# 回滚
uv run alembic downgrade -1
```

### 6.4 当前开发状态

| 组件 | 状态 | 说明 |
|------|------|------|
| 廉洁监察 Agents | ✅ 已实现 | 5 个 Agent 全部实现，含 LLM 调用、JSON 解析、降级策略 |
| 廉洁监察工作流 | ⚠️ 骨架可用 | LangGraph graph 已定义，Agent 集成待完善 |
| API 路由 | ✅ 完整 | 案件/工作流/审批/文档/知识库/管理后台 |
| 数据库模型 | ✅ 完整 | 案件/阶段/审批/文档/用户/审计日志 |
| A2A 通信 | ⚠️ 固定返回 | 返回"已连通"固定值，RabbitMQ 队列待接入 |
| 风控系统集成 | ⚠️ 手动模式 | 返回固定值，WebSocket/消息队列待接入 |
| RAG 引擎 | ✅ 可用 | pgvector + ILIKE 混合检索，降级策略完善 |
| 多模态处理 | ⚠️ 骨架 | Celery 任务已注册，模型加载待接入 |
| Redis/ES/MinIO | ⚠️ 可选初始化 | 未配置时自动降级 |

### 6.5 配置降级策略

所有外部依赖（Redis、Elasticsearch、MinIO）在未配置或不可用时自动降级：
- **Redis 不可用**: Session 使用内存存储，限流使用简单计数器
- **ES 不可用**: 全文搜索降级为 SQL ILIKE
- **MinIO 不可用**: 文件操作降级为本地文件系统
- **LLM 不可用**: 自动切换备用 LLM → 人工介入

### 6.6 安全规范

- 敏感字段使用 AES-256-GCM 加密存储
- 密码使用 bcrypt 哈希
- JWT Token 8 小时过期，Refresh Token 7 天
- 审计日志不可删除不可篡改
- RBAC 三级权限（集团/科沃斯/添可）

---

## 七、测试

```bash
# 运行所有测试
uv run pytest

# 运行特定模块
uv run pytest tests/unit/

# 带覆盖率
uv run pytest --cov=hermes --cov-report=html
```

---

## 八、Docker 部署

```bash
# 开发环境
docker-compose up -d

# 生产环境
docker-compose -f docker-compose.prod.yml up -d

# 查看日志
docker-compose logs -f api

# 执行数据库迁移
docker-compose exec api uv run alembic upgrade head
```

---

## 九、参考文档

- [系统架构设计](./architecture-design.md)
- [廉洁监察 Agent 设计](./agents/01-integrity-supervision-agents.md)
- [数据库设计](./data-design.md)
- [API 设计](./api-design.md)
- [前端开发文档](./frontend-development-guide.md)
