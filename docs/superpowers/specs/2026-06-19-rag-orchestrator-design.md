# RAG Orchestrator 重写与知识上传 — 设计规格

> **日期**：2026-06-19
> **依据文档**：`doc/agents/10-rag-shared-agent.md`
> **涉及模块**：RAG Engine、知识库 API、文档入库流水线

---

## 一、目标

1. **检索重写**：基于 `10-rag-shared-agent.md` 的 13 步流水线，实现完整 `RAGOrchestrator.retrieve()` 方法，返回标准 RAG 响应契约。
2. **文档上传**：实现知识库文档上传 → 解析 → 分块 → 向量化 → 入库的完整流水线。

---

## 二、文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `hermes/agents/rag_engine.py` | **重写** | 保留旧 `RAGEngine` + 新增 `RAGOrchestrator` |
| `hermes/agents/rag_schemas.py` | **新增** | 请求/响应 Pydantic 模型 |
| `hermes/agents/base.py` | **修改** | `BaseStageAgent` 支持新 `retrieve()` 调用 |
| `hermes/services/__init__.py` | **修改** | 导出 knowledge_ingestion 服务 |
| `hermes/services/knowledge_ingestion.py` | **新增** | 文档上传→解析→分块→向量化→入库流水线 |
| `hermes/api/v1/knowledge.py` | **重写** | 新增上传、retrieve、文档详情等端点 |
| `hermes/db/models/knowledge.py` | **修改** | 扩展字段以支持完整元数据 |
| `hermes/core/exceptions.py` | **修改** | 新增 RAG 相关异常类 |
| `hermes/core/config.py` | **修改** | 新增加载/分块相关配置项 |
| `alembic/versions/003_*` | **新增** | 知识库表扩展迁移 |
| `doc/agents/10-rag-shared-agent.md` | **修改** | 与实现对齐的更新 |

---

## 三、RAGOrchestrator 设计

### 3.1 与旧 RAGEngine 的兼容

- 旧 `RAGEngine.search()` 和 `RAGEngine.get_retrieval_context()` **行为不变**，现有 8 个模块 Stage Agent 不受影响。
- 新 `RAGOrchestrator` 在同一个文件中，提供 `retrieve()` 方法。
- Stage Agent 逐步迁移至 `retrieve()`，由各模块 owner 自行决定节奏。

### 3.2 13 步流水线

```
retrieve(RAGRequest) → RAGResponse

S1  请求校验        — Pydantic 自动校验 + role/scope 存在性检查
S2  权限解析        — 合并 Profile + tenant_scope + kb_types → metadata_filter
S3  查询预处理      — 清洗 → 脱敏 → 子查询生成
S4  Embedding       — 调用 Embedding API + 短期缓存
S5  双路召回        — pgvector 语义 + ILIKE 全文 (并行)
S6  合并去重+融合   — doc_id+chunk_index 去重 + RRF 融合
S7  二次硬过滤      — 内存级权限/密级/状态检查
S8  Rerank          — 当前用融合分数; 预留 RerankerAdapter
S9  引用校验        — doc_id/chunk_id/source_path 完整性
S10 上下文组装      — 压缩为 LLM Prompt 注入格式
S11 质量诊断        — knowledge_insufficient / degraded / reasons
S12 观测日志        — trace_id / latency / blocked / 脱敏 query
S13 反馈闭环        — 预留 feedback() 接口
```

### 3.3 请求契约 (RAGRequest)

```python
class RAGRequest(BaseModel):
    query: str                                    # 必填
    module: str                                   # 必填
    stage: str                                    # 必填
    tenant_scope: TenantScope                     # 必填: client, org_ids, role, security_levels
    trace_id: str                                 # 必填
    workflow_thread_id: str = ""
    case_id: str = ""
    kb_types: list[str] | None = None             # 可选，不传用 Profile 范围
    knowledge_scope: list[str] | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    mode: Literal["hybrid", "semantic", "keyword"] = "hybrid"
    evidence_refs: list[str] = []
```

### 3.4 响应契约 (RAGResponse)

```python
class RAGResponse(BaseModel):
    results: list[RAGResult]
    context: str
    knowledge_refs: list[str]
    diagnostics: RAGDiagnostics

class RAGResult(BaseModel):
    doc_id: str
    chunk_id: str
    kb_type: str
    title: str
    content_snippet: str
    relevance: float
    source_path: str | None
    metadata: dict
    retrieval: RetrievalDetail  # channels, scores

class RAGDiagnostics(BaseModel):
    recall_mode: str
    query_count: int
    search_latency_ms: int
    vector_latency_ms: int
    rerank_latency_ms: int
    total_latency_ms: int
    degraded: bool
    degrade_reasons: list[str]
    embedding_unavailable: bool
    reranker_unavailable: bool
    knowledge_insufficient: bool
    blocked_candidates: int
    suggested_actions: list[str] = []
```

### 3.5 权限过滤链

三层过滤，目标越权召回率 0：

1. **检索前**：`metadata_filter` 注入 SQL WHERE 条件（kb_type, is_active, client, org_id, security_level）
2. **检索中**：SQL 查询带 filter，避免返回越权行
3. **检索后**：内存级二次硬过滤（防范索引延迟/脏数据），丢弃的候选计入 `blocked_candidates`

### 3.6 降级路径

| 失败点 | 降级方式 |
|--------|----------|
| Embedding API 不可用 → | 跳过向量召回，仅 ILIKE，`embedding_unavailable=true` |
| PGVector 不可用 → | ILIKE 兜底 |
| 全部召回失败 → | 返回空结果 + `knowledge_insufficient=true` |
| 权限过滤后无结果 → | 返回知识不足，拒绝扩大权限 |

---

## 四、知识上传流水线设计

### 4.1 整体流程

```
POST /knowledge-bases/{kb_type}/upload  (multipart/form-data)
  → S1 文件接收与校验 (格式/大小/病毒扫描预留)
  → S2 内容解析 (txt/md/json 直接读; docx→python-docx; pdf→PyPDF2)
  → S3 文本清洗 (去噪声/规范化空白)
  → S4 语义分块 (~1000 字符, overlap ~200; 按段落/章节边界)
  → S5 content_hash 去重检查 (sha256)
  → S6 元数据标注 (kb_type, client, org_id, security_level, source_path)
  → S7 Embedding 向量化 (批量调用 Embedding API)
  → S8 写入 knowledge_documents (逐 chunk 写入)
  → S9 返回入库报告
```

### 4.2 支持的文件格式

- `.txt` / `.md` — 直接读取
- `.json` — 结构化知识条目（含 title + content）
- `.docx` — python-docx 解析
- `.pdf` — PyPDF2 解析
- 预留：`.xlsx`, `.pptx`, 图片 OCR, 音频 ASR

### 4.3 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/knowledge-bases/{kb_type}/upload` | 上传文件（multipart，支持批量） |
| `POST` | `/knowledge-bases/{kb_type}/upload-text` | 上传纯文本知识条目（JSON body） |
| `POST` | `/knowledge-bases/retrieve` | 完整 RAG 检索（新契约） |
| `GET` | `/knowledge-bases/{kb_type}/documents/{doc_id}` | 文档详情 + chunk 列表 |
| `POST` | `/knowledge-bases/feedback` | 检索反馈（预留） |

### 4.4 分块规则

- 默认：~1000 字符/块，overlap ~200 字符
- 按段落边界切分，保持语义完整
- 每个 chunk 记录：chunk_index, total_chunks, content_hash, section_path
- 制度法规类文档保留 "章/节/条" 层级信息

### 4.5 数据库扩展

`knowledge_documents` 表需要扩展字段以支持文档级元数据（当前表结构已有 `metadata_` JSONB，基本够用）。新增字段：

- `approval_status` — 审核状态: `pending` / `approved` / `rejected`
- `effective_at` — 生效日期
- `expired_at` — 失效日期
- `security_level` — 密级: `public` / `internal` / `confidential` / `secret`
- `client` — 租户
- `org_id` — 组织 ID

这些信息当前存储在 `metadata_` JSONB 字段中，迁移时提取为独立列以便索引和过滤。

---

## 五、实现顺序

1. **rag_schemas.py** — Pydantic 模型（无依赖，先定义契约）
2. **knowledge.py 模型扩展** — 新增数据库字段 + 迁移
3. **rag_engine.py** — RAGOrchestrator + 13 步流水线
4. **base.py** — BaseStageAgent 增加 `_retrieve_kb()` 方法
5. **knowledge_ingestion.py** — 上传流水线
6. **knowledge.py API** — 新端点
7. **exceptions.py / config.py** — 补充异常类和配置
8. **测试** — 集成测试 + 权限测试
9. **文档更新** — `10-rag-shared-agent.md` 对齐实现

---

## 六、验收标准

- [ ] 越权召回率为 0（三层过滤全部生效）
- [ ] `knowledge_insufficient=true` 时 Stage Agent 正确降低 confidence
- [ ] 降级路径可用且 diagnostics 明确记录
- [ ] 每条检索结果可追溯到 doc_id + chunk_id + source_path
- [ ] 文档上传→解析→分块→向量化→入库全流程可跑通
- [ ] 旧 `search()` / `get_retrieval_context()` 接口行为不变
- [ ] 存量 8 个模块 Stage Agent 不受影响
