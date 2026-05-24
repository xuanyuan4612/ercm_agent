# 项目知识库

**生成日期：** 2026-05-20
**状态：** 实施前设计阶段（尚未编写 Python 源码）
**Python：** 3.12

## 概述

赫尔墨斯（Hermes）—— 科沃斯集团企业风控 AI 智能体。采用 LLM + RAG + 多智能体协作（A2A），覆盖 8 大业务模块：廉洁监督 → 风险监测 → 内控评价 → 专项审计 → 离任审计 → 商业秘密 → 行为风险 → 持续改进。

## 目录结构

```
./
├── doc/              # [源] 设计规范 — 项目全部实质内容
│   └── modules/      # 8 个模块需求文档 + 索引
├── .venv/            # [环境] Python 3.12 虚拟环境（仅 pip，无项目依赖）
├── .idea/            # [IDE] PyCharm 配置 — 不可手动修改
└── .sisyphus/        # [工具状态] 智能体会话持久化 — 忽略
```

## 查阅指引

| 任务 | 位置 | 说明 |
|------|----------|-------|
| 项目概览与需求 | `doc/hermes-requirements.md` | 8 个模块、依赖关系图、业务背景 |
| 系统架构 | `doc/architecture-design.md` | LangGraph、FastAPI、K8s、PostgreSQL、RAG、A2A |
| 数据模型 / 数据库模式 | `doc/data-design.md` | 约 40 张 SQL 表，PostgreSQL 16 + pgvector |
| API 规范 | `doc/api-design.md` | RESTful `/api/v1/*`，JWT，RBAC，异步优先 |
| 模块级需求 | `doc/modules/` | 每个模块一个文件，编号 00-08 |
| 模块索引与模块间流程 | `doc/modules/README.md` | 依赖关系图、共享基础设施清单 |
| CI/CD 流水线设计 | `doc/architecture-design.md` §6.7 | GitLab CI，4 个阶段：Lint → Test → Build → Deploy |
| 测试策略 | `doc/architecture-design.md` §8.9 | pytest、异步、5 种测试类型 |

## 技术栈（规划中）

| 层级 | 技术 |
|-------|------|
| 后端 | Python 3.12、FastAPI、SQLAlchemy 2.0 异步 |
| 工作流 | LangGraph（每个模块一个 StateGraph，通过 interrupt_before 实现人机协作 HITL） |
| 大语言模型 | DeepSeek（主用）、Qwen 通义千问（备用） |
| 数据库 | PostgreSQL 16 + pgvector 0.7+ |
| 缓存 | Redis 7（检查点、会话、热数据） |
| 消息队列 | RabbitMQ + Celery（9 个工作池） |
| 搜索 | Elasticsearch（IK 中文分词器）+ pgvector 混合检索 |
| 存储 | MinIO（对象存储）、NAS（冷归档） |
| 前端 | Vue 3 + TypeScript SPA |
| 部署 | Kubernetes、Helm、Harbor 镜像仓库、GitLab CI/CD |
| 可观测性 | LangFuse + Prometheus + structlog + Jaeger |

## 约定规范（从设计文档推断）

- **Python**：必须 3.12（设计文档要求最低 3.11+）
- **包管理器**：`uv`（基于 Rust，架构文档中指定）
- **ORM**：SQLAlchemy 2.0 声明式，异步会话
- **模式校验**：Pydantic v2
- **API 响应封装**：`{"code": 0, "message": "success", "data": {...}}`
- **分页响应封装**：`{"code": 0, "data": {"items": [...], "total": N, "page": P, "page_size": S}}`
- **认证**：JWT Bearer Token，RBAC（三级：group/ecovacs/tineco）
- **数据库命名**：snake_case，表名复数，`id UUID PK`，`{action}_at TIMESTAMPTZ`，`is_{bool}`
- **时间戳**：ISO 8601（`2026-05-19T10:30:00Z`）
- **编码**：UTF-8
- **审计**：不可篡改的 audit_log 表，每次变更均记录

## 反模式（本项目）

尚无 — 不存在任何源码。以下是需要强制执行的**设计层面规则**：

- 不允许在最终的 `hermes/` 包目录之外创建新的 `.py` 文件
- 不允许绕过 LangGraph 的 HITL（人机协作）审批关卡
- 不允许在 SQLAlchemy 会话之外直接写入数据库
- 不允许硬编码密钥 — 使用 Pydantic Settings 与环境变量

## 命令

尚无可运行的命令。以下为根据架构文档规划的命令：

```bash
# 开发
uv sync                          # 安装依赖
uv run pytest                    # 运行全部测试
uv run pytest tests/unit/ -v     # 仅运行单元测试
uv run ruff check .              # 代码检查
uv run mypy --strict .           # 类型检查

# 数据库
alembic upgrade head             # 执行迁移（K8s Job）

# 构建
docker build -t harbor.intranet/hermes/api:$TAG .
helm package deploy/charts/hermes

# 部署
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-*-deployments.yaml
```

## 备注

- **尚无源码。** 当前 100% 为设计文档。实施应从 `doc/architecture-design.md` §5.1（包脚手架）开始。
- **尚未初始化 Git 仓库。** 编写代码前请运行 `git init`。
- **尚无项目配置文件**（`pyproject.toml`、`ruff.toml` 等）— 必须从零创建。
- 模块依赖关系图为 DAG（无环）：推送层（M2）→ 执行层（M1、M3、M6）→ 汇聚层（M8），并行层（M4、M5、M7）。
