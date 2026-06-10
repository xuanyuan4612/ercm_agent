# 赫尔墨斯（Hermes）小模型微调务实分析

> **约束条件**：不能微调大参数模型（DeepSeek/Qwen 等），只能微调小参数模型。
> **核心问题**：微调什么小模型？在哪些场景能产生最大回报？
> **文档版本**：v1.0 | **最后更新**：2026-06-10

---

## 一、结论先行

**最值得微调的小模型只有 3 个，按优先级排：**

```
优先级 1 (必做):  Embedding 模型 → 提升全部 14 个 Agent 的 RAG 检索质量
优先级 2 (推荐): Reranker 模型  → 提升检索精度，减少"搜到了但不用"的问题
优先级 3 (可选): 意图分流模型   → 降低 intake-agent 的 LLM 调用成本

为什么要微调的模型一个都不要碰: 大 LLM（你微调不了）、Whisper/PaddleOCR（已够用）
```

---

## 二、当前系统的真实瓶颈分析

### 2.1 哪里最痛

从 Agent 设计文档中提取的实际监控指标：

| 指标 | 当前值（预期/告警线） | 痛点程度 | 能否用小模型解决 |
|------|---------------------|---------|----------------|
| **KB 检索结果不相关** | 匹配准确率 < 50% → P3 告警 | 🔴 高 | ✅ Embedding 微调直接解决 |
| **驳回率** | 多个 Agent > 30% → P1 告警 | 🔴 高 | ⚠️ 部分（RAG 质量提升可降驳回率） |
| **格式错误率** | 偶发 JSON 格式错误 | 🟡 中 | ❌ 小模型解决不了（需大模型微调） |
| **工具选择错误** | 复杂场景选错工具 | 🟡 中 | ❌ 小模型解决不了 |
| **分流决策不准** | 分流准确率 < 70% → P2 | 🟡 中 | ⚠️ 部分（可训练分类器辅助） |
| **LLM 延迟** | P95 > 15-20s | 🟢 低 | ❌ 与模型大小无关 |
| **检索延迟** | P95 > 3s → P3 | 🟢 低 | ❌ 基础设施问题 |

### 2.2 根因链分析

```
真正的根因链:

Embedding 模型不懂风控术语
        │
        ▼
  RAG 检索召回了不相关的文档
        │
        ├──→ LLM 缺少正确的上下文 → 推理质量下降 → 驳回率升高
        │
        ├──→ LLM 引用不存在的法规 → 幻觉 → 守门不通过
        │
        └──→ 用户不得不反复提供信息 → 多轮对话 → 延迟升高

这就是为什么 Embedding 微调是第一优先级：
修好一个 Embedding 模型，14 个 Agent 全部受益。
```

---

## 三、优先级 1：Embedding 模型微调（必须做）

### 3.1 为什么 Embedding 是最高优先级

```
当前架构中的 Embedding 角色:

每个 Agent 工作流阶段启动
    │
    ├── 1. RAG 检索 (依赖 Embedding 将查询转为向量)
    │       ├── PGVector 语义检索 ← 依赖 Embedding 质量
    │       └── ES 全文检索 (不依赖 Embedding)
    │
    ├── 2. 混合检索结果融合
    │
    ├── 3. 注入 System Prompt ← LLM 的"参考资料"
    │
    └── 4. LLM 推理 ← 如果参考资料不相关，推理必然差

问题:
  当前用的 text-embedding-3-large 是通用模型，
  它不知道 "窜货" 和 "跨区域销售" 是同一个意思，
  不知道 "围标" 和 "串通投标" 是同一类行为，
  不知道 COSO 框架的 "控制活动" 在企业语境下的含义。
```

### 3.2 微调什么模型

| 候选模型 | 参数量 | 维度 | 模型大小 | 单卡训练时间 | 推理速度 | 推荐度 |
|---------|--------|------|---------|------------|---------|--------|
| `bge-small-zh-v1.5` | 24M | 512d | ~95MB | ~30min (RTX 4090) | 极快 | ⭐⭐⭐ |
| `bge-base-zh-v1.5` | 102M | 768d | ~400MB | ~2h (RTX 4090) | 快 | ⭐⭐⭐⭐⭐ |
| `bge-large-zh-v1.5` | 326M | 1024d | ~1.3GB | ~4h (RTX 4090) | 中等 | ⭐⭐⭐⭐ |
| `stella-base-zh-v3` | 102M | 1792d | ~400MB | ~2h (RTX 4090) | 快 | ⭐⭐⭐⭐ |

**推荐：`bge-base-zh-v1.5`**

理由：
- 102M 参数，单张 RTX 4090 即可微调
- 768 维向量，比当前 1536 维节省一半存储，PGVector 索引更小更快
- BGE 系列中文效果经过大量验证
- 社区活跃，微调工具链成熟
- 成本和质量的平衡点最优

### 3.3 训练数据怎么来

这是最关键的问题——微调 Embedding 需要 `(query, positive_document, negative_document)` 三元组。

你的系统里有三个天然的数据源：

```
数据源 1: 守门审批记录（最直接，质量最高）
─────────────────────────────────────────────

场景: AI 生成了报告，引用了知识库中的文档片段
守门结果: approved → 说明引用的文档是相关的（正例）
         rejected → 说明引用的文档不相关或引用错误（负例）

采集方式:
  - 从 stage_outputs 中提取 AI 引用的文档 ID
  - 从 audit_log 中获取该阶段的审批结果
  - 自动构建: (Agent 的 RAG 检索 query, approved 的文档=正, rejected 的文档=负)


数据源 2: Agent 工作流的 RAG 检索记录（量大，质量中）
─────────────────────────────────────────────

场景: 每个 Agent 阶段启动时都会执行 RAG 检索
LangFuse 记录了每次检索的: query + 返回的 top_k 文档 + 最终 AI 是否使用了

采集方式:
  - 从 LangFuse traces 中导出 RAG 检索记录
  - AI 在回复中引用过的文档 → 正例候选
  - AI 未引用的文档 → 负例候选


数据源 3: 知识库文档的人工标注（质量最高，量小）
─────────────────────────────────────────────

场景: 风控专家标注 "对于 X 类问题，应该参考 Y 文档"

采集方式:
  - 让风控专家每周花 1-2 小时标注 20-30 对
  - 6 个月积累 500-700 对高质量数据
  - 这 500 对高质量数据的价值远超 5000 对自动采集数据
```

### 3.4 具体训练方案

```python
# 使用 FlagEmbedding (BGE 官方微调工具)
# 硬件: 1× RTX 4090 24GB（或 1× A4000 16GB）
# 时间: ~2 小时

# 训练数据格式 (JSONL)
# 每行: {"query": str, "pos": [str], "neg": [str]}

# 示例:
# {"query": "供应商围标串标的风险识别方法",
#  "pos": ["采购业务中围标串标行为的识别要点：1.分析投标供应商的IP地址是否相同..."],
#  "neg": ["员工差旅报销标准及审批流程..."]}
# {"query": "内控评价中采购循环的设计缺陷常见类型",
#  "pos": ["采购循环常见设计缺陷：1.采购申请与审批未分离..."],
#  "neg": ["销售循环的信用控制流程..."]}

# 训练命令 (FlagEmbedding):
# torchrun --nproc_per_node 1 train.py \
#   --model_name_or_path BAAI/bge-base-zh-v1.5 \
#   --train_data ./data/hermes_embedding_train.jsonl \
#   --output_dir ./models/hermes-bge-base-v1 \
#   --num_epochs 3 \
#   --per_device_train_batch_size 32 \
#   --learning_rate 2e-5 \
#   --max_seq_length 512
```

### 3.5 效果评估

微调前后在嵌入质量上的评估：

```python
class EmbeddingEvaluator:
    """Embedding 模型评估器"""

    def __init__(self, test_set: list[dict]):
        """
        test_set: 人工标注的测试集
        [{query: "...", relevant_doc: "...", irrelevant_doc: "..."}]
        建议至少 200 条，覆盖 14 个 Agent 的场景
        """
        self.test_set = test_set

    def evaluate(self, model) -> dict:
        metrics = {
            "recall_at_5": 0,      # Top-5 召回率（相关文档是否在前5）
            "recall_at_10": 0,     # Top-10 召回率
            "mrr": 0,              # Mean Reciprocal Rank
            "ndcg_at_5": 0,        # NDCG@5
        }

        for item in self.test_set:
            query_vec = model.encode(item["query"])
            # 在测试库中检索
            results = self.search(query_vec, top_k=10)

            # 计算指标
            ...

        return metrics

# 预期提升 (基于行业经验):
# 通用 Embedding → 领域微调 Embedding
# Recall@5:  0.55 → 0.85  (+55%)
# MRR:       0.40 → 0.72  (+80%)
```

### 3.6 部署方式

```
替换路径:

1. 训练完成 → 模型保存为 ~400MB 文件
2. 部署到现有的 Embedding 服务 (替换 text-embedding-3-large API 调用)
   - 方案 A: 用 sentence-transformers 库直接加载，CPU 推理
   - 方案 B: 部署为独立微服务 (FastAPI + sentence-transformers)
3. 修改 RAG 引擎的 Embedding 调用指向本地模型
4. 注意: 切换 Embedding 模型意味着所有向量的语义空间变了
   → 需要重新对知识库全量做一次 Embedding（后台 Celery 任务批量执行）
   → 知识库重建约需数小时（取决于文档总量），但可以后台渐进式执行
5. 旧向量表保留 30 天作为回滚备份

成本变化:
  之前: 调用 text-embedding-3-large API → ¥200-1,000/月
  之后: 本地 CPU 推理 → ¥0/月 + 少量 CPU 资源
```

---

## 四、优先级 2：Reranker 模型微调（强烈推荐）

### 4.1 为什么需要 Reranker

RAG 检索的两阶段流程中，Reranker 是第二阶段的质量守门员：

```
第一阶段: 粗筛（Embedding + ES 混合检索）
  PGVector 语义检索 (Top 20) + ES 全文检索 (Top 20)
  → RRF 融合 → 候选集 20-30 条

第二阶段: 精排（Reranker）  ← 这里最需要微调
  对候选集逐条计算(query, document)的相关性分数
  → 重排序 → Top 5 最相关的 → 注入 System Prompt
```

**为什么通用 Reranker 不够好**：

```
通用 Reranker 的问题:
  输入: "请分析该供应商是否存在围标嫌疑"
  文档 A: "围标串标的法律定义及处罚标准..."（法律法规）
  文档 B: "供应商 X 在 2025 年的投标记录分析..."（历史案例）
  通用 Reranker 可能给 A 更高的分数（因为"围标"关键词匹配度更高）

  但风控人员真正需要的是: 先看历史案例（B），再看法律法规（A）
  这就是领域偏好 —— 只能通过微调注入
```

### 4.2 微调什么模型

| 候选模型 | 参数量 | 大小 | 推理速度 | 推荐度 |
|---------|--------|------|---------|--------|
| `bge-reranker-base` | ~280M | ~1.1GB | ~50ms/对 | ⭐⭐⭐⭐ |
| `bge-reranker-v2-minicpm` | ~280M | ~1.1GB | ~40ms/对 | ⭐⭐⭐⭐⭐ |
| `bge-reranker-v2-m3` | ~568M | ~2.2GB | ~80ms/对 | ⭐⭐⭐ |

**推荐：`bge-reranker-v2-minicpm`**（效果和速度的平衡最佳）

### 4.3 训练数据怎么来

```python
# Reranker 训练数据格式: (query, document, relevance_score)
# 天然数据来源比 Embedding 更丰富:

# 来源 1: 碳基守门的审批记录（最强信号）
# 守门通过 → relevance = 1.0
# 守门驳回 → relevance = 0.0
# 守门修改后通过 → 原始引用的文档 relevance 降低

# 来源 2: AI 输出中的文档引用模式
# AI 在推理中主动引用了文档 → relevance = 0.8
# AI 检索到但未引用 → relevance = 0.3
# 用户手动指定了参考文档 → relevance = 1.0

# 来源 3: 人工标注（高质量小批量）
# 风控专家评估检索结果的相关性
# 每月标注 100 对 → 一年积累 1200 对

# 训练: 使用 FlagEmbedding 的 reranker 训练脚本
# 硬件: 1× RTX 4090，~3 小时
# 数据量: 5,000-10,000 对即可看到明显提升
```

### 4.4 预期效果

```
微调前后对比:
  Top-5 精准率 (Precision@5): 0.45 → 0.75
  NDCG@5:                    0.52 → 0.80
  检索延迟增加:               +50ms (可接受)
```

---

## 五、优先级 3：意图分流模型（可选但好用）

### 5.1 当前瓶颈

```
廉洁监察 intake-agent 的当前流程:

案件录入
  │
  ▼
LLM 推理 (DeepSeek, ~3-5s, ~¥0.02/次)
  │
  ├── 输出: should_investigate / should_transfer / is_hr_related 等
  │
  ▼
碳基守门 → 确认分流决策

问题:
  每天可能产生几十到上百个案件
  每个案件都要调用一次大模型做分流判断
  其中相当一部分案件的答案是"显而易见"的（信息明显不足、明显不归本部门管）
```

### 5.2 用小模型做预筛

```
改进方案: 小模型预筛 + 大模型兜底

案件录入
  │
  ▼
小模型分类器 (BERT-base, 110M 参数, < 50ms, ¥0/次)
  │
  ├── 高置信度 → 直接给出分流建议 → 碳基守门
  │
  └── 低置信度 → 交由大模型 (DeepSeek) 深度分析

预期:
  60-70% 的简单案件由小模型直接处理
  30-40% 的复杂案件转交大模型
  月度 LLM 调用成本降低 40-50%
```

### 5.3 微调什么模型

| 候选模型 | 参数量 | 大小 | 推理速度 | 推荐度 |
|---------|--------|------|---------|--------|
| `bert-base-chinese` | 110M | ~400MB | < 10ms (GPU) / < 50ms (CPU) | ⭐⭐⭐⭐ |
| `RoBERTa-wwm-ext-chinese` | 110M | ~400MB | < 10ms (GPU) | ⭐⭐⭐⭐⭐ |
| `ModernBERT-base-chinese` | 139M | ~500MB | < 8ms (GPU) | ⭐⭐⭐⭐ |

**推荐：`RoBERTa-wwm-ext-chinese`**（全词掩码，中文理解更好）

### 5.4 训练数据怎么来

这个模型的数据来源非常直接：

```python
# 训练数据: 历史 intake-agent 的输入和守门后的分流结果
# 数据量需求: 至少 1,000-2,000 条历史案件

# 输入特征:
#   - 案件来源 (fraud_source)
#   - 事业部 (client)
#   - 涉案金额区间
#   - 举报类型/风险场景分类
#   - 案件描述文本（截断到 512 tokens）
#   - 附件类型和数量

# 输出标签（多标签分类）:
#   - should_investigate: yes/no
#   - should_transfer: yes/no
#   - transfer_target: hr/legal/other/none
#   - risk_level: high/medium/low

# 训练: HuggingFace Trainer，1× RTX 4090，~1 小时
# 部署: FastAPI 微服务 + ONNX Runtime (CPU 推理 ~30ms)
```

### 5.5 预期效果与适用范围

```
分流准确率:  当前 LLM ~85% → 小模型预筛后整体 ~88%
延迟:        当前 LLM 3-5s → 小模型 < 50ms (CPU)
成本:        当前 ¥0.02/次 → 小模型 ¥0/次
适用:        仅限 intake-agent 的分流决策任务
             其他 13 个 Agent 不适用
```

---

## 六、不应该微调的模型（省钱的建议）

### 6.1 大 LLM — 微调不了，也不要尝试

```
DeepSeek / Qwen 等大模型:
  - 参数规模 70B+ → 全量微调需要 8-16 张 A100，成本 ¥50万+
  - LoRA 微调也需要 2-4 张 A100，成本 ¥2-5 万/次
  - 你有更好的替代方案: Prompt 工程 + RAG + 小模型辅助

结论: 大模型微调的 ROI 远低于 Embedding + Reranker 微调
```

### 6.2 Whisper — 不需要微调

```
Whisper large-v3 在你的场景中已经足够好:
  - 中文转录准确率 > 95%
  - 风控访谈的音频质量通常不差
  - 微调需要大量标注的音频数据，采集成本极高

结论: 不值得。如果发现某些专业术语转录不准，
     用后处理词典替换即可。
```

### 6.3 PaddleOCR / CLIP — 不需要微调

```
PaddleOCR 中文准确率已经很高
CLIP 做证据图像零样本分类已够用

结论: 当前够用，不折腾。
```

### 6.4 总结：省钱清单

| 模型 | 建议 | 原因 |
|------|------|------|
| DeepSeek (大 LLM) | ❌ 不微调 | 微调不了，用 Prompt + RAG 替代 |
| Qwen (备 LLM) | ❌ 不微调 | 同上 |
| Whisper large-v3 | ❌ 不微调 | 已够用 |
| PaddleOCR | ❌ 不微调 | 已够用 |
| CLIP | ❌ 不微调 | 已够用 |
| **Embedding** | ✅ 微调 | **ROI 最高** |
| **Reranker** | ✅ 微调 | **ROI 次高** |
| **意图分流器** | ✅ 微调（可选）| **降低成本** |

---

## 七、实施路线图

```
Month 1: Embedding 模型微调
├── Week 1-2: 数据采集
│   ├── 编写 TrainingDataCollector
│   ├── 从守门记录中提取 (query, pos_doc, neg_doc) 三元组
│   └── 目标: 5,000+ 条训练数据
│
├── Week 3: 训练 + 评估
│   ├── 在 RTX 4090 上微调 bge-base-zh-v1.5
│   ├── 在 200 条测试集上评估 Recall@5 / MRR
│   └── 目标: Recall@5 提升 > 30%
│
├── Week 4: 部署 + 知识库重建
│   ├── 替换 Embedding 模型
│   ├── Celery 后台批量重建 PGVector 索引
│   └── 新知识库上线，旧向量表保留 30 天
│
├── Week 5: 效果验证
│   ├── 观察 KB 检索命中率变化
│   ├── 观察驳回率变化
│   └── 目标: 驳回率下降 > 5%

Month 2: Reranker 模型微调
├── 数据采集: 5,000-10,000 对 (query, doc, relevance)
├── 训练: bge-reranker-v2-minicpm，3h
├── 部署: 接入 RAG 检索流水线的 Re-ranking 阶段
└── 验证: Top-5 精准率提升 > 50%

Month 3: 意图分流模型 (可选)
├── 数据采集: 1,000+ 条历史 intake 案件
├── 训练: RoBERTa-wwm-ext，1h
├── 部署: 作为 intake-agent 的预筛层
└── 验证: 月度 LLM 调用量下降 > 40%
```

---

## 八、成本估算

| 项目 | 一次性投入 | 说明 |
|------|----------|------|
| GPU 资源 | ¥0（已有或租赁 RTX 4090 ~¥10/h） | 总训练时间 ~10h → ¥100 |
| 数据标注 | ¥0（自动采集为主 + 少量人工） | 人工标注可选 |
| 部署服务器 | ¥0（现有 CPU 服务器） | Embedding/Reranker 用 CPU 推理 |
| Embedding 微调 | ¥100-200 | 训练 2h |
| Reranker 微调 | ¥150-300 | 训练 3h |
| 意图分流器微调 | ¥50-100 | 训练 1h |
| **总计** | **¥300-600** | 一次性 |

```
月度成本节省 (vs 纯 API 方案):
  Embedding API 节省: ¥200-1,000/月
  LLM API 节省 (分流器替代部分调用): ¥500-2,000/月
  合计: ¥700-3,000/月

ROI: 1 个月内回本
```

---

## 附录：与功能性架构的对应关系

本文档分析的三个微调目标在赫尔墨斯功能性架构中的位置：

| 微调目标 | 对应功能域 | 影响范围 |
|---------|-----------|---------|
| Embedding 模型 | RAG 召回系统 → 向量语义检索 | 全部 14 个 Agent |
| Reranker 模型 | RAG 召回系统 → Re-ranking 阶段 | 全部 14 个 Agent |
| 意图分流器 | 意图识别 → L2 阶段意图（辅助决策） | intake-agent |
