# Hermes 项目面试准备材料

> 适用场景：后端 / AI 应用 / 企业风控 / 架构设计 / 项目复盘面试。
> 讲述口径：以最终生产蓝图为准，生产蓝图就是最终实现，全篇只讲最终生产能力。
> 重点：讲清楚端到端工作流，重点突出 RAG、Text2SQL、HITL、生产安全边界，以及项目难点、亮点和持续优化方向。

---

## 0. 面试前先记住的总口径

Hermes 可以这样定性：

- **项目定位**：Hermes 是面向企业风控的 AI 智能体系统，用 LLM + RAG + Text2SQL + LangGraph + HITL + A2A，把“风险发现、调查分析、处置追责、整改闭环”做成完整风控链路。
- **最终规模**：面向集团 10,000 名注册 / 授权内部用户，峰值 500 并发会话或 API 请求，管理约 10TB 文档与证据数据，支持音频、视频、图像、PDF、Office 等多模态材料。
- **核心边界**：LangGraph Workflow Runtime 是唯一流程推进中心；API、Agent、Worker、外部系统都不能直接跳转业务阶段。
- **知识与数据依据**：RAG 负责制度、案例、模板、证据、数据字典文档的可信检索；Text2SQL 负责结构化数仓查询、指标口径、SQL 生成、校验、审批和只读执行。
- **安全边界**：AI 生成结构化建议，但不直接执行处罚、移交、扣款、外部写入等高风险动作；所有高风险动作必须经过 HITL 和 audit_log。
- **生产口径**：后面所有讲述都按最终生产架构讲，把蓝图能力作为最终实现能力来表达。

一句稳妥开场：

> Hermes 不是一个简单的问答机器人，而是一个企业风控 AI 工作流系统。它的核心是把 LLM 放进可审计、可恢复、可降级、可追溯、有人类守门的生产系统里。RAG 解决“结论有没有制度和证据依据”，Text2SQL 解决“结构化业务数据是否支持这个判断”，LangGraph 负责流程状态，HITL 负责风险边界。

---

## 1. 30 秒项目介绍

Hermes 是一个企业风控 AI 智能体系统，覆盖廉洁监察、风险监控、内控评价、专项审计、离任审计、商业秘密、行为风险和持续改善 8 大模块。系统用 LangGraph 编排多阶段工作流，用 RAG 检索制度、案例、模板和证据，用 Text2SQL 安全查询结构化业务数据，用 HITL 控制高风险动作，最终形成“风险发现、调查分析、处置追责、整改闭环”的端到端风控平台。

---

## 2. 1 分钟项目介绍

这个项目叫 Hermes，面向企业内部风控场景。传统风控里常见的问题是：线索发现依赖举报，调查方案依赖个人经验，制度和历史案例分散，结构化业务数据查询门槛高，外部系统协同和整改闭环割裂。

所以我把系统设计成 8 个业务模块加共享 AI 基础设施。风险监控负责 7x24 主动扫描异常；廉洁监察、内控评价、专项审计、离任审计、商业秘密和行为风险负责不同场景的调查分析；持续改善负责统一承接问题整改、复核和归档。

技术上，LangGraph Workflow Runtime 是唯一流程推进中心；Stage Agent 只生成结构化建议，不直接修改终态；RAG Orchestrator 统一完成混合检索、权限过滤、rerank 和引用追溯；Text2SQL Orchestrator 统一完成 DataQueryIntent、Data Catalog、Semantic Layer、Doris SQL 生成、AST 安全校验、HITL、只读执行和结果脱敏；RabbitMQ + Celery 承接长耗时任务；Outbox / Inbox 保证外部系统协同可追踪、可重试、可审计。

---

## 3. 最终生产架构怎么讲

面试时建议先讲“权威边界”，再讲技术栈。这样能体现你不是堆组件，而是在设计一个生产系统。

### 3.1 六个主运行层

Hermes 最终生产架构是 **6 个主运行层 + 3 个横切治理面**。

```text
接入与业务应用层
  -> 工作流运行层
  -> Agent 与模型能力层
  -> 知识检索、结构化数据查询与文档智能层
  -> 异步任务与事件集成层
  -> 数据与存储层

横切治理面：
  -> 安全与权限治理
  -> 可观测性与质量治理
  -> 平台与交付治理
```

各层职责：

- **接入与业务应用层**：Vue SPA、FastAPI、WebSocket、Webhook、审批界面、任务中心、文档管理、审计查询。
- **工作流运行层**：LangGraph Workflow Runtime，负责阶段路由、HITL 暂停 / 恢复、重试、人工接管和下游事件触发。
- **Agent 与模型能力层**：Model Gateway、Provider Adapter、Prompt Manager、Tool Registry、Memory、Evaluator，负责生成结构化建议和模型治理。
- **知识检索、结构化数据查询与文档智能层**：RAG Orchestrator、Text2SQL Orchestrator、Doris Adapter、Semantic Layer、Search Adapter、Milvus、OCR、ASR、rerank。
- **异步任务与事件集成层**：RabbitMQ quorum queues、Celery Worker、Outbox、Inbox、A2A Adapter、DLQ、KEDA。
- **数据与存储层**：PostgreSQL 保存业务事实、审计事实和 durable checkpoint；Redis 做热缓存、会话、限流；MinIO 存对象和报告；NAS 做冷归档。

### 3.2 六个权威域

这张表适合面试时拿来解释“为什么系统不会乱”：

| 权威域 | 负责什么 | 禁止什么 |
|---|---|---|
| LangGraph Workflow Runtime | 唯一流程推进、阶段路由、HITL、恢复、重试 | API、Worker、Agent 直接跳阶段 |
| PostgreSQL 业务事实库 | 案件、审批、任务、审计、Outbox/Inbox、durable checkpoint | 承担 10TB 级全文和向量主检索 |
| 检索与知识域 | ES/OpenSearch 全文检索，Milvus 向量检索，PG 保存知识元数据 | 业务 OLTP 和大规模检索混在一个库 |
| RabbitMQ + Celery | 长任务可靠投递、异步执行、重试、DLQ | 承载工作流语义或裁决案件终态 |
| Agent 与模型能力域 | 结构化建议、证据摘要、知识引用、下一步建议 | 直接修改业务终态或绕过 HITL |
| 事件集成域 | Adapter、Outbox、Inbox、Webhook 验签、幂等、审计 | 外部系统直接互写数据库 |

### 3.3 为什么这样分层

一句话总结：

> API 负责接入和命令受理，Workflow 负责状态推进，Agent 负责生成建议，RAG 和 Text2SQL 负责提供依据，Worker 负责长任务执行，PostgreSQL 负责事实和审计，外部系统通过事件契约协同。

这样做的好处：

- 状态推进有唯一权威，不会出现 API、Worker、Agent 各自改状态。
- RAG 和 Text2SQL 都是共享能力，不散落在各业务 Agent 里。
- 长耗时任务不会阻塞 API，也不会绕过 Workflow。
- 外部系统集成有 Outbox / Inbox、签名、幂等和审计。
- 安全、观测、质量治理可以贯穿所有层。

---

## 4. 端到端工作流怎么讲

建议按“一条风险线索从进入系统到闭环”的方式讲。

### 4.1 总体链路

```text
用户操作 / 风控系统推送
  -> API 创建案件和 task_id
  -> 附件上传到 MinIO
  -> 多模态 Worker 异步解析并写入 Search / Milvus
  -> WorkflowService 只创建 workflow 命令和业务事实
  -> LangGraph Workflow Runtime invoke / resume
  -> Stage Agent 执行阶段任务
      -> RAG 检索制度、案例、模板、证据
      -> Text2SQL 查询结构化数仓数据
      -> Tool 查询 OCR / ASR / 证据检索 / 文档生成
      -> LLM 生成结构化 stage_output
  -> 写入 durable checkpoint 和 case_stages
  -> interrupt_before 挂起等待 HITL
  -> 人工审批通过 / 修改 / 驳回
  -> Workflow Runtime resume
  -> 处置追责 / 外部系统协同 / 整改闭环
  -> audit_log 全链路留痕
```

### 4.2 线索和附件进入

线索来源包括：

- 风控系统按钮或 webhook 推送。
- 用户在案件工作台人工录入。
- 风险监控模块 7x24 扫描生成异常线索。

附件上传后不直接阻塞案件流程：

- 文件进入 MinIO。
- MinIO Bucket 事件进入 RabbitMQ。
- 音频走 Whisper ASR 和说话人分离。
- 图片走 PaddleOCR 和 CLIP 分类。
- 视频走 OpenCV 关键帧和场景分析。
- PDF / Office 走 unstructured.io 解析。
- 解析结果进入 Elasticsearch/OpenSearch 全文索引和 Milvus 向量索引。

### 4.3 廉洁监察 6 阶段流程

以廉洁监察为例：

```text
intake 初筛
  -> investigation 调查方案
  -> analysis 多维分析与报告
  -> disposition 处置分流
  -> enforcement 处罚执行
  -> post_report 报案后续协助
```

每个阶段的统一模式：

```text
读取 workflow state
  -> 读取案件事实和阶段目标
  -> 生成 RAG RetrievalIntent
  -> 需要结构化数据时生成 DataQueryIntent
  -> 调用 RAG / Text2SQL / Tool
  -> LLM 生成结构化建议
  -> Pydantic / Schema 校验
  -> 写 stage_output 和 citations / data_refs
  -> HITL 守门
  -> resume 到下一阶段
```

### 4.4 analysis 阶段为什么最能体现技术深度

`analysis` 阶段是面试里最值得重点讲的，因为它同时用到 RAG、Text2SQL、多模态证据和人工守门：

```text
analysis-agent
  -> RAG：检索制度、历史案例、调查报告模板、证据片段
  -> Text2SQL：查询供应商、采购、财务、员工行为等结构化数据
  -> Tool：查询 OCR / ASR / ES 全文证据 / Milvus 相似证据
  -> LLM：生成分析报告草稿、证据链、风险定性和不确定项
  -> HITL：人工查看引用、数据摘要、异常样本和结论
  -> disposition：进入处置分流
```

这里要强调：

- RAG 给出“制度和证据依据”。
- Text2SQL 给出“数据是否支持判断”。
- Agent 负责组合依据并生成结构化建议。
- HITL 决定是否采纳、修改或驳回。

### 4.5 enforcement 和外部系统协同

处罚执行阶段可能涉及 HR、法务、财务、OA、MDM 等系统。生产上不允许直接写外部系统：

- 所有外发事件先写 `event_outbox`。
- Adapter 从 Outbox 发布到外部系统或 A2A 智能体。
- 外部回调进入 `event_inbox`。
- Inbox 完成验签、去重、幂等和审计。
- Workflow Runtime 消费事件后恢复流程。

典型外部协同：

- A2A -> 龟宝：员工处罚。
- A2A -> 西塞罗：协议审核。
- A2A -> 波特：供应商扣款。
- MDM Adapter：黑名单同步。
- OA Adapter：处罚公告审批。

---

## 5. RAG 怎么讲

RAG 是第一个重点。不要只说“用了向量库”，要讲它在生产系统中的边界、流程、安全和质量。

### 5.1 RAG 的定位

RAG 在 Hermes 中不是主 Agent，而是全模块共享的 **RAG Orchestrator**。

它负责：

- 知识检索。
- 证据检索。
- 候选过滤。
- 结果融合和 rerank。
- 引用追溯。
- 上下文组装。
- diagnostics、trace、审计和质量反馈。

它不负责：

- 推进 workflow。
- 判断案件是否立案、处罚或关闭。
- 直接修改业务终态。
- 绕过 HITL。

### 5.2 RAG 调用链路

```text
Stage Agent / Conversation Gateway / Knowledge API
  -> Business Retrieval Adapter
  -> RetrievalIntent
  -> RAGRequest
  -> RAG Orchestrator
  -> 权限与知识范围解析
  -> 查询预处理
  -> Embedding
  -> Search Adapter 全文召回 + Milvus 向量召回
  -> 候选合并、去重、二次过滤
  -> Rerank 精排
  -> 引用校验
  -> 上下文压缩与组装
  -> RAGResponse(context + knowledge_refs + diagnostics)
  -> Stage Agent 生成业务建议
```

### 5.3 Business Retrieval Adapter 的价值

业务 Agent 不应该直接把原始举报全文丢给 RAG。中间要有业务检索适配层，把业务输入变成标准检索意图。

适配层做几件事：

- `CaseInputNormalizer`：标准化举报正文、案件字段、附件摘要、证据引用。
- `BusinessFactExtractor`：抽取主体、组织、供应商、金额、时间、系统、附件类型。
- `RiskScenarioClassifier`：识别利益输送、围标串标、价格异常、关联关系、内控缺陷等场景。
- `IntentTemplateRegistry`：按 `module + stage + intent` 管理检索模板。
- `RetrievalIntentBuilder`：生成业务主检索问题、风险标签、所需知识源和证据边界。
- `RAGRequestAssembler`：合并权限上下文、证据引用、trace_id 和 schema_version。

这层的核心价值：

> Stage Agent 负责业务理解，RAG Orchestrator 负责检索执行。RAG 可以做查询改写和子查询扩展，但不能改变业务意图或扩大权限范围。

### 5.4 RAG 内部 13 步流程

面试里可以压缩成这 13 步：

1. **基础校验**：校验 `query`、`module`、`stage`、`tenant_scope`、`trace_id`。
2. **权限与知识范围解析**：根据模块、阶段、租户、组织、角色、密级计算可检索范围。
3. **查询预处理**：去噪、脱敏、识别 Prompt 注入和越权意图。
4. **Embedding 向量化**：对标准 query 和子查询生成 embedding。
5. **双路召回**：Search Adapter 走 Elasticsearch/OpenSearch 全文检索，Milvus 走向量召回。
6. **融合去重**：用 `doc_id + version_id + chunk_id` 去重，用 RRF 或加权融合生成 `fusion_score`。
7. **二次硬过滤**：过滤跨租户、跨密级、未审核、已废止、当前阶段不可用候选。
8. **Rerank 精排**：用领域 reranker 对融合候选排序。
9. **引用校验**：校验 `doc_id`、`chunk_id`、版本、生效状态、来源路径、页码或段落。
10. **上下文压缩与组装**：只把必要片段注入 LLM，不把完整文档塞进 Prompt。
11. **质量判定**：标记 `knowledge_insufficient`、低相关、引用不足、降级等情况。
12. **观测和安全日志**：记录 query hash、召回数、过滤数、返回引用、blocked_candidates。
13. **反馈闭环**：根据人工采纳、驳回、补充知识更新检索质量和评测集。

### 5.5 生产检索架构

生产环境中，RAG 的主检索负载不放在业务库里：

- **Elasticsearch/OpenSearch**：中文全文检索、BM25、过滤、聚合、审计检索。
- **Milvus Distributed**：知识库、证据、历史案例的大规模向量召回，collection 按模块和租户隔离。
- **PostgreSQL**：保存知识元数据、索引版本、审批状态、业务事实，不承担 10TB 级主检索负载。
- **Reranker**：负责二阶段精排，提高 Top K 引用质量。

一句话：

> PostgreSQL 是事实和元数据权威，Elasticsearch/OpenSearch 是全文检索域，Milvus 是语义向量检索域，RAG Orchestrator 是统一编排入口。

### 5.6 RAG 的安全和质量

RAG 的核心风险有三个：幻觉、越权、引用不可信。

对应方案：

- **防幻觉**：Stage Agent 必须基于 `knowledge_refs` 输出结论；引用不足时返回 `knowledge_insufficient=true`。
- **防越权**：检索前 metadata filter，召回后二次硬过滤，跨租户、跨密级候选不能进入 Prompt。
- **防引用伪造**：每条结果必须可追溯到 `doc_id`、`chunk_id`、版本、生效状态、source_path 或页码。
- **防 Prompt 注入**：识别“忽略权限”“显示全部资料”“绕过审计”等注入指令。
- **质量评测**：建立 RAG eval，关注召回率、MRR、nDCG、引用采纳率、越权召回率、blocked candidate recall、rerank latency。

---

## 6. Text2SQL 怎么讲

Text2SQL 是第二个重点。它解决的是“自然语言如何安全查询结构化业务数据”。

### 6.1 Text2SQL 的定位

Hermes 中各模块都有自然语言查数仓的需求：

- 风险监控：风险规则 SQL 生成、批量扫描、误报分析。
- 廉洁监察：供应商、员工、采购、招投标、费用、财务数据核验。
- 内控评价：样本抽取、控制执行记录核对、异常交易筛选。
- 专项审计：审计主题下的数据抽样、穿行测试、异常明细查询。
- 离任审计：任期内关键业务数据、费用、权限、行为记录查询。
- 行为风险：员工行为日志、系统访问、异常行为查询。
- 持续改善：整改证据、逾期问题、复发问题统计。

所以 Text2SQL 不能散落在各 Agent 里，而是抽象为统一的 **Text2SQL Orchestrator**。

### 6.2 Text2SQL 和 RAG 的区别

| 能力 | 查询对象 | 输出 | 是否查询数仓 |
|---|---|---|---|
| RAG Orchestrator | 制度、案例、模板、报告、数据字典文档、字段口径说明 | 知识片段、上下文、知识引用 | 否 |
| Text2SQL Orchestrator | 结构化业务数据、数仓明细、指标聚合、异常样本 | SQL、结果摘要、数据引用 | 是，只读 |

一句话：

> RAG 解决“依据从哪里来”，Text2SQL 解决“数据是否支持这个判断”。

### 6.3 Text2SQL 总流程

```text
Stage Agent / Conversation Gateway / Data Query API
  -> Text2SQL Orchestrator
  -> 权限与数据域解析
  -> DataQueryIntent 解析和校验
  -> Data Catalog + RAG 数据字典检索
  -> Semantic Layer / Metric Registry 口径匹配
  -> Schema 路由与缺口判断
  -> 查询计划生成
  -> Doris SQL 生成
  -> SQL AST 安全校验
  -> 策略注入与 SQL 改写
  -> 二次 AST 校验
  -> EXPLAIN / 成本评估
  -> HITL 门禁
  -> 只读数仓执行
  -> 结果脱敏、摘要、data_refs
  -> diagnostics、trace、审计与反馈闭环
```

### 6.4 DataQueryIntent 是关键

Text2SQL 不是“用户一句话 + 全量 Schema -> 生成 SQL”。Stage Agent 发送给 Text2SQL 的核心对象是 `DataQueryIntent`。

`DataQueryIntent` 包含：

- `intent_type`：明细查询、聚合统计、异常筛选、趋势分析、主体关联、指标核对。
- `entities`：供应商、员工、客户、项目、合同、单据、组织，优先使用主数据 ID。
- `metrics`：中标次数、中标金额、预算接近度、异常付款金额、费用报销金额。
- `dimensions`：供应商、员工、部门、项目、月份、业务循环。
- `time_range`：起止时间；大表明细查询没有时间范围必须追问或进入 HITL。
- `filters`：业务过滤条件和阈值，使用业务别名而不是物理字段名。
- `grain`：统计粒度，例如按供应商、按员工、按项目、按天。
- `output_preference`：聚合摘要、异常样本、明细列表、趋势序列。
- `missing_slots` / `ambiguous_entities`：缺失槽位和歧义主体。

为什么要有它：

- 防止模型凭一句自然语言猜表。
- 让业务意图、权限范围、指标口径、审计记录都有结构化边界。
- 低置信度、缺少时间范围、主体歧义时，系统可以追问，而不是硬生成 SQL。

### 6.5 Schema 路由和缺口判断

生产 Text2SQL 不能让 LLM 直接猜 Schema。必须先做 Schema 路由：

1. 根据 `module + stage + caller_agent` 读取 Module Agent Profile，确认当前阶段可用数据域和工具。
2. 将请求 `data_scope` 与 Profile 授权、用户角色、组织、密级策略取交集。
3. 对 `entities` 做主数据解析，例如供应商名称映射到 `supplier_id`。
4. 用 `metrics` 和 `dimensions` 查询 Semantic Layer / Metric Registry，获得候选事实表、维表、时间字段、默认过滤和 join path。
5. 用 `intent_type` 和 `filters` 查询 Data Catalog 的业务标签、字段别名、中文名、数据等级和分区键。
6. 用 RAG 检索数据字典、历史规则和字段口径文档。
7. 对候选 Schema 按数据域匹配、实体覆盖、指标覆盖、维度覆盖、时间可控、权限可控、口径可信、成本可控打分。
8. 只把最终授权的最小表集合、字段、口径说明和 join path 注入 SQL 生成 Prompt。

如果这些条件不满足，返回 `schema_insufficient=true`：

- 缺少关键实体、时间范围、指标或维度。
- 候选表过多且评分接近。
- Metric Registry 找不到指标口径。
- 实体解析失败。
- 找不到可信 join path。
- Data Catalog 与 Semantic Layer 冲突。
- 需要访问的表或字段不在当前阶段授权范围内。
- 大表明细查询缺少时间或分区过滤。

### 6.6 Semantic Layer / Metric Registry

这是 Text2SQL 最容易被追问的点。

生产 Text2SQL 不能只依赖物理字段，否则容易生成“能跑但口径错”的 SQL。Hermes 维护语义层：

- **Metric**：中标金额、预算金额、费用报销金额、异常访问次数。
- **Dimension**：供应商、员工、部门、事业部、业务循环、系统。
- **Grain**：按人、按供应商、按单据、按天、按月。
- **Default Filter**：只取有效订单、已审批单据、未作废记录。
- **Join Path**：事实表与维表的可用关联路径。
- **Semantic Version**：指标定义、生效时间、废止时间、owner 和审批记录。

原则：

- 涉及金额、频次、比例、风险率时必须引用 Metric Registry。
- 语义层没有定义的指标不能自动编造口径。
- Agent 最终报告引用数据时必须带 `semantic_version`。

### 6.7 SQL 安全链路

Text2SQL 的安全链路要讲完整：

1. 生产数仓固定对接 Doris，只生成 Doris / MySQL 兼容 SQL。
2. Prompt 只注入授权 Schema、字段口径、查询计划和安全规则。
3. SQL 必须是单条 `SELECT` 或只读 CTE。
4. 第一次 AST 校验拒绝 DDL、DML、多语句、系统库、导入导出、UDF、外部访问、未授权表字段。
5. 策略注入租户、组织、密级、行列级过滤、敏感字段脱敏、`LIMIT`、时间分区条件。
6. 第二次 AST 校验确认改写后 SQL 仍是单条只读查询，且策略没有被移除。
7. Doris `EXPLAIN` 做成本评估，检查分区裁剪、扫描行数、join、shuffle、窗口函数和返回数据量。
8. 高风险查询进入 HITL，审批绑定 `query_id`、最终 SQL hash、catalog_version、semantic_version、policy_version。
9. `execute_readonly` 只能执行审批记录绑定的最终 SQL hash。
10. 返回前做结果脱敏、摘要和 `data_refs`，高敏明细不直接注入 LLM。

### 6.8 Text2SQL 的结果如何被 Agent 使用

Text2SQL 返回的不是“案件结论”，而是可追溯数据依据：

- `summary`：脱敏后的聚合摘要。
- `rows_sample`：必要时返回脱敏异常样本。
- `data_refs`：结果快照、查询 ID、SQL hash、审批记录、数据源、版本信息。
- `diagnostics`：schema_insufficient、permission_denied、sql_validation_failed、cost_too_high、human_review_required、result_truncated。
- `semantic_version`：指标口径版本。

Stage Agent 只能基于这些结果写：

- 数据支持什么。
- 数据不能证明什么。
- 还缺哪些事实。
- 结论置信度如何。

不能把 Text2SQL 查询失败、无结果或 schema 不足解释成确定事实。

---

## 7. RAG + Text2SQL 在业务中的组合讲法

面试官如果问“这两个能力怎么一起用”，可以按廉洁监察 `analysis` 阶段讲。

### 7.1 一个供应商舞弊分析示例

业务问题：

> 某采购经理长期指定供应商 A 中标，报价接近预算上限，且举报材料称二者存在亲属关系，如何判断是否存在廉洁风险？

系统处理：

```text
analysis-agent
  -> RAG:
      检索采购制度、供应商关联关系回避制度、历史舞弊案例、调查报告模板
  -> Text2SQL:
      生成 DataQueryIntent
      查询供应商 A 中标次数、预算接近度、异常付款、相关员工参与项目记录
  -> Tool:
      查询 OCR 合同、报价单、访谈 ASR、历史证据全文
  -> Agent:
      汇总制度依据、历史案例、结构化数据摘要和证据片段
  -> HITL:
      人工查看引用、SQL hash、数据摘要、异常样本和不确定性
  -> disposition:
      进入处置分流
```

### 7.2 这个例子体现的价值

- RAG 解决制度和案例依据。
- Text2SQL 解决数据是否异常。
- 多模态处理解决非结构化证据提取。
- LangGraph 解决阶段推进和恢复。
- HITL 解决高风险判断的责任边界。
- audit_log、knowledge_refs、data_refs 解决事后追溯。

---

## 8. 项目难点和解决办法

### 难点 1：长流程状态权威如何保证

**背景**：风控案件不是一次问答，而是跨多个阶段、跨多天甚至跨多周的业务流程。
**难点**：API、Agent、Worker、外部系统都可能触发动作，如果没有唯一状态权威，案件状态会混乱。
**方案**：

- LangGraph Workflow Runtime 是唯一流程推进中心。
- API 只创建命令和业务事实，不直接跳阶段。
- Worker 只写任务结果并发布事件，不裁决业务终态。
- 外部回调进入 Inbox 后由 Workflow Runtime 恢复流程。
- PostgreSQL durable checkpoint 保存 workflow state，Redis 只做热缓存。

**结果**：流程可暂停、可恢复、可驳回重跑、可人工接管，并且所有阶段推进都有审计链。

### 难点 2：RAG 如何防幻觉和防越权

**背景**：风控和审计场景不能让大模型编制度、编案例、编法律依据。
**难点**：既要召回相关知识，又不能跨租户、跨密级、跨案件泄露。
**方案**：

- RAGRequest 必须携带 `module`、`stage`、`tenant_scope`、`trace_id`。
- 检索前按租户、组织、角色、密级、阶段、审批状态做 metadata filter。
- 召回后做二次硬过滤，外部索引返回的越权候选也不能进入 Prompt。
- 每条引用必须绑定 `doc_id`、`chunk_id`、版本、来源路径、页码或段落。
- 知识不足时返回 `knowledge_insufficient=true`，Agent 必须降低置信度或转人工。

**结果**：AI 输出从“凭模型记忆”变成“带引用的建议”，越权召回率必须为 0。

### 难点 3：Text2SQL 如何避免“能跑但口径错”

**背景**：SQL 能执行不代表业务口径正确。比如“中标金额”“预算接近度”“异常付款”都有特定定义。
**难点**：自然语言容易让模型猜表、猜字段、猜指标口径。
**方案**：

- Stage Agent 先生成 `DataQueryIntent`，明确意图、主体、指标、维度、时间范围、粒度和输出偏好。
- Text2SQL 做 Schema 路由，不能让 LLM 直接猜 Schema。
- Data Catalog 提供表字段、数据等级、分区、owner。
- Semantic Layer / Metric Registry 提供指标表达式、默认过滤、join path 和语义版本。
- 口径不足时返回 `schema_insufficient=true`，不得生成高风险 SQL。

**结果**：Text2SQL 不只是生成 SQL，而是生成“有权限、有口径、有版本、有审计”的受控查询。

### 难点 4：Text2SQL 如何安全执行

**背景**：Text2SQL 直接接触结构化业务数据，风险高于普通问答。
**难点**：要防止越权查询、SQL 注入、大表扫描、敏感数据泄露。
**方案**：

- 生产固定 Doris 方言，只允许单条 `SELECT` 或只读 CTE。
- 使用 SQL AST 校验，不依赖字符串黑名单。
- 策略注入租户、组织、密级、字段脱敏、`LIMIT`、时间分区。
- 改写后做第二次 AST 校验。
- 执行前用 Doris `EXPLAIN` 做成本评估。
- 高风险查询进入 HITL，审批绑定最终 SQL hash。
- 结果返回前脱敏、摘要和生成 `data_refs`。

**结果**：自然语言不能绕过权限直接查数仓，所有执行都可追踪、可审批、可回放。

### 难点 5：10TB 文档和证据如何检索

**背景**：系统管理约 10TB 文档、音频、视频、图像、PDF、Office 等证据材料。
**难点**：不能让业务库同时承担 OLTP、审计、全文检索和向量检索。
**方案**：

- PostgreSQL 保存业务事实、审计事实、知识元数据和索引版本。
- Elasticsearch/OpenSearch 承载全文检索和审计检索。
- Milvus Distributed 承载大规模向量召回。
- MinIO 保存对象文件和报告。
- 多模态 Worker 异步解析文件，处理结果进入 Search 和 Milvus。
- RAG Orchestrator 统一编排召回、融合、rerank 和引用校验。

**结果**：业务写入、审计查询、全文检索、向量召回各自扩展，避免单库承压。

### 难点 6：AI 自动化和人工责任边界如何划分

**背景**：风控场景涉及处罚、扣款、拉黑、移交、报案、机密下载等高风险动作。
**难点**：既要提升效率，又不能让 AI 越权执行。
**方案**：

- Agent 只生成结构化建议、证据摘要、知识引用、数据引用和下一步建议。
- HITL 负责关键节点审批、修改和驳回。
- 高风险动作必须进入人工守门，并写入 audit_log。
- 外部系统写操作走 Outbox / Inbox 和 Adapter，不允许 Agent 直接写。
- 低风险任务可以自动化，如检索、草稿、摘要、提醒；高风险任务必须审批。

**结果**：AI 提效，人类负责，系统有完整责任链。

### 难点 7：外部系统一致性如何保证

**背景**：系统要与风控、OA、MDM、HR、法务、财务和 A2A 智能体协作。
**难点**：外部调用可能失败、重复、延迟、回调异常。
**方案**：

- 所有外发事件先写 Outbox。
- 所有外部回调先进 Inbox。
- 消息带 `schema_version`、`trace_id`、`correlation_id`、`idempotency_key`。
- 回调必须验签、去重、审计。
- RabbitMQ 负责可靠投递、重试和 DLQ。
- Workflow Runtime 根据事件恢复节点。

**结果**：即使外部系统重试、延迟或重复回调，系统也能最终一致并可审计。

### 难点 8：如何衡量 Agent 效果

**背景**：AI 系统不能只看“能不能回答”，要看业务质量、检索质量、SQL 质量和安全质量。
**方案**：

- RAG 指标：召回率、MRR、nDCG、引用采纳率、越权召回率、rerank latency。
- Text2SQL 指标：SQL 可执行率、语义正确率、权限拦截率、AST 校验失败率、HITL 驳回率、结果脱敏正确率。
- Workflow 指标：阶段通过率、人工驳回率、节点重试率、恢复耗时。
- 业务指标：线索初筛准确率、调查方案采纳率、报告采纳率、整改闭环率、误报回流率。
- 观测链路：OpenTelemetry trace_id 贯穿 API、Workflow、Worker、LLM、RAG、Text2SQL、Tool 和外部系统。

**结果**：质量治理从“线上感觉”变成可评测、可回放、可灰度、可回滚。

---

## 9. 项目亮点

### 9.1 不是聊天机器人，而是生产工作流系统

Hermes 的核心是有状态、多阶段、可暂停、可恢复、可审计的工作流。LLM 只是一个能力组件，不是状态权威。

### 9.2 Workflow Runtime 权威清晰

LangGraph Workflow Runtime 是唯一流程推进中心。API、Agent、Worker、外部系统都通过命令、事件或审批结果与它协作。

### 9.3 RAG 做成共享 Orchestrator

所有模块统一走 RAG Orchestrator，复用同一套权限过滤、混合召回、RRF、rerank、引用校验、diagnostics 和安全策略。

### 9.4 Text2SQL 是受控数据查询链路

Text2SQL 不是“自然语言直接跑 SQL”，而是 DataQueryIntent、Schema 路由、Semantic Layer、Doris SQL、AST 校验、策略注入、HITL、只读执行和脱敏引用的完整链路。

### 9.5 RAG 和 Text2SQL 分工清楚

RAG 管文档、制度、案例、证据和字段口径文档；Text2SQL 管结构化数仓、指标聚合和异常样本。二者都给 Agent 提供依据，但都不直接裁决业务终态。

### 9.6 安全和审计是内建能力

RBAC、RLS、密级、字段加密、对象加密、短期预签名 URL、Webhook 验签、Outbox / Inbox、append-only audit_log、HITL 都是主流程设计的一部分。

### 9.7 面向 10TB 数据规模设计

业务事实库、全文检索、向量检索、对象存储和冷归档物理分离，避免单一 PostgreSQL 承担所有负载。

### 9.8 可观测性贯穿全链路

OpenTelemetry 统一 trace，Prometheus/Grafana 看指标，LangFuse 看模型调用和 Prompt，Jaeger/Tempo 看链路，结构化日志做审计和排障。

---

## 10. 生产后持续优化方向

这一部分按生产后的持续治理和优化来讲。

### 10.1 RAG 持续优化

- 优化分块策略：制度条款、案例事实、证据片段、报告模板采用不同 chunk 规则。
- 建立 RAG Golden Set，持续评估召回、排序、引用、权限和降级行为。
- 引入 citation verifier，校验 Agent 结论是否真的被引用支撑。
- 优化 reranker profile，不同模块和阶段使用不同权重。
- 监控越权候选、blocked candidates、knowledge_insufficient 和引用采纳率。

### 10.2 Text2SQL 持续优化

- 扩充 Data Catalog 和 Semantic Layer 覆盖率。
- 建立风控指标库和 Metric Registry owner 审批流程。
- 对高频风险规则 SQL 做计划回归，防止 Doris 执行成本退化。
- 建立 Text2SQL eval，覆盖语义正确、SQL 可执行、权限负例、脱敏正确和成本阈值。
- 引入查询模板和规则 SQL 库，提高高频场景稳定性。

### 10.3 Workflow 持续优化

- 优化 durable checkpoint 查询性能和归档策略。
- 对长暂停 HITL 做恢复演练，验证 24 小时或更长暂停后精确恢复。
- 细化节点级重试、补偿和人工接管策略。
- 对 Outbox / Inbox 做积压监控和重放工具。

### 10.4 成本和性能优化

- 对 RAG、Text2SQL、LLM、OCR、ASR 分别设置成本预算和限流。
- 对高频 query、embedding、rerank 和 Text2SQL Schema 路由做缓存。
- 对 Worker 按任务类型拆池，使用 KEDA 根据队列积压扩缩容。
- 对大文件使用预览、分页、HLS、Range 下载和 CDN 缓存。

### 10.5 安全和合规优化

- 持续做 Prompt 注入、RAG 越权、Text2SQL 越权、Tool 越权红队测试。
- 对敏感字段、文件下载、机密数据查询增加二次审批和水印。
- 定期演练密钥轮换、灾备恢复、数据库迁移回滚和外部系统失败恢复。
- 审计日志分区归档，保证可搜索、不可篡改、可长期保存。

---

## 11. 高频追问答案

### Q1：这个项目到底解决什么问题？

回答：

> 解决企业风控从被动、分散、依赖个人经验，走向主动发现、智能分析和闭环治理的问题。风险监控负责发现异常，各业务模块负责分析处置，持续改善负责整改闭环。AI 不是替代风控人员，而是把制度、案例、数据、证据和报告生成能力嵌入到可审计的工作流里。

### Q2：为什么用 LangGraph？

回答：

> 因为 Hermes 是多阶段、有状态、有条件路由、有人工守门、有恢复需求的 AI 工作流。LangGraph 支持 state、checkpoint、interrupt/resume 和条件路由，更适合 LLM Agent 场景。Temporal 更偏传统长事务编排，RabbitMQ/Celery 只负责任务执行，不承载工作流语义。生产上 LangGraph Workflow Runtime 是唯一流程推进中心。

### Q3：RAG 是怎么做的？

回答：

> RAG 是统一 RAG Orchestrator。Stage Agent 先通过业务检索适配层生成 RetrievalIntent，再组装 RAGRequest。RAG 内部做权限范围解析、查询预处理、Embedding、ES/OpenSearch 全文召回、Milvus 向量召回、RRF 融合、二次硬过滤、rerank、引用校验和上下文组装。每条结果必须带 doc_id、chunk_id、版本和来源，知识不足会显式返回 knowledge_insufficient。

### Q4：为什么不用单纯向量库？

回答：

> 单纯向量库解决不了中文关键词精确匹配、制度条款编号、租户和密级过滤、版本生效状态、引用追溯和审计检索。生产上需要 ES/OpenSearch 承载全文和过滤，Milvus 承载大规模向量召回，PostgreSQL 存元数据和版本，由 RAG Orchestrator 做统一融合和安全过滤。

### Q5：Text2SQL 是怎么做的？

回答：

> Text2SQL 是统一 Orchestrator，不允许 Agent 自己拼 SQL。Stage Agent 先生成 DataQueryIntent，包含查询类型、主体、指标、维度、时间范围、过滤条件、粒度和输出偏好。Text2SQL 再结合 Module Profile、权限、Data Catalog、Semantic Layer、RAG 数据字典做 Schema 路由和缺口判断，之后生成 Doris SQL，经过 AST 校验、策略注入、二次 AST 校验、EXPLAIN、HITL 审批后，只读执行并返回脱敏摘要和 data_refs。

### Q6：Text2SQL 最大风险是什么？

回答：

> 最大风险不是 SQL 语法错误，而是越权查询、口径错误、大表扫描和敏感数据泄露。所以系统不让模型直接猜全量 Schema，而是先做 DataQueryIntent 和 Schema 路由；不只看 SQL 能不能跑，还要看指标口径、权限、成本和脱敏。所有高风险查询必须 HITL，审批绑定最终 SQL hash。

### Q7：RAG 和 Text2SQL 怎么配合？

回答：

> RAG 提供制度、案例、模板、证据和字段口径文档；Text2SQL 提供结构化业务数据摘要和 data_refs。比如供应商舞弊分析里，RAG 查采购制度和相似案例，Text2SQL 查供应商中标次数、预算接近度和异常付款，Agent 再把知识引用、数据引用、证据引用汇总成结构化报告，最后由人工守门。

### Q8：如何防止大模型幻觉？

回答：

> 四层控制：第一，RAG 和 Text2SQL 提供可追溯依据；第二，Agent 输出结构化 Schema，必须写引用、不确定因素和缺失事实；第三，知识不足、Schema 不足、SQL 失败、依赖降级时显式降低置信度或转人工；第四，高风险结论必须 HITL，不能自动执行。

### Q9：人工审批和自动化边界在哪里？

回答：

> 检索、摘要、报告草稿、低风险提醒可以自动化；处罚、移交、扣款、拉黑、机密下载、敏感 SQL 执行、外部系统写入必须 HITL。AI 负责生成建议和材料，人类负责确认高风险动作，系统负责审计和追溯。

### Q10：外部系统怎么保证一致性？

回答：

> 所有外发事件先写 Outbox，所有回调先写 Inbox。事件带 schema_version、trace_id、correlation_id、idempotency_key 和签名。RabbitMQ 负责可靠投递、重试和 DLQ。外部回调验签、去重、审计后，由 Workflow Runtime 恢复流程。这样即使外部系统重复回调或延迟，也能最终一致。

### Q11：10TB 文档证据怎么处理？

回答：

> 文件对象存在 MinIO，冷数据归档到 NAS；音频、图像、视频、文档分别由异步 Worker 解析；解析结果进入 ES/OpenSearch 全文索引和 Milvus 向量索引；PostgreSQL 只保存业务事实、审计事实、知识元数据和索引版本。这样 OLTP、全文检索、向量检索和对象存储各自扩展。

### Q12：这个项目最有亮点的地方是什么？

回答：

> 最大亮点是把 AI 能力生产化：Workflow 管状态，RAG 管知识依据，Text2SQL 管数据依据，HITL 管风险边界，Outbox/Inbox 管外部一致性，OpenTelemetry/LangFuse 管观测评测，audit_log 管合规追溯。它不是单点模型调用，而是一套企业级 AI 风控运行架构。

---

## 12. 最后一页速记

### 一句话

Hermes 是企业风控 AI 智能体平台，用 LangGraph 编排流程，用 RAG 提供知识和证据依据，用 Text2SQL 提供结构化数据依据，用 HITL 控制高风险动作，最终形成风险发现、调查分析、处置追责和整改闭环。

### 三个关键词

- **有状态工作流**：LangGraph Workflow Runtime 是唯一流程推进中心。
- **双依据增强**：RAG 查知识和证据，Text2SQL 查结构化业务数据。
- **人机协同闭环**：AI 生成建议，人工确认高风险动作，审计全链路留痕。

### 五个亮点

- 6 个主运行层 + 3 个横切治理面的生产架构。
- RAG Orchestrator 统一检索、权限、融合、rerank、引用和 diagnostics。
- Text2SQL Orchestrator 统一 DataQueryIntent、Schema 路由、Semantic Layer、Doris SQL、AST 校验、HITL 和只读执行。
- Outbox / Inbox + A2A Adapter 保证外部系统协同可追踪、可重试、可审计。
- OpenTelemetry、Prometheus、LangFuse、Jaeger/Tempo 贯穿 API、Workflow、Worker、LLM、RAG、Text2SQL 和外部系统。

### 六个难点

- 长流程状态权威和 durable checkpoint。
- RAG 幻觉、越权召回和引用真实性。
- Text2SQL 语义口径、SQL 安全、权限和成本控制。
- 10TB 多模态证据的全文和向量检索。
- 高风险动作的 HITL 和责任边界。
- 外部系统 Outbox / Inbox、幂等、签名和最终一致性。

### 最稳妥收尾

> 这个项目最重要的工程价值是：它没有把 AI 当成一个孤立模型，而是把模型放进企业级风控运行体系里。RAG 让结论有知识和证据来源，Text2SQL 让判断有结构化数据依据，Workflow 保证状态可恢复，HITL 保证高风险动作有人负责，审计和观测保证系统可追溯、可治理、可持续优化。
