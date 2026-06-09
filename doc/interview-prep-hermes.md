# Hermes 项目面试准备材料

> 适用场景：全栈综合面试、后端/AI 架构面试、项目复盘面试。  
> 讲述口径：以完整生产蓝图为主线，同时明确当前代码实现状态，避免把规划模块说成已经全部上线。

---

## 0. 面试前先记住的边界

这个项目可以这样定性：

- **项目定位**：Hermes 是面向科沃斯集团企业风控场景的 AI 智能体平台，用 LLM + RAG + 多智能体工作流，把风险发现、调查取证、处置处罚、整改闭环串成一个端到端系统。
- **业务范围**：覆盖 8 个模块：廉洁监察、风险监控、内控评价、专项审计、离任审计、商业秘密、行为风险、持续改善。
- **实现状态**：当前仓库已经有 FastAPI 后端、API v1 路由、异步 SQLAlchemy 数据模型、廉洁监察 5 个 Agent、RAG 引擎、LangGraph 工作流骨架、Celery/RabbitMQ 多模态任务骨架、A2A/风控系统集成骨架。
- **蓝图状态**：风险监控、内控评价、专项审计、离任审计、商业秘密、行为风险、持续改善等模块在文档里是生产级设计，部分数据库模型和接口已经规划或建模，但不应说成全部生产落地。

面试里推荐使用这句稳妥话术：

> 这个项目目前处于“核心后端脚手架 + 廉洁监察 Agent 优先落地 + 生产架构蓝图完整”的阶段。我主要按照完整生产架构去设计系统，但在回答实现细节时，会区分当前已编码部分和规划中的生产能力。

---

## 1. 30 秒项目介绍

Hermes 是一个企业风控 AI 智能体系统，目标是把传统风控里被动举报、人工调查、手工审计和整改跟踪，升级成主动发现、智能分析和闭环管理。系统用 FastAPI 做后端接口，用 PostgreSQL + pgvector 存业务数据和知识库向量，用 LangGraph 编排多阶段 Agent 工作流，并通过 RAG、人工守门和 A2A 协作保证 AI 输出有依据、可审核、可追溯。整体上，风险监控负责主动发现异常，廉洁监察、内控评价、审计等模块负责分析处置，持续改善模块负责最终整改闭环。

---

## 2. 1 分钟项目介绍

我这个项目叫 Hermes，是面向企业风控的 AI 智能体平台。业务背景是企业内部风控往往存在几个问题：线索发现依赖举报，调查决策依赖个人经验，审计方案和历史案例没有沉淀，证据处理和整改追踪也比较割裂。

所以我把系统设计成 8 个业务模块的闭环架构：风险监控负责主动扫描异常并推送线索；廉洁监察、内控评价、专项审计、离任审计、商业秘密、行为风险负责不同类型风险的调查分析；持续改善统一承接问题整改，跟踪到复核和归档。

技术上，后端使用 FastAPI、SQLAlchemy async、Pydantic v2 和 JWT/RBAC；AI 侧使用 LangGraph 编排工作流，用 Agent 分阶段处理初筛、调查方案、分析报告、处置分流和处罚执行；知识增强采用 pgvector + Elasticsearch 的混合检索思路；长耗时任务通过 RabbitMQ + Celery 异步化；关键 AI 决策都设计了 Human-in-the-Loop 人工守门，保证输出不是黑盒自动执行。

当前代码已经实现了后端骨架、廉洁监察 Agent、RAG 引擎、API、数据库模型和工作流骨架，其他模块主要是生产蓝图和数据/API 设计。

---

## 3. 3 分钟技术深挖讲法

如果面试官让你详细讲，可以按“一个案件从创建到闭环”的链路说。

### 3.1 请求进入系统

用户在前端创建案件或从风控系统同步线索，请求进入 FastAPI。后端统一挂载在 `/api/v1`，通过中间件做审计日志、限流、CORS，再通过 JWT Bearer Token 解析当前用户。用户角色分为 `group`、`ecovacs`、`tineco`，应用层会按 `client` 做行级过滤，生产蓝图里还会叠加 PostgreSQL RLS 作为数据库兜底。

数据库层使用 SQLAlchemy 2.0 async session。FastAPI 的 `get_db()` 依赖负责请求结束后的 commit，异常时 rollback，保证 API handler 不需要手动管理事务边界。

### 3.2 案件数据落库

廉洁监察核心表主要有：

- `cases`：案件主表，记录案件来源、事业部、当前阶段、状态、LangGraph thread_id。
- `case_stages`：阶段流转表，记录每个阶段的 AI 输入、AI 输出、知识库引用、状态、错误和重试次数。
- `human_approvals`：人工守门记录，记录原始 AI 输出、人工修改、审批动作、签名和时间。
- `generated_documents`：生成文档表，记录 Word/Excel 报告在 MinIO 或文件系统中的位置。

共享表包括 `users`、`audit_log`、`external_sync_logs`、`a2a_tasks`。其中 `audit_log` 按 append-only 思路设计，支持等保二级要求下的操作追溯。

### 3.3 工作流启动

用户点击“启动工作流”后，后端会：

1. 检查案件是否存在、用户是否有权限访问。
2. 生成 `thread-{task_id}` 作为 LangGraph 线程 ID。
3. 更新 `cases.status = investigating`、`current_stage = intake`。
4. 新建第一条 `case_stages`，状态为 `pending_approval`。
5. 异步触发廉洁监察 LangGraph 工作流。

廉洁监察工作流是 6 阶段：

```text
intake 初筛
  -> investigation 调查方案
  -> analysis 多维分析与报告
  -> disposition 处置分流
  -> enforcement 处罚执行
  -> post_report 报案后续协助
```

其中 `intake` 后有条件路由：如果 AI 判断不需要调查，或需要转交，就可以结束或进入外部协作；如果继续调查，就进入 `investigation`。`disposition` 后也有条件路由：如果不涉及追责，可以闭环；如果涉及追责，进入处罚执行。

### 3.4 Agent 怎么执行

每个廉洁监察 Agent 的实现模板类似：

1. **Pydantic 输入校验**：例如 `IntakeAgentInput` 要求案件描述、来源、事业部、附件预处理结果等。
2. **PromptManager 渲染模板**：按模块和阶段加载 YAML prompt，注入案件信息、知识库上下文、历史案例上下文。
3. **LLMAdapter 调用大模型**：主模型是 DeepSeek，备用是 Qwen，使用 OpenAI 兼容接口；主模型连续失败会切换备用。
4. **结构化解析**：优先解析 LLM 返回的 JSON，转成 `IntakeAgentOutput`、`InvestigationAgentOutput` 等 Pydantic 模型。
5. **降级处理**：如果 JSON 解析失败，就做自由文本应急解析；如果 LLM 全部不可用，就返回 `confidence=unable` 的 fallback 输出，进入人工判断。
6. **上下文传递**：每个 Agent 输出 `downstream_context`，把关键事实、置信度、风险标记、证据摘要传给下游 Agent。

这套设计的核心不是让 AI 直接“拍脑袋决策”，而是让 AI 输出结构化、可校验、可追溯的中间结果，再由人工守门确认后进入下一步。

### 3.5 RAG 怎么做

知识库按业务阶段分区，例如 `intake`、`investigation`、`analysis`、`disposition`、`enforcement`、`risk_monitor`、`ic_evaluation` 等。查询时可以限定不同 `kb_type`，避免把不相关知识混进 prompt。

目标生产方案是：

- PGVector 负责语义相似度召回。
- Elasticsearch 负责中文全文检索、关键词、过滤和聚合。
- 双路召回结果用 RRF 或加权融合。
- 检索结果带 `doc_id`、`kb_type`、标题、片段、相关度、更新时间，注入 prompt 时保留引用来源。

当前代码实现已经支持：

- 尝试调用 Embedding API 获取 query embedding。
- 成功时使用 pgvector 余弦相似度检索。
- pgvector 或 Embedding 不可用时，降级为 PostgreSQL ILIKE 搜索。
- 最终把检索结果格式化成“相关知识库内容”注入 LLM prompt。

### 3.6 人工守门怎么做

Hermes 里把人工审批叫“碳基守门”，这是整个系统的安全边界。每个关键 AI 决策节点完成后，不直接执行外部写操作，而是进入 `pending_approval` 状态。前端审批页展示：

- AI 输出结论。
- 知识库引用。
- 置信度和不确定因素。
- 原始输出和可修改内容。
- 审批动作：通过、驳回、修改。

审批记录写入 `human_approvals`。如果通过，工作流继续；如果修改，则以人工修改后的结果恢复工作流；如果驳回，则重新执行当前阶段或转人工处理。

### 3.7 异步和外部系统

系统里有很多长耗时任务，例如 LLM 推理、文档生成、音频转文字、OCR、视频关键帧、外部系统同步、A2A 协作等。设计上用 RabbitMQ + Celery 承接后台任务：

- API 快速返回 `task_id`。
- Worker 后台执行。
- WebSocket 推送进度。
- RabbitMQ 提供 ACK、持久化、死信队列、优先级和重试。

外部协作通过 A2A 协议连接 HR、法务、财务等智能体，比如龟宝、 西塞罗、波特。A2A 任务写入 `a2a_tasks`，通过统一消息格式、callback、retry 和幂等键保证可追踪。

### 3.8 前端怎么承接

前端蓝图使用 Vue 3 + TypeScript + Vite + Element Plus + Pinia。核心页面包括：

- 登录页：获取 access token 和 refresh token。
- 案件列表：筛选、分页、创建案件、启动工作流。
- 案件详情：展示案件基本信息、阶段状态、生成文档。
- 守门审批页：展示 AI 输出、修改内容、审批动作。
- 知识库页：管理和搜索知识库。
- 管理后台：用户、角色、审计日志。

前端重点不是炫技，而是把复杂流程状态表达清楚：`pending -> investigating -> pending_approval -> approved/rejected -> closed`。写操作要带幂等键，按钮要 loading/disabled，避免重复提交。

### 3.9 部署怎么讲

部署分两个 Profile：

- **P1 生产高可用**：Kubernetes 多节点、PostgreSQL Patroni、Redis Cluster、RabbitMQ、MinIO、Elasticsearch、Prometheus/Grafana、LangFuse、Jaeger。目标是 10K 注册用户、峰值 500 并发、10TB 数据，API 可用性 99.9%。
- **D0 本地/测试/PoC**：Docker Compose 单机，适合 100 用户测试规模、30 并发以内、5TB 以下测试或脱敏数据。不承诺生产 SLA。

面试里要强调：不要把 D0 的单机测试部署说成生产架构。

---

## 4. 项目架构图讲法

```text
前端 Vue3/TS
  -> FastAPI API Gateway
      -> Auth/RBAC/Audit/RateLimit
      -> Cases / Workflow / Approval / Knowledge / Webhooks
          -> SQLAlchemy AsyncSession
          -> PostgreSQL + pgvector
          -> MinIO / Elasticsearch / Redis
          -> LangGraph Workflow
              -> Intake Agent
              -> Investigation Agent
              -> Analysis Agent
              -> Disposition Agent
              -> Enforcement Agent
          -> RabbitMQ + Celery Workers
              -> LLM 推理
              -> 文档生成
              -> 多模态处理
              -> A2A / 外部系统同步
```

一句话解释：

> API 层负责接入和权限，服务层负责业务状态，数据层负责持久化和审计，LangGraph 负责有状态 AI 工作流，Celery/RabbitMQ 负责长耗时异步任务，RAG 和 Agent 负责智能分析，HITL 负责风险控制。

---

## 5. 八大模块如何有条理地讲

不要逐个模块散讲，按“推送层、执行层、并行业务层、闭环层”讲。

### 5.1 推送层：风险监控

风险监控是主动发现入口。它根据风险规则、业务数据、外部数据自动跑数，识别异常主体，做风险定性，然后推送到廉洁监察、内控评价、商业秘密、行为风险等模块。它的核心价值是把“被动等举报”变成“主动找异常”。

### 5.2 执行层：廉洁监察、内控评价、商业秘密

廉洁监察处理舞弊举报和调查闭环；内控评价评估制度设计和执行缺陷；商业秘密处理定密预审、评审和管理报告。这些模块都需要知识库、AI 分析、人工守门和外部系统集成。

### 5.3 并行业务层：专项审计、离任审计、行为风险

专项审计和离任审计更偏审计项目制，强调方案生成、访谈、检查、问题确认和报告输出。行为风险强调跨系统数据分析，比如文件传输、解密、DLP、人事档案、涉密信息等。

### 5.4 闭环层：持续改善

持续改善是所有问题的统一承接层。它把廉洁监察、内控评价、专项审计、离任审计、行为风险、商业秘密产生的问题清单汇入，走问题录入、整改下发、计划审核、整改提交、AI 初审、审计复核、闭环归档。

一句总括：

> 风险监控负责发现问题，各业务模块负责分析和处置，持续改善负责把整改做到闭环。

---

## 6. 6 个 STAR 难点回答

### 难点 1：为什么用 LangGraph，不用自研工作流或 Temporal？

**S - 背景**  
廉洁监察不是一个简单的同步流程，而是多阶段、有状态、有条件路由、有人工审批的 AI 工作流。每个阶段都可能被人工修改、驳回、重试或中断。

**T - 任务**  
需要一个能表达 Agent 节点、状态传递、断点恢复、条件分支和 HITL 的工作流框架。

**A - 行动**  
我选择 LangGraph。它天然支持 StateGraph、节点编排、条件路由、checkpointer、interrupt 和 streaming，和 LangChain/LLM 生态集成更顺。廉洁监察 6 个阶段被建成 StateGraph 节点，`intake` 和 `disposition` 后用条件路由决定是否继续调查或进入处罚执行。

**R - 结果**  
这样工作流逻辑和 Agent 逻辑解耦，阶段状态可以落在 `case_stages`，人工审批可以通过 `human_approvals` 暂停和恢复。

**替代方案**  
自研状态机维护成本高，后续扩展 Agent 和断点恢复会复杂；Temporal 很强，但更适合传统长事务编排，对 LLM Agent 的 prompt、streaming、interrupt 场景偏重。生产级如果流程更复杂，可以考虑 Temporal 管外层业务长事务，LangGraph 管内层 AI 推理链路。

### 难点 2：为什么用 PGVector + Elasticsearch，不直接用 Milvus？

**S**  
项目既有结构化业务数据，也有知识库文档和审计报告。查询既需要语义相似度，也需要中文关键词、过滤和聚合。

**T**  
需要一个兼顾运维复杂度、事务一致性、中文检索和性能的知识库方案。

**A**  
设计上用 PostgreSQL + pgvector 存向量和知识库元数据，用 Elasticsearch 做中文全文检索。pgvector 和业务数据共库，便于权限过滤、事务一致和数据治理；ES 用 IK 中文分词和倒排索引，适合 10TB 文档规模下的全文搜索。

**R**  
当前实现已经支持 pgvector 语义检索和 ILIKE 降级，生产蓝图会升级成 PGVector + ES 双路召回，再做 RRF 融合。

**替代方案**  
Milvus 适合更大规模纯向量检索，但会引入单独集群和一致性治理成本。Pinecone 这类 SaaS 不适合等保和内网数据要求。如果未来知识库规模远超 pgvector 能承受，可以把向量层迁到 Milvus，但保留 PostgreSQL 作为元数据和权限控制源。

### 难点 3：为什么 RabbitMQ + Celery，不用 Redis 队列或 Kafka？

**S**  
系统里有大量长耗时任务：LLM 推理、多模态处理、文档生成、外部系统同步、A2A 任务。任务要可靠、可重试、可观测。

**T**  
需要一个企业级任务队列，支持持久化、ACK、优先级、死信队列和失败重放。

**A**  
我选择 RabbitMQ + Celery。Celery 负责任务执行模型，RabbitMQ 负责可靠消息投递。RabbitMQ 支持 quorum queue、DLX、优先级、延迟投递和确认机制，更适合任务队列。

**R**  
API 可以快速返回，耗时任务后台执行，前端通过 WebSocket 看进度，失败任务可以重试或进入人工处理。

**替代方案**  
Redis 适合缓存和简单队列，但作为任务队列时可靠性、优先级和死信治理弱一些。Kafka 更适合日志流和事件流，不太适合需要任务确认和重试语义的工作队列。未来如果风险监控需要海量事件流，可以引入 Kafka 做事件流入口，RabbitMQ 继续做任务执行队列。

### 难点 4：如何防止大模型幻觉？

**S**  
风控和审计场景不能让 AI 随便编法律依据、制度条款或案件结论，否则会带来合规风险。

**T**  
要让 AI 输出有依据、可解释、可审核。

**A**  
我做了多层控制：

- RAG 检索知识库，要求输出引用制度、法条、历史案例或数据来源。
- Pydantic Schema 限定输出结构，例如置信度、不确定因素、缺失信息、法律引用。
- JSON 解析失败时降级为低置信度自由文本解析。
- 如果知识库为空或 LLM 不可用，显式标注 `low/unable`，进入人工介入。
- 人工守门展示 AI 输出、引用依据和不确定因素。
- 生产蓝图里还有 Golden Test、对抗测试、知识库质量评分和 LangFuse 追踪。

**R**  
AI 不再是直接决策者，而是生成可审查的建议。最终关键操作必须由人审批。

**替代方案**  
可以进一步引入 verifier agent，对法条编号、制度引用、证据链做二次校验；也可以引入 citation-only prompt，强制没有来源就不能输出结论。

### 难点 5：如何处理人工审批和 AI 自动化边界？

**S**  
企业风控涉及人员处罚、供应商扣款、报案、黑名单等高风险动作，不能完全自动化。

**T**  
要提升效率，但不能越权或绕过人工责任。

**A**  
设计上所有关键 AI 决策节点都进入 `pending_approval`。AI 可以生成建议、报告和执行动作清单，但外部写操作必须经过人工守门。审批记录写入 `human_approvals`，包括原始输出、修改内容、审批意见和签名。

**R**  
系统既保留了 AI 效率，又保证了责任边界、审计追踪和合规要求。

**替代方案**  
低风险任务可以逐步自动化，比如知识库检索、报告草稿、提醒通知；高风险任务保留人工审批。后续可以按风险等级做分级自动化：低风险自动执行，中风险抽检，高风险强制双签。

### 难点 6：如果继续优化，如何从骨架走向生产级？

**S**  
当前代码实现了后端骨架和廉洁监察核心能力，但生产蓝图更完整，包括全模块、完整异步调度、多模态、可观测性和高可用。

**T**  
要规划清晰的演进路径。

**A**  
我会分四步做：

1. 先把廉洁监察工作流完整跑通：Agent 与 LangGraph 状态、审批恢复、阶段记录和文档生成闭环。
2. 接入 RabbitMQ/Celery：让 LLM、多模态、A2A、文档生成真正异步化。
3. 强化 RAG：补齐 Embedding、pgvector HNSW/IVFFlat、ES 双路召回、RRF 融合和引用校验。
4. 上生产治理：接入 Prometheus、LangFuse、Jaeger、审计日志 append-only、RLS、Vault、备份恢复和 Golden Test。

**R**  
这样能从可演示系统逐步演进到生产可用系统，同时每一步都有明确收益。

---

## 7. 高频追问答案

### Q1：你项目里真正实现了什么？

可以这样回答：

> 当前仓库不是只有文档，已经有后端实现骨架。已实现的包括 FastAPI 应用入口、API v1 路由、JWT 登录和 RBAC、统一响应和异常、SQLAlchemy async 数据模型、廉洁监察 5 个 Agent、Pydantic 输入输出 Schema、LLMAdapter 主备模型调用、PromptManager、RAGEngine、LangGraph 廉洁监察工作流骨架、Celery 任务骨架、A2A 和风控系统集成骨架。风险监控、内控评价等模块更多是完整设计和部分模型/API 规划，还没有全部生产落地。

### Q2：Agent 是怎么调用大模型的？

回答：

> Agent 先接收 Pydantic 输入，做基础校验，然后通过 PromptManager 加载对应模块和阶段的 prompt 模板，把案件信息、知识库内容和上游上下文注入进去。接着通过 LLMAdapter 调用 DeepSeek，如果主模型连续失败就切到 Qwen。返回结果优先按 JSON 解析成 Pydantic 输出模型，如果解析失败就做自由文本降级解析；如果模型完全不可用，就返回 `confidence=unable` 的 fallback 结果，并进入人工判断。

### Q3：RAG 是怎么做的？

回答：

> 知识库按业务阶段分区，例如 intake、investigation、analysis、risk_monitor 等。当前代码里 RAGEngine 支持传入 query、kb_types 和 top_k，先尝试获取 embedding，再用 pgvector 做余弦相似度搜索；如果 embedding 或 pgvector 不可用，就降级为 PostgreSQL ILIKE 检索。生产蓝图里会升级成 PGVector + Elasticsearch 双路召回，PGVector 负责语义，ES 负责中文全文，最后用融合排序把结果注入 prompt。

### Q4：工作流卡在人工审批时怎么恢复？

回答：

> 每个 AI 阶段完成后会把当前阶段、AI 输出和状态写入 `case_stages`，并把案件状态置为 `pending_approval`。前端审批页提交通过、驳回或修改后，后端写入 `human_approvals`。如果通过或修改，就把人工确认后的结果作为新的状态输入，恢复 LangGraph 后续节点；如果驳回，则重新执行当前阶段或转人工处理。生产里会通过 LangGraph checkpointer 保存断点，当前代码是工作流骨架，已预留 thread_id 和阶段状态字段。

### Q5：数据权限怎么保证？

回答：

> 权限分三层：集团、科沃斯、添可。JWT 里带用户身份和角色，后端解析后在 API 层做 `client` 过滤。比如 `ecovacs` 只能看 `client=ecovacs` 的数据，`tineco` 只能看添可，`group` 才能看全局。生产蓝图里还会启用 PostgreSQL RLS 做数据库层兜底，MinIO bucket、ES index、Redis key 也按 client 分区。敏感字段用 AES-256-GCM 列级加密，日志里脱敏。

### Q6：如果 LLM 挂了怎么办？

回答：

> LLMAdapter 有主备模型机制，主模型 DeepSeek 连续失败达到阈值后切换到备用 Qwen。Agent 自己也有重试和指数退避。如果主备都不可用，Agent 不会伪造结论，而是返回低置信度或 unable 输出，保留已有输入和检索结果，进入人工介入。这样系统可降级运行，不会因为模型不可用导致流程完全失控。

### Q7：这个项目有没有更好的实现方式？

回答：

> 有。当前设计是比较适合企业内网和中等规模风控场景的平衡方案。如果进一步做生产增强，我会考虑几件事：第一，用 Temporal 管外层跨系统长事务，LangGraph 只管 Agent 推理链；第二，把 RAG 升级成 pgvector + ES + reranker 的多阶段检索；第三，增加 verifier agent 做引用校验和法律条款核验；第四，用事件 outbox/inbox 完整保证跨模块消息最终一致；第五，按风险等级做分级自动化，低风险自动，高风险双签审批。

### Q8：为什么前端没有说太多？

回答：

> 这个项目的核心复杂度在业务流程、AI 工作流和数据闭环。前端使用 Vue 3 + TypeScript + Element Plus，重点不是花哨交互，而是把案件状态、AI 输出、人工审批、进度推送和文档下载表达清楚。比如案件详情页展示阶段流转，审批页展示 AI 输出和修改入口，WebSocket 用于长任务进度。前端要配合后端幂等键、JWT、RBAC 和敏感信息脱敏。

### Q9：如何衡量 Agent 效果？

回答：

> 我会分技术指标和业务指标。技术指标包括 LLM 调用成功率、P95 延迟、JSON 解析成功率、RAG 命中率、工具调用成功率。业务指标包括初筛分流准确率、立案建议采纳率、调查方案采纳率、报告完整度、AI 初核准确率、整改复核采纳率。文档里还设计了 Golden Test Set，用固定案例持续评估 Agent 输出质量。

### Q10：如何处理跨系统一致性？

回答：

> 跨系统一致性不能只依赖一次 HTTP 调用。生产设计里会用 event_outbox 和 event_inbox：业务状态变更和待发送事件在同一个数据库事务里落库，后台 publisher 再发 RabbitMQ；消费侧用 event_id 和 idempotency_key 去重。A2A 和 Webhook 回调也都带 schema_version、event_id、correlation_id 和 idempotency_key。这样即使消息重复、回调延迟或服务重启，也能最终一致。

---

## 8. 技术选型为什么这样选

| 技术 | 为什么用 | 替代方案 | 更好实现 |
|------|----------|----------|----------|
| FastAPI | 原生异步、OpenAPI 自动生成、Python AI 生态好 | Django、Flask | 如果业务后台很重可用 Django Admin，但 AI 异步场景 FastAPI 更轻 |
| SQLAlchemy async | 类型清晰、异步支持、和 FastAPI 配合好 | Django ORM、Tortoise ORM | 复杂查询可结合 SQLModel 或 repository/service 分层 |
| PostgreSQL 16 | 关系数据、JSONB、分区、事务成熟 | MySQL | 风控审计数据强一致，PostgreSQL 更适合 |
| pgvector | 与业务数据共库、权限和事务一致 | Milvus、Weaviate | 大规模向量可迁 Milvus，PostgreSQL 保留元数据 |
| Elasticsearch | 中文全文检索、聚合、倒排索引 | PostgreSQL FTS、Solr | 结合 reranker 做二阶段排序 |
| LangGraph | LLM 工作流、状态、条件路由、interrupt | 自研状态机、Temporal | Temporal 管外层事务，LangGraph 管 Agent |
| RabbitMQ + Celery | 任务队列、ACK、DLX、优先级、重试 | Redis Queue、Kafka | Kafka 可补充事件流，RabbitMQ 保留任务队列 |
| DeepSeek + Qwen | 中文能力、成本、OpenAI 兼容、主备切换 | GPT-4、文心一言 | 生产可做模型网关和灰度评估 |
| Vue 3 + TS | 企业前端成熟、类型友好 | React | 大型管理端可继续强化组件库和权限路由 |
| Docker Compose / K8s | D0 快速测试，P1 高可用生产 | 单机裸部署 | 生产必须走 K8s + 外部密钥 + 监控 |

---

## 9. 项目价值怎么讲

可以从四个维度讲：

1. **业务效率**：把人工筛查、方案编制、报告撰写、整改跟踪自动化，减少重复劳动。
2. **风险发现**：风险监控从被动举报变成主动扫描，支持 7x24 异常发现。
3. **知识沉淀**：制度、历史案例、审计方案、缺陷类型沉淀到知识库，降低对个人经验的依赖。
4. **合规可控**：AI 输出可追溯、人工可审批、操作有审计日志、敏感数据加密脱敏。

一句总结：

> Hermes 的价值不是让 AI 替代风控人员，而是把风控人员从重复检索、整理和写报告里释放出来，让他们把精力放在判断、审批和处置上。

---

## 10. 面试时不要踩的坑

- 不要说 8 个模块已经全部生产上线。应说“完整蓝图覆盖 8 个模块，当前优先落地廉洁监察和后端基础能力”。
- 不要说 AI 自动处罚或自动报案。应说“AI 生成建议和材料，外部写操作必须人工守门”。
- 不要把 D0 Docker Compose 当成生产架构。应区分 D0 测试和 P1 K8s 生产。
- 不要只背技术栈。要把技术栈和业务痛点绑定，例如 LangGraph 解决多阶段 HITL，RabbitMQ 解决长任务可靠投递，RAG 解决依据和可解释性。
- 不要回避当前骨架状态。承认当前是逐步落地，更真实。

---

## 11. 最后一页速记

### 11.1 一句话

Hermes 是企业风控 AI 智能体平台，用 LLM + RAG + LangGraph + HITL + A2A，把风险发现、调查分析、处置处罚、整改闭环串起来。

### 11.2 三个关键词

- **主动发现**：风险监控 7x24 扫描异常。
- **智能分析**：Agent + RAG 生成调查方案、证据链和报告。
- **闭环可控**：人工守门、审计日志、持续改善整改归档。

### 11.3 五个技术亮点

- LangGraph 多阶段 Agent 工作流。
- Pydantic Schema 结构化 AI 输出。
- PGVector + ES 混合 RAG。
- RabbitMQ + Celery 异步任务。
- JWT/RBAC/RLS/AES/审计日志安全体系。

### 11.4 六个难点

- LLM 不稳定。
- AI 幻觉。
- 长流程状态一致性。
- 人工审批和自动化边界。
- 跨系统 A2A 一致性。
- 大规模知识库检索和运维。

### 11.5 最稳妥收尾

> 这个项目对我最大的收获是：AI 应用真正难的不是调用一次大模型，而是把模型放进一个可靠的业务系统里。它需要状态管理、权限、安全、审计、降级、人工审批、数据治理和可观测性。Hermes 正是围绕这些工程问题做的设计和实现。
