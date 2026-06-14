# 赫尔墨斯（Hermes）小模型微调工程实施手册

> **约束条件**：只能微调小参数模型（< 500M 参数），无法微调大模型（DeepSeek/Qwen 等）。
> **定位**：面向实际落地的微调全流程指南——从做什么、怎么做、到怎么管。
> **关联文档**：[功能性架构](functional-architecture.md) | [系统架构设计](architecture-design.md)
> **文档版本**：v1.0 | **最后更新**：2026-06-10

---

## 目录

1. [为什么微调小模型](#一为什么微调小模型)
2. [微调什么：三个目标](#二微调什么三个目标)
3. [训练数据管道](#三训练数据管道)
4. [数据治理与合规](#四数据治理与合规)
5. [训练方案与工程实现](#五训练方案与工程实现)
6. [模型评估与验收](#六模型评估与验收)
7. [部署策略与知识库迁移](#七部署策略与知识库迁移)
8. [运维与模型退化监控](#八运维与模型退化监控)
9. [组织流程与审批](#九组织流程与审批)
10. [风险管理](#十风险管理)
11. [实施路线图与成本估算](#十一实施路线图与成本估算)

---

## 一、为什么微调小模型

### 1.1 现状：通用模型不理解风控领域

```
当前架构:
  用户请求 → RAG (通用 Embedding) → 混合检索 → 通用 Reranker → LLM 推理 → 输出

根因链:
  通用 Embedding 不懂 "窜货=跨区域销售"、"围标=串通投标"
      │
      ▼
  RAG 召回了不相关的文档
      │
      ├──→ LLM 缺少正确的法规/案例上下文 → 推理质量差 → 驳回率升高
      ├──→ LLM 引用不存在的法规 → 幻觉 → 守门不通过
      └──→ 用户反复补充信息 → 多轮对话 → 效率降低

结论: 修好 Embedding 这一个模型，14 个 Agent 全部受益。
```

### 1.2 微调小模型 vs 微调大模型

| 维度 | 大模型微调 (DeepSeek 70B+) | 小模型微调 (Embedding/Reranker <500M) |
|------|--------------------------|--------------------------------------|
| **GPU 需求** | 8-16× A100 80G | 1× RTX 4090 24GB |
| **训练时间** | 数天到数周 | 1-4 小时 |
| **数据量** | 50K-500K 条 | 3K-10K 条 |
| **单次成本** | ¥20,000-100,000 | ¥100-500 |
| **存储** | ~100GB 完整模型 | ~100MB-1GB |
| **回滚速度** | 数小时 | 即时（切换 Adapter） |
| **数据不出网** | 困难（通常需云 GPU） | 容易（本地 RTX 4090） |
| **替代方案** | 无（非大模型不可的任务） | Prompt + RAG 可替代大部分 |

### 1.3 大模型的问题用 RAG + Prompt 工程解决

```
以下能力依赖大模型推理，小模型替代不了:
  ✅ 复杂报告撰写      → 仍用 DeepSeek，通过 RAG 提供更好的上下文
  ✅ 多步推理分析      → 仍用 DeepSeek，通过 Prompt 工程约束
  ✅ 法律文书生成      → 仍用 DeepSeek，通过 Few-shot 引导格式
  ✅ 开放式问答        → 仍用 DeepSeek

以下能力可以用小模型显著改善:
  ✅ 语义检索质量      → 微调 Embedding（ROI 最高）
  ✅ 检索结果精排      → 微调 Reranker
  ✅ 简单分流决策      → 微调 BERT 分类器（降低 LLM 成本）
```

---

## 二、微调什么：三个目标

### 2.1 目标总览

```
优先级 1 (必做):  Embedding 模型 → 提升全部 14 个 Agent 的 RAG 检索质量
优先级 2 (推荐): Reranker 模型  → 提升检索 Top-5 精准率
优先级 3 (可选): 意图分流模型   → 降低 intake-agent 的 LLM 调用成本
```

### 2.2 目标一：Embedding 模型微调

#### 选型对比

| 候选模型 | 参数量 | 维度 | 大小 | 训练时间 (RTX 4090) | CPU 推理 | 推荐度 |
|---------|--------|------|------|-------------------|---------|--------|
| `bge-small-zh-v1.5` | 24M | 512d | ~95MB | ~30min | ~5ms/条 | ⭐⭐⭐ |
| `bge-base-zh-v1.5` | 102M | 768d | ~400MB | ~2h | ~10ms/条 | ⭐⭐⭐⭐⭐ |
| `bge-large-zh-v1.5` | 326M | 1024d | ~1.3GB | ~4h | ~25ms/条 | ⭐⭐⭐⭐ |
| `stella-base-zh-v3` | 102M | 1792d | ~400MB | ~2h | ~15ms/条 | ⭐⭐⭐⭐ |

**推荐：`bge-base-zh-v1.5`**

选择理由：
- 102M 参数，单张 RTX 4090 即可训练，数据不出内网
- 768 维 vs 当前 1536 维 → 存储减半，PGVector HNSW 索引缩小 50%
- BGE 中文社区活跃，FlagEmbedding 工具链成熟
- 效果/速度/成本平衡点最佳

#### 训练数据采集

需要 `(query, positive_document, negative_document)` 三元组，从你的运行系统中自动采集：

```
数据源 1: 守门审批记录（最直接，质量最高）
  - AI 生成报告时引用了 KB 文档 → 守门 approved → 引用的文档是正例
  - AI 引用被驳回 → 引用的文档相关性不足 → 负例
  - 自动构建: (Agent RAG query, approved 引用的文档=正, rejected 引用的文档=负)

数据源 2: LangFuse 检索记录（量大，质量中等）
  - 每次 RAG 检索的 query + 返回的 Top K 文档
  - AI 主动引用的 → 正例候选
  - AI 未引用的 → 负例候选

数据源 3: 人工标注（质量最高，量小）
  - 风控专家每周标注 20-30 对
  - 6 个月积累 500-700 对
  - 质量远超自动采集数据，用作评估集核心
```

### 2.3 目标二：Reranker 模型微调

#### 为什么需要 Reranker

RAG 检索是两阶段的：粗筛（Embedding+ES）→ 精排（Reranker）。通用 Reranker 不理解风控领域的文档优先级。例如：

```
查询: "该供应商是否有围标嫌疑"
  文档 A: "围标串标法律定义..."  → 通用 Reranker 给高分（关键词匹配）
  文档 B: "供应商X历史投标记录分析" → 通用 Reranker 给低分
  但风控人员真正需要: 先看 B（历史案例），再看 A（法规）

→ 微调 Reranker 注入这种领域偏好
```

#### 选型

| 候选模型 | 参数量 | 大小 | 推理速度 | 推荐度 |
|---------|--------|------|---------|--------|
| `bge-reranker-v2-minicpm` | ~280M | ~1.1GB | ~40ms/对 | ⭐⭐⭐⭐⭐ |
| `bge-reranker-base` | ~280M | ~1.1GB | ~50ms/对 | ⭐⭐⭐⭐ |

**推荐：`bge-reranker-v2-minicpm`**

#### 训练数据采集

Reranker 数据格式是 `(query, document, relevance_score)`，比 Embedding 更容易自动采集：

```
来源 1: 守门 approved → relevance = 1.0
        守门 rejected → relevance = 0.0
        守门 modified → 原始引用文档 relevance 降低

来源 2: AI 主动引用了文档 → relevance = 0.8
        AI 检索到但未引用 → relevance = 0.3

来源 3: 人工标注（每月 100 对，高质量校准集）
```

### 2.4 目标三：意图分流模型（可选）

#### 场景

```
当前 intake-agent 流程:
  案件录入 → LLM (DeepSeek, 3-5s, ¥0.02/次) → 分流决策 → 守门

优化后:
  案件录入 → 小模型 (<50ms, ¥0/次) → 高置信度 → 直接分流 → 守门
                                    → 低置信度 → LLM 兜底
预期: 60-70% 的简单案件直接用小模型处理，月度 LLM 成本降低 40-50%
```

#### 选型

| 候选模型 | 参数量 | 大小 | CPU 推理 | 推荐度 |
|---------|--------|------|---------|--------|
| `RoBERTa-wwm-ext-chinese` | 110M | ~400MB | ~30ms | ⭐⭐⭐⭐⭐ |
| `bert-base-chinese` | 110M | ~400MB | ~30ms | ⭐⭐⭐⭐ |

**推荐：`RoBERTa-wwm-ext-chinese`**（全词掩码，中文法律/商务文本理解更好）

#### 训练数据

直接从历史 intake-agent 的输入和守门结果中提取：

```python
# 输入特征
#   - 案件来源 (fraud_source)
#   - 事业部 (client)
#   - 涉案金额区间
#   - 举报类型/风险场景分类
#   - 案件描述文本（截断到 512 tokens）

# 输出标签（多标签分类）
#   - should_investigate: yes/no
#   - should_transfer: yes/no
#   - transfer_target: hr/legal/other/none
#   - risk_level: high/medium/low
```

### 2.5 不微调的模型

| 模型 | 建议 | 原因 |
|------|------|------|
| DeepSeek / Qwen（大 LLM） | ❌ | 微调不了，用 RAG + Prompt 替代 |
| Whisper large-v3 | ❌ | 中文准确率 > 95%，已够用 |
| PaddleOCR | ❌ | 中文准确率已高，够用 |
| CLIP | ❌ | 零样本分类已满足证据分类需求 |

---

## 三、训练数据管道

### 3.1 数据管道全景

```
┌─────────────────────────────────────────────────────────────────────┐
│                    训练数据管道（5 阶段）                                 │
│                                                                      │
│  Stage 1: 数据采集                                                    │
│  ├── LangFuse traces → RAG 检索记录 + Tool 调用轨迹                   │
│  ├── audit_log → 守门审批记录（approved/rejected/modified）           │
│  ├── stage_outputs → AI 各阶段产出物（含文档引用信息）                  │
│  └── KB metadata → 知识库文档元数据                                    │
│       │                                                              │
│       ▼                                                              │
│  Stage 2: 数据清洗                                                    │
│  ├── PII 脱敏（姓名/电话/邮箱/身份证号 → 占位符替换）                   │
│  ├── 租户去标识化（ecovacs/tineco → org_a/org_b）                     │
│  ├── 去重（相似度 > 0.95 视为重复）                                    │
│  ├── 格式校验（排除格式错误的输出）                                     │
│  └── 长度过滤（排除空输出和异常长输出，3σ 原则）                         │
│       │                                                              │
│       ▼                                                              │
│  Stage 3: 数据标注                                                    │
│  ├── 自动标注: 从审批记录/引用模式自动推导标签                          │
│  └── 人工标注: 风控专家标注高价值样本（每周 1-2h, 20-30 对）           │
│       │                                                              │
│       ▼                                                              │
│  Stage 4: 格式转换 + 拆分                                             │
│  ├── Embedding: JSONL (query, pos, neg)                              │
│  ├── Reranker: JSONL (query, doc, score)                             │
│  ├── Classifier: JSONL (text, label)                                 │
│  └── 拆分: Train 80% / Validation 10% / Test 10%                     │
│       │                                                              │
│       ▼                                                              │
│  Stage 5: 版本管理                                                    │
│  ├── 命名: {model}-{dataset_version}-{date}                          │
│  ├── 存储: MinIO bucket: hermes-training-data                        │
│  └── 元数据: 样本量/来源分布/标注方式/质量评分                          │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 自动采集代码骨架

```python
class TrainingDataCollector:
    """训练数据采集器"""

    def __init__(
        self,
        langfuse: LangFuseClient,
        db: AsyncSession,
        audit_log: AuditLogService,
    ):
        self.langfuse = langfuse
        self.db = db
        self.audit_log = audit_log

    # ========== Embedding 训练数据 ==========

    async def collect_embedding_triplets(
        self,
        start_date: date,
        end_date: date,
        min_quality: float = 0.6,
    ) -> list[dict]:
        """
        采集 (query, positive_doc, negative_doc) 三元组。

        逻辑:
        - 找到守门 approved 的 Agent 调用
        - 该调用中 AI 引用过的文档 = 正例
        - 同次检索返回但未被引用的文档 = 负例
        """
        traces = await self.langfuse.get_traces(
            start_date=start_date, end_date=end_date,
            filters={"has_rag": True},
        )

        triplets = []
        for trace in traces:
            approval = await self.audit_log.get_approval(
                case_id=trace.case_id, stage=trace.stage
            )
            if not approval or approval.result != "approved":
                continue

            query = self._extract_rag_query(trace)
            cited_docs = self._extract_cited_docs(trace)
            uncited_docs = self._extract_uncited_docs(trace)

            for pos_doc in cited_docs:
                neg = random.choice(uncited_docs) if uncited_docs else self._hard_negative(pos_doc)
                triplets.append({"query": query, "pos": [pos_doc], "neg": [neg]})

        return triplets

    # ========== Reranker 训练数据 ==========

    async def collect_reranker_pairs(
        self,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """
        采集 (query, document, relevance_score) 数据。

        评分规则:
        - approved 时引用的文档 → 1.0
        - approved 时未引用的文档 → 0.0
        - AI 主动引用的文档 → 0.8
        - 人工标注 → 精确分数
        """
        # 同 Embedding 采集逻辑，输出格式不同
        ...

    # ========== 分流分类器训练数据 ==========

    async def collect_classifier_data(
        self,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """
        采集 (text, label) 分类数据。
        从历史 intake-agent 的输入和守门结果中直接构建。
        """
        cases = await self.db.query(
            """
            SELECT c.fraud_source, c.client, c.amount_range,
                   c.description, c.attachment_types,
                   s.intake_report, a.result, a.modified_output
            FROM cases c
            JOIN stage_outputs s ON c.id = s.case_id AND s.stage = 'intake'
            JOIN audit_log a ON a.case_id = c.id AND a.stage = 'intake'
            WHERE a.result IN ('approved', 'modified')
            AND c.created_at BETWEEN $1 AND $2
            """,
            start_date, end_date
        )

        samples = []
        for case in cases:
            # 使用守门后的最终结果作为 label（而非 AI 原始输出）
            output = case["modified_output"] or case["intake_report"]
            label = self._extract_label(output)
            text = self._format_input(case)
            samples.append({"text": text, "label": label})

        return samples
```

### 3.3 数据质量保障

```
自动化检查（每次采集后执行）:
├── PII 扫描: 正则 + Presidio 检测未脱敏的个人信息
├── JSON Schema 校验: 结构化输出是否完整
├── 分布均衡检查: 各 Agent/各场景的样本量是否均衡
├── 重复度检查: 相似度 > 0.95 的去重
└── 质量阈值: 质量分 < 0.6 的自动丢弃

人工抽检（每周）:
├── 随机抽取 50 条 → 风控专家审核
├── 标记 A/B/C 等级
├── 目标: A 级 > 60%, A+B 级 > 85%
└── 标注反馈 → 更新自动质量规则
```

---

## 四、数据治理与合规

### 4.1 数据脱敏规范

这是企业微调中最容易出问题的环节。训练数据中可能包含真实的个人信息、财务数据、商业秘密。

```python
class TrainingDataAnonymizer:
    """训练数据脱敏器 —— 必须在数据采集后、存入 MinIO 前执行"""

    # PII 检测规则
    PII_PATTERNS = {
        "phone": r"1[3-9]\d{9}",
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "id_card": r"[1-9]\d{5}(19|20)\d{2}[01]\d[0123]\d\d{3}[0-9Xx]",
        "bank_card": r"\d{16,19}",
    }

    # 实体替换映射（同一实体在全量数据中保持一致）
    entity_map: dict[str, str] = {}

    def anonymize(self, text: str) -> tuple[str, AnonymizeReport]:
        report = AnonymizeReport()

        # 1. 正则匹配 → 替换
        text = self._mask_patterns(text, report)

        # 2. NER 检测 → 替换（姓名、公司名、地名）
        text = self._mask_entities(text, report)

        # 3. 金额扰动
        #    原始金额 × random(0.3, 3.0) → 保留量级，隐藏精确值
        text = self._perturb_amounts(text, report)

        # 4. 租户去标识化
        text = text.replace("ecovacs", "org_alpha")
        text = text.replace("tineco", "org_beta")
        text = text.replace("group", "org_headquarters")

        return text, report

    def _mask_patterns(self, text: str, report: AnonymizeReport) -> str:
        """正则匹配脱敏"""
        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = re.findall(pattern, text)
            for match in matches:
                if pii_type == "phone":
                    replacement = match[:3] + "****" + match[-2:]
                elif pii_type == "email":
                    replacement = f"user_{hash(match)[:8]}@example.com"
                else:
                    replacement = f"<{pii_type.upper()}_MASKED>"
                text = text.replace(match, replacement)
                report.add(pii_type, match, replacement)

        return text

    def _perturb_amounts(self, text: str, report: AnonymizeReport) -> str:
        """金额扰动: 保留量级，隐藏精确值"""
        amount_pattern = r"¥\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*元"

        def perturb(match):
            amount_str = match.group(1) or match.group(2)
            amount = float(amount_str.replace(",", ""))
            scale = random.uniform(0.3, 3.0)  # 在 0.3x~3.0x 范围内随机缩放
            perturbed = int(amount * scale)
            report.add("amount", str(amount), str(perturbed))
            return f"¥{perturbed:,}"

        return re.sub(amount_pattern, perturb, text)
```

### 4.2 数据合规检查清单

```
训练前必须确认:

□ 所有训练数据已完成 PII 脱敏（姓名/电话/邮箱/身份证/银行卡）
□ 所有训练数据已完成租户去标识化
□ 金额数据已扰动处理（保留量级，隐藏精确值）
□ 供应商名称已替换为代号
□ 涉及刑事案件的具体细节已移除或泛化
□ 训练数据不包含任何生产环境的密钥/Token/密码
□ 如果用云端 GPU: 确认数据出境风险评估已完成
□ 如果用云端 GPU: 确认训练完成后云端数据已清除
□ MinIO bucket 权限: 仅 AI 工程师 + 风控负责人可读
□ 训练数据版本已打 tag，可追溯到具体采集时间和范围
□ 合规审批已通过（见第九章审批流程）
```

### 4.3 数据存储安全

```
存储层级:
  MinIO bucket: hermes-training-data (隔离的 Bucket，不与业务数据混存)
  ├── raw/          原始采集数据（PII 脱敏前，仅保留 7 天，用于审计）
  ├── anonymized/   脱敏后数据（永久保留，可复用于后续训练）
  ├── datasets/     格式化后的训练/验证/测试集（版本化管理）
  └── models/       训练产物（Adapter 权重 + 训练配置 + 评估报告）

访问控制:
  - Bucket level: 仅 hermes-training-sa 有读写权限
  - 应用层: 通过内部 API 访问，不在公网暴露
  - 审计: 每次数据读写记录 audit_log

数据生命周期:
  - raw 数据: 7 天后自动删除
  - anonymized 数据: 保留至案件归档周期（与业务数据一致）
  - datasets: 保留最近 10 个版本
  - 训练中间产物: 训练完成后 24h 自动清理
```

---

## 五、训练方案与工程实现

### 5.1 硬件与环境

```
训练主机:
  推荐: 1× RTX 4090 24GB (或 A4000 16GB, A5000 24GB)
  备选: 云 GPU 租赁 (AutoDL/矩池云, A100 40G ~¥10/h)

软件环境:
  Python 3.11+
  PyTorch 2.x + CUDA 12.x
  FlagEmbedding (BGE 官方微调框架)
  transformers + datasets + accelerate

实验管理:
  MLflow (自部署, 数据不出网)
  记录: 训练超参数 / loss curve / eval metrics / 模型产物路径
```

### 5.2 Embedding 微调方案

```bash
# 环境准备
pip install flagembedding datasets accelerate

# 训练数据格式 (JSONL): 每行一个三元组
# {"query": "供应商围标串标的风险识别方法",
#  "pos": ["采购业务中围标串标行为的识别要点：1.投标供应商IP相同..."],
#  "neg": ["员工差旅报销标准及审批流程..."]}

# 训练 (1× RTX 4090, ~2h)
torchrun --nproc_per_node 1 \
  -m FlagEmbedding.baai_general_embedding.finetune.run \
  --model_name_or_path BAAI/bge-base-zh-v1.5 \
  --train_data ./data/hermes_embedding_train.jsonl \
  --output_dir ./models/hermes-bge-base-v1 \
  --num_epochs 3 \
  --per_device_train_batch_size 32 \
  --learning_rate 2e-5 \
  --max_seq_length 512 \
  --temperature 0.02 \
  --query_max_len 128 \
  --passage_max_len 512 \
  --save_steps 500 \
  --logging_steps 100

# 评估
python -m FlagEmbedding.baai_general_embedding.finetune.eval \
  --model_path ./models/hermes-bge-base-v1 \
  --eval_data ./data/hermes_embedding_eval.jsonl
```

### 5.3 Reranker 微调方案

```bash
# 训练数据格式 (JSONL):
# {"query": "围标风险分析", "doc": "采购业务中围标识别要点...", "label": 1}
# {"query": "围标风险分析", "doc": "员工考勤管理制度...", "label": 0}

# 训练 (1× RTX 4090, ~3h)
torchrun --nproc_per_node 1 \
  -m FlagEmbedding.reranker.run \
  --model_name_or_path BAAI/bge-reranker-v2-minicpm-layerwise \
  --train_data ./data/hermes_reranker_train.jsonl \
  --output_dir ./models/hermes-reranker-v1 \
  --num_epochs 3 \
  --per_device_train_batch_size 16 \
  --learning_rate 3e-5 \
  --max_seq_length 512 \
  --query_max_len 128 \
  --passage_max_len 512
```

### 5.4 意图分流分类器微调方案

```python
# 训练 (1× RTX 4090, ~1h)
from transformers import (
    AutoTokenizer, AutoModelForSequenceClassification,
    Trainer, TrainingArguments
)

model = AutoModelForSequenceClassification.from_pretrained(
    "hfl/chinese-roberta-wwm-ext",
    num_labels=4,  # should_investigate, should_transfer, risk_level, transfer_target
    problem_type="multi_label_classification",
)

training_args = TrainingArguments(
    output_dir="./models/hermes-intake-classifier-v1",
    num_train_epochs=5,
    per_device_train_batch_size=32,
    per_device_eval_batch_size=64,
    learning_rate=5e-5,
    warmup_ratio=0.1,
    evaluation_strategy="steps",
    eval_steps=200,
    save_strategy="steps",
    save_steps=200,
    logging_steps=50,
    load_best_model_at_end=True,
    metric_for_best_model="f1",
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    compute_metrics=compute_metrics,
)
trainer.train()
```

### 5.5 模型导出与加速

训练完成后，将模型转换为 ONNX 格式以加速 CPU 推理：

```python
# PyTorch → ONNX 导出（适用于部署到生产 CPU 服务器）
import onnx
from transformers import AutoTokenizer, AutoModel
from optimum.onnxruntime import ORTModelForFeatureExtraction

# Embedding 模型导出
model = AutoModel.from_pretrained("./models/hermes-bge-base-v1")
tokenizer = AutoTokenizer.from_pretrained("./models/hermes-bge-base-v1")

# 使用 Optimum 导出 ONNX
ort_model = ORTModelForFeatureExtraction.from_pretrained(
    "./models/hermes-bge-base-v1",
    export=True,
    provider="CPUExecutionProvider",
)

ort_model.save_pretrained("./models/hermes-bge-base-v1-onnx")
tokenizer.save_pretrained("./models/hermes-bge-base-v1-onnx")

# 性能对比:
# PyTorch CPU: ~25ms/条
# ONNX CPU:    ~8ms/条  (3x 加速)
```

### 5.6 服务部署

```python
# Embedding 服务 (FastAPI 微服务)
from fastapi import FastAPI
from pydantic import BaseModel
from optimum.onnxruntime import ORTModelForFeatureEmbedding

app = FastAPI()
model = ORTModelForFeatureEmbedding.from_pretrained(
    "./models/hermes-bge-base-v1-onnx"
)
tokenizer = AutoTokenizer.from_pretrained(
    "./models/hermes-bge-base-v1-onnx"
)

class EmbeddingRequest(BaseModel):
    texts: list[str]
    normalize: bool = True

class EmbeddingResponse(BaseModel):
    embeddings: list[list[float]]
    model_version: str
    inference_ms: float

@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def get_embeddings(req: EmbeddingRequest):
    start = time.perf_counter()
    inputs = tokenizer(
        req.texts, padding=True, truncation=True,
        max_length=512, return_tensors="pt"
    )
    outputs = model(**inputs)
    vectors = outputs.last_hidden_state[:, 0, :].cpu().numpy()

    if req.normalize:
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    elapsed = (time.perf_counter() - start) * 1000
    return EmbeddingResponse(
        embeddings=vectors.tolist(),
        model_version="hermes-bge-base-v1",
        inference_ms=elapsed,
    )
```

---

## 六、模型评估与验收

### 6.1 评估维度全景

```
┌─────────────────────────────────────────────────────────────────────┐
│                    三层评估体系                                         │
│                                                                      │
│  Layer 1: 离线基准评估（训练后立即执行，自动化）                          │
│  ├── Embedding: Recall@K, MRR, NDCG@K                               │
│  ├── Reranker: Precision@K, NDCG@K, MAP                             │
│  ├── Classifier: Accuracy, F1, Precision/Recall per class           │
│  └── 门禁: 所有指标不得低于基线 95%                                   │
│                                                                      │
│  Layer 2: 人工盲评（离线评估通过后，1-3 天）                            │
│  ├── 评测员: 2-3 位风控专家                                          │
│  ├── 方式: 随机展示新旧模型输出（盲评，评测员不知道哪个是新的）          │
│  ├── 维度: 相关性/准确性/完整性/可操作性（1-5 分）                     │
│  └── 门禁: 新模型胜率 > 50%，无严重退化                               │
│                                                                      │
│  Layer 3: 在线 A/B 测试（灰度发布期间，5-7 天）                          │
│  ├── 碳基采纳率 (approved/all)                                       │
│  ├── 碳基驳回率 (rejected/all)                                       │
│  ├── AI 输出的人工修改幅度                                            │
│  ├── KB 检索命中率（AI 引用了检索结果的次数/总检索次数）                │
│  └── 门禁: 采纳率下降 < 5%, 驳回率上升 < 3%, 样本量 ≥ 200             │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 具体评估指标与门禁

#### Embedding 模型

```python
class EmbeddingQualityGates:
    """Embedding 模型质量门禁"""

    gates = {
        # 从 13 个 KB 分区各抽样 50 条查询构建评估集 (~650 条)
        "recall_at_5":    {"baseline": 0.55, "target": 0.85, "min": 0.80},
        "recall_at_10":   {"baseline": 0.70, "target": 0.92, "min": 0.88},
        "mrr":            {"baseline": 0.40, "target": 0.72, "min": 0.65},
        "ndcg_at_5":      {"baseline": 0.45, "target": 0.78, "min": 0.72},
    }

    def check(self, eval_results: dict) -> GateResult:
        failures = []
        for metric, thresholds in self.gates.items():
            if eval_results[metric] < thresholds["min"]:
                failures.append(
                    f"{metric}: {eval_results[metric]:.3f} < min {thresholds['min']}"
                )
        return GateResult(
            passed=len(failures) == 0,
            failures=failures,
            recommendation=self._recommend(eval_results),
        )
```

#### Reranker 模型

```python
class RerankerQualityGates:
    gates = {
        "precision_at_5": {"target": 0.75, "min": 0.68},
        "ndcg_at_5":      {"target": 0.80, "min": 0.73},
        "mrr":            {"target": 0.85, "min": 0.78},
        "latency_p95_ms": {"target": 100, "min": 200},  # P95 < 200ms
    }
```

#### 意图分流分类器

```python
class ClassifierQualityGates:
    gates = {
        "accuracy":       {"target": 0.90, "min": 0.85},
        "f1_macro":       {"target": 0.88, "min": 0.82},
        "should_investigate_recall": {"target": 0.95, "min": 0.90},
        # ↓ 最重要：不能把该查的案件分错
    }
```

### 6.3 A/B 测试统计设计

```python
class ABTestDesign:
    """
    在线 A/B 测试设计。

    核心问题: 需要多少样本才能得出有统计显著性的结论？
    """

    def calculate_sample_size(
        self,
        baseline_rate: float = 0.70,    # 基线采纳率 70%
        expected_lift: float = 0.10,    # 期望提升 10%
        alpha: float = 0.05,            # 显著性水平
        power: float = 0.80,            # 统计功效
    ) -> int:
        """
        公式: n = (Z_α/2 + Z_β)² * (p1(1-p1) + p2(1-p2)) / (p2 - p1)²

        代入: p1=0.70, p2=0.80, α=0.05, β=0.20
        → n ≈ 200 per group

        结论: 每组至少 200 次交互 → 灰度期至少积累 400 次交互
        """
        from scipy import stats
        z_alpha = stats.norm.ppf(1 - alpha / 2)
        z_beta = stats.norm.ppf(power)

        p1, p2 = baseline_rate, baseline_rate + expected_lift
        n = (z_alpha + z_beta)**2 * (p1*(1-p1) + p2*(1-p2)) / (p2 - p1)**2
        return math.ceil(n)

    def check_significance(
        self,
        control: ABTestResult,  # 旧模型
        treatment: ABTestResult,  # 新模型
    ) -> SignificanceResult:
        """
        卡方检验判断新旧模型是否有显著差异。

        H₀: 新旧模型的采纳率没有差异
        H₁: 新旧模型的采纳率有显著差异
        """
        from scipy.stats import chi2_contingency

        table = [
            [control.approved, control.total - control.approved],
            [treatment.approved, treatment.total - treatment.approved],
        ]
        chi2, p_value, _, _ = chi2_contingency(table)

        return SignificanceResult(
            significant=p_value < 0.05,
            p_value=p_value,
            recommendation=(
                "可以全量发布" if p_value < 0.05 and treatment.approval_rate > control.approval_rate
                else "需要继续观察" if p_value >= 0.05
                else "不建议发布（效果显著变差）"
            )
        )
```

### 6.4 验收签字流程

```
微调模型验收清单:
□ 离线评估报告已生成，所有指标通过质量门禁
□ 人工盲评完成（≥2 位专家，≥30 条/模型），新模型胜率 > 50%
□ A/B 测试完成（≥400 次交互），统计显著性检验通过
□ 未检测到任何 Agent 的指标退化 > 5%
□ 模型安全性检查通过（输出不包含越权内容/敏感数据泄露）
□ 回滚预案已就绪（旧模型保留在生产环境 30 天）
□ 监控告警规则已更新（新模型专属看板已配置）

签字:
  训练工程师: __________  日期: __________
  风控专家:    __________  日期: __________
  技术负责人:   __________  日期: __________
```

---

## 七、部署策略与知识库迁移

### 7.1 Embedding 模型部署的特殊挑战

最关键的工程问题：**切换 Embedding 模型 = 向量的语义空间完全改变，必须重建全量知识库索引**。

```
旧模型 (text-embedding-3-large, 1536d):
  知识库文档 → Embedding → 向量 v_old_1, v_old_2, ... → PGVector (kb_chunks 表)

新模型 (bge-base-zh-v1.5, 768d):
  知识库文档 → Embedding → 向量 v_new_1, v_new_2, ... → PGVector (kb_chunks_v2 表)
  维度不同！无法兼容旧索引！
```

### 7.2 知识库迁移方案：双表并行 + 后台渐进迁移

```
Phase 1: 双写（新模型训练完成后，预计 1 天）
┌──────────────────────────────────────────────────────────────┐
│  创建 kb_chunks_v2 表（新维度 768d）                          │
│                                                              │
│  RAG 引擎改造:                                                │
│    新文档入库 → 同时写入 kb_chunks (旧) + kb_chunks_v2 (新)    │
│    查询 → 继续使用 kb_chunks（旧，不影响线上）                 │
│                                                              │
│  后台 Celery 任务: 批量将存量知识库用新模型重新 Embedding      │
│    每批 500 chunks, 间隔 100ms, 避免打满 CPU                  │
│    10TB 知识库预计 4-8 小时完成（取决于文档总量）               │
└──────────────────────────────────────────────────────────────┘

Phase 2: 灰度查询（知识库重建完成后，预计 3-5 天）
┌──────────────────────────────────────────────────────────────┐
│  RAG 引擎: 按 task_id 哈希分流                                 │
│    5% → kb_chunks_v2（新）                                    │
│    95% → kb_chunks（旧）                                      │
│                                                              │
│  监控指标:                                                    │
│    - 检索命中率 (AI 引用检索结果的比例)                        │
│    - 检索延迟 P95                                             │
│    - 驳回率变化                                                │
└──────────────────────────────────────────────────────────────┘

Phase 3: 全量切换（灰度通过后）
┌──────────────────────────────────────────────────────────────┐
│  RAG 引擎: 100% → kb_chunks_v2                               │
│  旧表保留 30 天作为回滚备份                                   │
│                                                              │
│  新文档: 仅写入 kb_chunks_v2                                  │
│  旧表: 停止写入，标记为 deprecated                            │
└──────────────────────────────────────────────────────────────┘

Phase 4: 清理（30 天后）
┌──────────────────────────────────────────────────────────────┐
│  确认新模型稳定 30 天 → 删除 kb_chunks 旧表                   │
│  释放存储空间 (~50% 因为维度从 1536 → 768)                    │
└──────────────────────────────────────────────────────────────┘
```

### 7.3 迁移代码骨架

```python
class KnowledgeBaseMigrator:
    """知识库迁移器 —— 从旧 Embedding 模型切换到新模型"""

    def __init__(
        self,
        old_model: EmbeddingService,
        new_model: EmbeddingService,
        db: AsyncSession,
        pgvector: PGVectorStore,
    ):
        self.old_model = old_model
        self.new_model = new_model
        self.db = db
        self.pgvector = pgvector

    async def setup_dual_write(self):
        """Phase 1a: 创建新向量表，开启双写"""
        # 1. 创建新表 kb_chunks_v2（新维度 768d）
        await self.db.execute("""
            CREATE TABLE kb_chunks_v2 (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                kb_type VARCHAR(50) NOT NULL,
                doc_id UUID NOT NULL REFERENCES knowledge_documents(id),
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding VECTOR(768),  -- 新维度
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX ON kb_chunks_v2
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 200);
            CREATE INDEX ON kb_chunks_v2 (kb_type, doc_id);
        """)

        # 2. 修改入库逻辑 → 同时写入两表
        self.pgvector.enable_dual_write(
            old_table="kb_chunks",
            new_table="kb_chunks_v2",
        )

    async def backfill_existing(self):
        """Phase 1b: 后台批量迁移存量知识库"""
        # 分批读取 kb_chunks 中的内容
        batch_size = 500
        total = await self.db.scalar(
            select(func.count()).select_from(KBChunk)
        )

        with tqdm(total=total // batch_size, desc="Knowledge Base Migration") as pbar:
            offset = 0
            while True:
                chunks = await self.db.execute(
                    select(KBChunk).offset(offset).limit(batch_size)
                )
                chunks = chunks.scalars().all()
                if not chunks:
                    break

                # 用新模型重新 Embedding
                texts = [c.content for c in chunks]
                new_vectors = await self.new_model.encode(texts)

                # 批量写入新表
                await self.db.execute(
                    insert(KBChunkV2),
                    [
                        {
                            "id": str(uuid.uuid4()),
                            "kb_type": c.kb_type,
                            "doc_id": c.doc_id,
                            "chunk_index": c.chunk_index,
                            "content": c.content,
                            "embedding": v.tolist(),
                            "metadata": c.metadata,
                        }
                        for c, v in zip(chunks, new_vectors)
                    ]
                )
                await self.db.commit()

                offset += batch_size
                pbar.update(1)

                # 避免打满 CPU，每批间隔 100ms
                await asyncio.sleep(0.1)

    async def canary_query(self, ratio: float = 0.05):
        """Phase 2: 灰度查询"""
        self.pgvector.set_canary_ratio(
            old_table="kb_chunks",
            new_table="kb_chunks_v2",
            ratio=ratio,  # 5% 流量走新表
            hash_key="task_id",
        )

    async def full_switch(self):
        """Phase 3: 全量切换"""
        self.pgvector.set_canary_ratio(
            old_table="kb_chunks",
            new_table="kb_chunks_v2",
            ratio=1.0,  # 100% 到新表
        )

    async def rollback(self):
        """回滚: 切回旧表"""
        self.pgvector.set_canary_ratio(
            old_table="kb_chunks",
            new_table="kb_chunks_v2",
            ratio=0.0,  # 0% 到新表，全量旧表
        )
```

### 7.4 Reranker 和分类器的部署

Reranker 和分类器不涉及知识库迁移，部署简单得多：

```python
# Reranker 部署: 替换 RAG 引擎中的 Re-ranking 步骤
# 旧: cross_encoder = SentenceTransformer("BAAI/bge-reranker-v2-minicpm")
# 新: cross_encoder = SentenceTransformer("./models/hermes-reranker-v1")

# 分类器部署: 作为 intake-agent 的预筛层
# 在 intake-agent 的 Context Builder 之前插入:
class IntakeRouter:
    def __init__(self, classifier, llm_adapter, threshold=0.85):
        self.classifier = classifier
        self.llm_adapter = llm_adapter
        self.threshold = threshold  # 置信度阈值

    async def route(self, case: Case) -> CaseDecision:
        # 1. 小模型快速预测
        probs = await self.classifier.predict(case)
        max_prob = max(probs)

        # 2. 高置信度 → 直接使用小模型结果
        if max_prob >= self.threshold:
            return CaseDecision(
                source="classifier",
                confidence=max_prob,
                **self._format_output(probs),
            )

        # 3. 低置信度 → 转交大模型
        return await self.llm_adapter.invoke(case)
```

---

## 八、运维与模型退化监控

### 8.1 模型性能漂移检测

这是企业微调中最容易被忽略的问题——模型上线后性能随时间下降。

```python
class ModelDriftDetector:
    """
    模型性能漂移检测器。

    两种漂移:
    - Data Drift: 输入数据的分布变了（如新增了原来没见过的案件类型）
    - Concept Drift: 同样的输入，正确答案变了（如法规变更导致判断标准变化）
    """

    def __init__(self, model_name: str, baseline_metrics: dict):
        self.model_name = model_name
        self.baseline = baseline_metrics

    async def detect_drift(
        self,
        window_days: int = 7,
    ) -> DriftReport:
        """
        每周自动运行，对比近期指标与基线。

        检测方法:
        1. Embedding 模型: 监控 RAG 检索的"引用率"
           → AI 引用了检索结果的次数 / 总检索次数
           → 如果引用率持续下降，说明检索质量在退化

        2. Reranker 模型: 监控 Top-5 结果的"碳基采纳率"
           → 守门 approved 时 AI 引用了 Reranker Top-5 中的文档
           → 如果采纳率下降，说明精排质量退化

        3. 分类器: 监控"转交大模型比例"
           → 如果比例持续上升，说明分类器变保守了（可能是新案件类型增多）
        """
        current_metrics = await self._collect_recent_metrics(window_days)

        drift_detected = {}
        for metric, baseline_value in self.baseline.items():
            current = current_metrics.get(metric, 0)
            relative_change = abs(current - baseline_value) / max(baseline_value, 0.01)

            # 常见退化阈值: 相对变化 > 20%
            if relative_change > 0.20:
                drift_detected[metric] = {
                    "baseline": baseline_value,
                    "current": current,
                    "change_pct": relative_change * 100,
                    "severity": "high" if relative_change > 0.40 else "medium",
                }

        return DriftReport(
            model=self.model_name,
            drift_detected=drift_detected,
            needs_retraining=len(drift_detected) >= 3,  # ≥3 个指标退化 → 建议重训
            recommendation=self._recommend(drift_detected),
        )

    def _recommend(self, drift_detected: dict) -> str:
        if not drift_detected:
            return "模型状态正常，无需操作"
        if len(drift_detected) < 3:
            return "个别指标退化，建议人工排查原因（数据变化？法规变更？）"
        return "多个指标显著退化，建议触发重新微调"
```

### 8.2 何时触发重新微调

| 触发条件 | 阈值 | 操作 |
|---------|------|------|
| **数据积累** | 新增标注数据 > 原始训练集 30% | 融合新旧数据重新训练 |
| **性能退化** | ≥3 个关键指标相对退化 > 20% | 分析退化原因 → 决定是否重训 |
| **法规变更** | 重大法规/制度更新（如等保升级） | 补充新法规相关训练数据后重训 |
| **新 Agent 上线** | 新 Agent 使用现有的 Embedding/Reranker | 补充新 Agent 场景的数据后重训 |
| **定期重训** | 每 6 个月（即使无明显退化） | 用累积的新数据增量训练 |

### 8.3 告警规则

```yaml
alerts:
  embedding_model:
    - name: "RAG 引用率持续下降"
      condition: "rag_citation_rate < baseline * 0.8 for 3 consecutive days"
      severity: P2
      action: "通知 AI 工程师排查"

    - name: "RAG 检索延迟异常"
      condition: "p95_latency > 500ms"
      severity: P3
      action: "检查 PGVector 索引状态"

  reranker_model:
    - name: "Top-5 采纳率下降"
      condition: "top5_citation_rate < baseline * 0.85 for 3 consecutive days"
      severity: P2
      action: "通知 AI 工程师，准备回滚"

  classifier_model:
    - name: "转交大模型比例异常上升"
      condition: "llm_fallback_rate > baseline * 1.5 for 5 consecutive days"
      severity: P3
      action: "检查是否有新的案件类型出现，考虑补充训练数据"
```

---

## 九、组织流程与审批

### 9.1 微调全流程 SOP

```
┌─────────────────────────────────────────────────────────────────────┐
│             赫尔墨斯小模型微调标准操作流程 (SOP)                           │
│                                                                      │
│  Step 1: 微调申请 (Owner: AI 工程师)                                   │
│  ├── 填写《微调申请表》: 目标模型、预期收益、数据来源、风险评估          │
│  ├── 技术负责人审批 (1 个工作日内)                                      │
│  └── 如涉及新数据源，需额外合规审批                                      │
│                                                                      │
│  Step 2: 数据准备 (Owner: AI 工程师)                                    │
│  ├── 执行数据采集 Pipeline                                              │
│  ├── 执行 PII 脱敏                                                      │
│  ├── 数据质量抽检 (AI 工程师 + 1 位风控专家)                            │
│  └── 数据版本归档到 MinIO                                               │
│                                                                      │
│  Step 3: 训练执行 (Owner: AI 工程师)                                    │
│  ├── 在训练主机上启动训练任务                                            │
│  ├── MLflow 记录训练过程                                                │
│  ├── 训练完成 → 自动跑离线评估                                           │
│  └── 评估通过 → 进入 staging 验证                                       │
│                                                                      │
│  Step 4: 评估验收 (Owner: AI 工程师 + 风控专家)                          │
│  ├── 离线评估报告生成                                                    │
│  ├── 人工盲评 (≥2 位专家, ≥30 条/模型)                                  │
│  ├── 如为 Embedding 模型: 在 staging 环境跑知识库迁移预演                │
│  └── 验收通过 → 填写《微调上线审批表》                                   │
│                                                                      │
│  Step 5: 上线审批 (Owner: 技术负责人)                                    │
│  ├── 审核评估报告、盲评结果                                              │
│  ├── 确认回滚预案已就绪                                                  │
│  ├── 审批通过 → 开始灰度发布                                            │
│  └── 高风险变更（Embedding 知识库迁移）→ 需风控负责人加签                │
│                                                                      │
│  Step 6: 灰度发布 (Owner: AI 工程师 + 运维)                              │
│  ├── Staging 环境验证 (1-2 天)                                          │
│  ├── 生产金丝雀 5% (3 天, ≥200 次交互)                                  │
│  ├── 生产金丝雀 20% (3 天)                                              │
│  ├── 全量发布                                                           │
│  └── 持续监控 7 天，无异常 → 关闭灰度窗口                                │
│                                                                      │
│  Step 7: 归档 (Owner: AI 工程师)                                        │
│  ├── 旧模型标记为 deprecated, 保留 30 天                                 │
│  ├── 新模型标记为 production                                             │
│  ├── 更新监控告警规则到新模型基线                                        │
│  └── 微调全流程审计记录写入 audit_log                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 9.2 审批模板

#### 《微调申请表》

| 项目 | 内容 |
|------|------|
| 申请人 | |
| 日期 | |
| 微调目标 | □ Embedding 模型  □ Reranker 模型  □ 意图分流分类器 |
| 基座模型 | (如 bge-base-zh-v1.5) |
| 预期收益 | (如: KB 检索 Recall@5 从 0.55 提升至 0.85) |
| 训练数据来源 | □ 自动采集（守门记录）□ 自动采集（LangFuse）□ 人工标注 |
| 训练数据量 | (预估条数) |
| 数据是否含 PII | □ 是（已完成脱敏）□ 否 |
| 数据是否含商业秘密 | □ 是（已完成去标识化）□ 否 |
| 训练环境 | □ 本地 GPU □ 云 GPU（需额外合规审批） |
| 风险评估 | (数据泄露风险/模型退化风险/业务中断风险) |
| 回滚预案 | (确认回滚方案已就绪，回滚时间 < 5 分钟) |

#### 《微调上线审批表》

| 项目 | 内容 |
|------|------|
| 微调模型 ID | |
| 离线评估 | □ 通过（报告附后） |
| 人工盲评 | □ 通过（新模型胜率: __%） |
| Staging 验证 | □ 通过 |
| 回滚预案 | □ 已就绪（回滚时间 < 5 分钟） |
| 监控告警 | □ 已配置新模型专属看板 |
| 审批 - AI 工程师 | 签字: ______ 日期: ______ |
| 审批 - 风控专家 | 签字: ______ 日期: ______ |
| 审批 - 技术负责人 | 签字: ______ 日期: ______ |
| 审批 - 风控负责人 | 签字: ______ 日期: ______（仅 Embedding 知识库迁移需要） |

### 9.3 团队与职责

| 角色 | 职责 | 时间投入 |
|------|------|---------|
| **AI 工程师** | 数据采集/清洗、训练执行、模型部署、监控配置 | 核心人力，占 60-80% 时间 |
| **风控专家** | 训练数据人工标注、盲评评测、生产效果验收 | 每周 2-4h |
| **技术负责人** | 方案审批、上线审批、架构决策 | 每阶段 1-2h |
| **风控负责人** | 高风险变更加签、合规审批 | 每阶段 0.5-1h |

---

## 十、风险管理

### 10.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 | 应急预案 |
|------|------|------|---------|---------|
| **过拟合** | 中 | 中 | 早停 (early stopping)、验证集监控、训练/验证 loss 曲线检查 | 回滚到旧模型 |
| **数据污染** | 低 | 高 | PII 自动扫描、人工抽检、数据版本锁定 | 立即下线，数据溯源，重新清洗训练 |
| **模型退化** | 中 | 中 | 每周自动漂移检测、关键指标告警 | 触发重训或回滚 |
| **知识库迁移中断** | 低 | 高 | 双表并行、后台分批迁移、断点续迁 | 暂停迁移，继续使用旧表 |
| **新模型性能倒退** | 中 | 高 | 多层质量门禁、金丝雀灰度、自动回滚触发 | 自动/手动回滚到旧模型 |
| **训练数据泄露** | 低 | 高 | MinIO Bucket 隔离、访问控制、审计日志 | 立即撤销权限、数据溯源、安全事件上报 |
| **云端 GPU 数据残留** | 低 | 中 | 训练后清理脚本、确认云端数据已删除 | 联系云服务商确认删除 |

### 10.2 过拟合检测

```python
class OverfittingDetector:
    """过拟合检测器 —— 训练过程中实时监控"""

    def __init__(self, patience: int = 3, threshold: float = 0.05):
        """
        patience: 连续 N 次评估 loss 不降反升 → 早停
        threshold: train_loss - eval_loss > threshold → 疑似过拟合
        """
        self.patience = patience
        self.threshold = threshold

    def check(self, train_loss: float, eval_loss: float, eval_metrics: dict) -> str:
        loss_gap = train_loss - eval_loss

        if loss_gap > self.threshold * 2:
            return "SEVERE_OVERFITTING"  # 严重过拟合，建议停止训练
        elif loss_gap > self.threshold:
            return "MILD_OVERFITTING"    # 轻度过拟合，增加 dropout / 减少 epoch
        elif eval_loss > self.best_eval_loss:
            self.no_improvement_count += 1
            if self.no_improvement_count >= self.patience:
                return "EARLY_STOP"      # 触发早停
        else:
            self.no_improvement_count = 0

        return "OK"
```

### 10.3 紧急回滚 SOP

```
场景: 新模型上线后检测到严重问题（如驳回率飙升 > 10%）

响应步骤:
  1. [立即, 5min] 确认告警
     ├── 检查 Prometheus 指标: 驳回率/错误率图表
     └── 确认不是误报（如风控系统本身故障导致的异常）

  2. [立即, 2min] 执行回滚
     ├── Embedding 模型: 切换 RAG 引擎 → 100% 使用旧向量表 kb_chunks
     ├── Reranker 模型: 切换 RAG Re-ranking → 使用旧 Reranker 模型
     └── 分类器: 关闭预筛 → 100% 走 LLM 推理

  3. [15min] 验证回滚效果
     ├── 观察驳回率是否恢复到基线水平
     └── 确认核心 API 功能正常

  4. [1h] 通知相关方
     ├── Elink 通知: 风控团队 + 技术团队
     └── 简要说明: 回滚原因、影响范围、预计恢复时间

  5. [24h] 根因分析
     ├── 对比新旧模型在退化场景上的输出差异
     ├── 检查训练数据是否存在偏差
     └── 输出《模型回滚根因分析报告》

  6. [1 周] 修复并重新上线
     ├── 根据根因分析修复模型
     └── 重新走完整灰度流程
```

---

## 十一、实施路线图与成本估算

### 11.1 实施路线图

```
Phase 1: 基础设施搭建 (Week 1-2)
├── 搭建 TrainingDataCollector（自动采集管道）
├── 搭建 MLflow 实验管理
├── 部署 Embedding/Reranker 微服务框架
├── 准备 GPU 环境（本地 RTX 4090 或云 GPU）
└── 开始积累训练数据（从 LangFuse + audit_log）

Phase 2: Embedding 模型微调 (Week 3-6)
├── Week 3: 采集 ≥ 5,000 条训练三元组
├── Week 4: 训练 + 离线评估 + 人工盲评
├── Week 5: 知识库双表迁移（后台 Celery 批量重建）
├── Week 6: 灰度发布 5%→20%→100%
└── 验收标准: KB 检索 Recall@5 提升 > 30%

Phase 3: Reranker 模型微调 (Week 7-10)
├── Week 7-8: 采集 ≥ 5,000 条 (query, doc, score) 训练对
├── Week 9: 训练 + 评估
├── Week 10: 灰度发布 + 效果验证
└── 验收标准: Top-5 Precision 提升 > 40%

Phase 4: 意图分流模型 (Week 11-13, 可选)
├── Week 11-12: 采集 ≥ 1,000 条历史 intake 案件
├── Week 12: 训练 + 评估
├── Week 13: 部署预筛层 + A/B 测试
└── 验收标准: LLM 调用量下降 > 30%，分流准确率不降

Phase 5: 持续优化 (长期)
├── 每月自动检测模型漂移
├── 每季度评估是否需要重新微调
├── 每半年用累积的新数据增量训练
└── 新 Agent 上线时补充该 Agent 场景的训练数据
```

### 11.2 成本估算

| 项目 | 一次性成本 | 说明 |
|------|----------|------|
| GPU 资源 | ¥0（已有 RTX 4090）或 ¥300（租赁 30h） | 总训练时间 ~15h |
| 数据标注（人工） | ¥0-2,000 | 风控专家每周 2h × 2 个月，可选 |
| 软件/工具 | ¥0 | 全部开源（FlagEmbedding/MLflow/ONNX） |
| **Embedding 微调** | **¥200-300**（云 GPU 租赁 20h） | — |
| **Reranker 微调** | **¥200-300**（云 GPU 租赁 20h） | — |
| **分类器微调** | **¥50-100**（云 GPU 租赁 5h） | — |
| **总计** | **¥450-700**（云 GPU）或 ¥0（自有 GPU） | 一次性 |

```
月度成本变化 (vs 纯 API 方案):
  之前: text-embedding-3-large API → ¥500-2,000/月
  之后: 本地 CPU 推理 → ¥0/月

  之前: 所有 intake 案件用 LLM → ¥500-1,500/月
  之后: 60-70% 走分类器 → 节省 ¥300-1,000/月

  合计节省: ¥800-3,000/月

ROI: 1 个月内回本（即使算上云 GPU 租赁成本）
```

### 11.3 成功标准

| 阶段 | 关键指标 | 目标值 |
|------|---------|--------|
| Embedding 微调 | KB 检索 Recall@5 | 0.55 → 0.85+ |
| Embedding 微调 | AI 引用检索结果的比例 | 基线 + 30% |
| Embedding 微调 | 驳回率（间接影响） | 基线 - 5% |
| Reranker 微调 | Top-5 Precision | 0.45 → 0.75+ |
| 分类器微调 | LLM 调用量降低 | 40%+ |
| 分类器微调 | 分流准确率 | 不低于原 LLM 水平 |
| 全局 | 月度 AI 服务成本 | 降低 20-30% |

---

## 附录 A：技术选型速查表

| 组件 | 选型 | 用途 |
|------|------|------|
| Embedding 基座 | `BAAI/bge-base-zh-v1.5` | 微调起点 |
| Reranker 基座 | `BAAI/bge-reranker-v2-minicpm-layerwise` | 微调起点 |
| 分类器基座 | `hfl/chinese-roberta-wwm-ext` | 微调起点 |
| 微调框架 | FlagEmbedding | Embedding + Reranker 训练 |
| 分类训练框架 | HuggingFace Transformers + Trainer | 分类器训练 |
| 实验管理 | MLflow (自部署) | 训练追踪 |
| 模型加速 | ONNX Runtime (Optimum) | CPU 推理加速 |
| 模型服务 | FastAPI | 模型微服务 |
| 训练硬件 | 1× RTX 4090 24GB | 本地训练 |

## 附录 B：与功能性架构的关系

| 微调目标 | 对应功能域 | 影响范围 |
|---------|-----------|---------|
| Embedding 模型 | RAG 召回系统 → 向量语义检索 | 全部 14 个 Agent |
| Reranker 模型 | RAG 召回系统 → Re-ranking 阶段 | 全部 14 个 Agent |
| 意图分流器 | 意图识别 → L2 阶段意图（辅助决策） | intake-agent |

## 附录 C：文档修订历史

| 版本 | 日期 | 修订说明 |
|------|------|----------|
| v1.0 | 2026-06-10 | 合并 small-model-fine-tuning-analysis.md 和 fine-tuning-architecture.md，聚焦小模型微调，补充数据治理、合规、模型退化监控、SOP 流程、风险管理等企业落地内容 |
