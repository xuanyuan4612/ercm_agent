# 赫尔墨斯（Hermes）模型微调架构设计

> **文档定位**：本文档定义赫尔墨斯系统中模型微调的完整架构，包括微调目标选择、训练数据管道、训练基础设施、评估框架、部署策略和持续优化闭环。
> **关联文档**：[功能性架构](functional-architecture.md) | [系统架构设计](architecture-design.md) | [Agent 详细设计](agents/)
> **文档版本**：v1.0 | **最后更新**：2026-06-10

---

## 目录

1. [为什么需要微调](#一为什么需要微调)
2. [微调目标矩阵](#二微调目标矩阵)
3. [训练数据管道](#三训练数据管道)
4. [训练基础设施](#四训练基础设施)
5. [评估框架](#五评估框架)
6. [部署与回滚策略](#六部署与回滚策略)
7. [持续优化闭环](#七持续优化闭环)
8. [微调 vs RAG vs Prompt 工程决策框架](#八微调-vs-rag-vs-prompt-工程决策框架)
9. [实施路线图](#九实施路线图)

---

## 一、为什么需要微调

### 1.1 现状与瓶颈

赫尔墨斯当前的架构完全依赖通用 LLM（DeepSeek） + RAG + Prompt 工程：

```
当前架构:
  用户请求 → Context Builder (RAG + Prompt) → 通用 LLM → 输出

痛点:
  1. 通用 LLM 对风控/审计领域的专业术语理解不够精确
  2. Prompt 越来越长 (已占用 ~12,700 tokens)，继续堆示例边际效益递减
  3. 某些任务的输出格式遵循率波动 (JSON Schema 偶尔偏差)
  4. 工具选择在复杂场景下准确率不够高
  5. 幻觉问题在法规引用场景中仍有出现
```

### 1.2 微调能解决什么

| 问题类型 | RAG/Prompt 工程 | 微调 | 最佳选择 |
|----------|----------------|------|----------|
| **领域知识注入** | ✅ 适合（新知识随时更新） | ⚠️ 知识固化，更新需重新训练 | RAG 为主 |
| **输出格式遵循** | ⚠️ 占用 Token 预算 | ✅ 直接训练进模型 | **微调** |
| **工具选择准确率** | ⚠️ 依赖 Few-shot 示例 | ✅ 可显著提升 | **微调** |
| **专业术语理解** | ⚠️ 需在 KB 中覆盖 | ✅ 融入模型语义空间 | **微调 + RAG** |
| **推理风格/角色扮演** | ⚠️ System Prompt 约束 | ✅ 训练进模型行为 | **微调** |
| **时效性知识** | ✅ 实时更新 | ❌ 无法即时更新 | RAG |
| **幻觉防控** | ⚠️ 需提示词约束 | ⚠️ 不能根本解决 | 两者结合 |
| **降低推理成本** | ❌ 长 Prompt 增加成本 | ✅ 可缩短 Prompt | **微调** |

### 1.3 赫尔墨斯的微调策略

采用 **"微调做减法 + RAG 做加法"** 的互补策略：

```
微调的目标:
  让模型 "学会怎么做" → 推理模式、输出格式、工具使用、角色定位

RAG 的目标:
  让模型 "知道是什么" → 具体制度法规、最新案例、组织结构、业务数据
```

---

## 二、微调目标矩阵

### 2.1 四大微调目标

赫尔墨斯定义了四个层级的微调目标，按优先级和价值排序：

```
┌─────────────────────────────────────────────────────────────────────┐
│                      微调目标层级金字塔                                 │
│                                                                      │
│                        ┌─────────────┐                               │
│                        │  L4: 偏好对齐 │  ← 最高价值，最难             │
│                        │  RLHF/DPO     │                               │
│                        ├─────────────┤                               │
│                        │  L3: 工具使用 │  ← 高价值，中等难度           │
│                        │  Tool Calling │                               │
│                        ├─────────────┤                               │
│                        │  L2: 领域知识 │  ← 中等价值，中等难度         │
│                        │  Domain FT    │                               │
│                        ├─────────────┤                               │
│                        │  L1: 指令遵循 │  ← 基础价值，较低难度         │
│                        │  Instruction  │                               │
│                        └─────────────┘                               │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 详细微调目标定义

#### L1: 指令遵循微调 (Instruction Fine-tuning)

| 维度 | 说明 |
|------|------|
| **目标** | 提升模型对 System Prompt 中输出格式约束的遵循率 |
| **微调对象** | 基础 LLM（DeepSeek/Qwen） |
| **训练数据** | 14 个 Agent 的 System Prompt + 期望的 JSON 输出 |
| **数据量** | ~5,000-10,000 条 instruction-output 对 |
| **训练方式** | SFT (Supervised Fine-Tuning) |
| **评估指标** | JSON Schema 遵循率、输出字段完整率、格式错误率 |
| **优先级** | ⭐⭐⭐⭐⭐ (最高，因为直接解决当前最痛的问题) |

**数据样例**：
```json
{
  "instruction": "你是一位资深案件初审官...[System Prompt]...请对以下案件做出初判：[案件信息]",
  "output": {
    "should_investigate": true,
    "should_transfer": false,
    "is_hr_related": false,
    "analysis_reason": "案件涉及...",
    "preliminary_direction": "建议从...方向展开调查",
    "risk_level": "高",
    "confidence": "high"
  }
}
```

#### L2: 领域知识微调 (Domain Fine-tuning)

| 维度 | 说明 |
|------|------|
| **目标** | 将风控/审计/反舞弊领域的专业知识融入模型参数 |
| **微调对象** | 基础 LLM（DeepSeek/Qwen） |
| **训练数据** | 风控知识对：法规条款理解、审计方法论、反舞弊调查技巧、COSO 框架、19 个业务循环知识 |
| **数据量** | ~20,000-50,000 条领域 QA 对 |
| **训练方式** | 持续预训练 (CPT) + SFT |
| **评估指标** | 领域术语理解准确率、法规引用准确率、专业建议合理性 |
| **优先级** | ⭐⭐⭐⭐ |

**数据来源**：
- 知识库中的制度法规 → QA 对生成
- 历史案件的分析结论 → 推理链标注
- 内控评价的缺陷判断 → 标准答案提取
- 专家人工标注的高质量 QA

**数据样例**：
```json
{
  "instruction": "根据《企业内部控制应用指引第7号——采购业务》，请说明采购验收环节的关键控制点",
  "output": "根据该指引，采购验收环节的关键控制点包括：\n1. 验收标准明确：企业应当制定明确的采购验收标准...\n2. 验收人员独立：验收人员应当独立于采购人员和仓储人员...\n3. 异常情况处理：验收过程中发现的异常情况...\n4. 验收记录完整：所有验收活动应当形成书面记录..."
}
```

#### L3: 工具使用微调 (Tool-use Fine-tuning)

| 维度 | 说明 |
|------|------|
| **目标** | 提升模型在正确时机选择正确工具的能力 |
| **微调对象** | 基础 LLM（DeepSeek/Qwen） |
| **训练数据** | ReAct 循环中的完整交互序列：用户/系统需求 → 工具选择 → 参数填充 → 结果解读 |
| **数据量** | ~10,000-30,000 条多轮工具调用序列 |
| **训练方式** | SFT (含 Function Calling 格式) |
| **评估指标** | 工具选择准确率、参数正确率、工具调用效率（平均工具调用次数） |
| **优先级** | ⭐⭐⭐⭐ |

**数据来源**：
- 从 LangFuse 中导出已成功的多轮工具调用序列
- 碳基守门通过的任务（说明工具使用正确）
- 补充人工标注的复杂工具链场景

**数据样例**：
```json
{
  "messages": [
    {"role": "system", "content": "你是风险分析Agent...[System Prompt]"},
    {"role": "user", "content": "请分析采购部门最近30天的异常交易"},
    {"role": "assistant", "content": "我先检索相关风险规则..."},
    {"role": "assistant", "tool_calls": [
      {"id": "call_1", "function": {"name": "kb_search_risk_rules", "arguments": "{\"query\": \"采购 异常交易 风险规则\", \"kb_type\": \"risk_rules\", \"top_k\": 5}"}}
    ]},
    {"role": "tool", "content": "[检索结果: 3条相关规则...]"},
    {"role": "assistant", "content": "已获取3条相关规则，现在执行SQL查询..."},
    {"role": "assistant", "tool_calls": [
      {"id": "call_2", "function": {"name": "sql_batch_execute", "arguments": "{\"sql\": \"SELECT ... FROM procurement WHERE ...\", \"timeout\": 30}"}}
    ]}
  ]
}
```

#### L4: 偏好对齐微调 (Preference Alignment)

| 维度 | 说明 |
|------|------|
| **目标** | 将模型输出偏好对齐到碳基守门的实际决策标准 |
| **微调对象** | 经过 L1+L2 微调的模型 |
| **训练数据** | 守门对比对：AI 原始输出 vs 碳基修改后输出（偏好数据） |
| **数据量** | ~5,000-15,000 条对比对（持续积累） |
| **训练方式** | DPO (Direct Preference Optimization) 或 RLHF |
| **评估指标** | 碳基采纳率、修改幅度、驳回率 |
| **优先级** | ⭐⭐⭐ (中期目标，依赖 L1-L3 的积累) |

**数据来源**：
- 碳基守门中的 "approved"（正例）vs "rejected"（负例）
- 碳基守门中的 "modified" → AI 原始输出（负）vs 碳基修改后（正）
- 同案件不同处置路径的人工选择

**DPO 数据样例**：
```json
{
  "prompt": "[System Prompt] 请对以下案件做出初判：[案件信息]",
  "chosen": "{\"should_investigate\": true, \"risk_level\": \"高\", \"transfer_target\": null, ...}",
  "rejected": "{\"should_investigate\": true, \"risk_level\": \"中\", \"transfer_target\": \"hr\", ...}"
}
```

### 2.3 微调目标优先级路线图

```
Phase 1 (0-3 个月): L1 指令遵循微调
  ├── 解决最痛的 JSON 格式遵循问题
  ├── 14 个 Agent 的 System Prompt → output pairs 自动生成
  ├── SFT 训练, 2-4 周完成
  └── 预期提升: 格式遵循率 70% → 95%+

Phase 2 (3-6 个月): L3 工具使用微调
  ├── 积累 3 个月的 ReAct 工具调用轨迹
  ├── SFT 训练, 4-6 周完成
  └── 预期提升: 工具选择准确率 75% → 90%+

Phase 3 (6-12 个月): L2 领域知识微调
  ├── 积累足够的高质量领域 QA 对
  ├── CPT + SFT, 8-12 周完成
  └── 预期提升: 法规引用准确率 80% → 93%+

Phase 4 (12+ 个月): L4 偏好对齐微调
  ├── 积累 12 个月以上的守门对比数据
  ├── DPO 训练, 4-6 周完成
  └── 预期提升: 碳基采纳率持续提升
```

---

## 三、训练数据管道

### 3.1 数据管道全景

```
┌─────────────────────────────────────────────────────────────────────┐
│                      训练数据管道 (Data Pipeline)                        │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Stage 1: 数据采集 (Data Collection)                            │   │
│  │  ──────────────────────────────────────────────────────────── │   │
│  │                                                                │   │
│  │  数据源1: 运行系统日志                                           │   │
│  │  ├── LangFuse: 每次 LLM 调用的 input/output/tools              │   │
│  │  ├── audit_log: 碳基守门审批记录 (approved/rejected/modified)    │   │
│  │  ├── stage_outputs: AI 各阶段产出物（结构化 JSON）              │   │
│  │  └── tool_call_logs: ReAct 循环中的工具调用轨迹                  │   │
│  │                                                                │   │
│  │  数据源2: 知识库内容                                             │   │
│  │  ├── 制度法规文档 → LLM 生成 QA 对 → 人工校验                   │   │
│  │  ├── 历史案件报告 → 关键决策点标注                               │   │
│  │  └── 内控矩阵 → 控制活动分类标注                                 │   │
│  │                                                                │   │
│  │  数据源3: 人工标注                                               │   │
│  │  ├── 风控专家标注的高质量问题 (优先)                              │   │
│  │  ├── 碳基守门中的 "modified" 修改记录                            │   │
│  │  └── Golden Test Set 的标准答案                                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Stage 2: 数据清洗 (Data Cleaning)                               │   │
│  │  ──────────────────────────────────────────────────────────── │   │
│  │                                                                │   │
│  │  自动化清洗规则:                                                │   │
│  │  ├── PII 脱敏 (姓名/电话/邮箱/身份证号 → 占位符替换)            │   │
│  │  ├── 租户去标识化 (ecovacs/tineco → org_a/org_b)               │   │
│  │  ├── JSON 格式校验 (过滤格式错误的输出)                         │   │
│  │  ├── 去重 (相似度 > 0.95 的样本视为重复)                        │   │
│  │  ├── 长度过滤 (output 为空或过短的样本丢弃)                     │   │
│  │  └── 敏感内容过滤 (含真实金额/具体人名/公司名的样本标记审查)     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Stage 3: 数据标注 (Data Labeling)                               │   │
│  │  ──────────────────────────────────────────────────────────── │   │
│  │                                                                │   │
│  │  自动化标注 (Auto-labeling, 低成本):                             │   │
│  │  ├── L1 指令遵循: 从 System Prompt 自动生成期望输出格式          │   │
│  │  ├── L3 工具使用: 从成功完成的任务中提取工具调用链               │   │
│  │  └── L4 偏好对齐: 从 audit_log 中自动提取 chosen/rejected 对    │   │
│  │                                                                │   │
│  │  人工标注 (Human-labeling, 高成本):                              │   │
│  │  ├── L2 领域 QA: 风控专家编写或审核 LLM 生成的 QA 对            │   │
│  │  ├── 复杂工具链: 人工标注正确的多步骤工具调用路径                │   │
│  │  └── 高质量偏好数据: 风控专家对比评估不同 AI 输出                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Stage 4: 数据格式转换 (Format Conversion)                       │   │
│  │  ──────────────────────────────────────────────────────────── │   │
│  │                                                                │   │
│  │  根据微调框架输出标准格式:                                       │   │
│  │  ├── HuggingFace ChatML 格式 (通用)                             │   │
│  │  ├── OpenAI Fine-tuning JSONL 格式 (如果用 OpenAI 微调服务)     │   │
│  │  ├── LLaMA-Factory 格式 (自部署训练)                            │   │
│  │  └── 数据集拆分: Train 80% / Validation 10% / Test 10%         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Stage 5: 数据存储与版本管理 (Data Versioning)                   │   │
│  │  ──────────────────────────────────────────────────────────── │   │
│  │                                                                │   │
│  │  存储: MinIO bucket: hermes-training-data                      │   │
│  │  版本: dataset_name-v{version}-{date}  (如: instr-ft-v2-20260601)│
│  │  元数据:                                                        │   │
│  │    ├── 样本数量、数据来源分布、标注方式                           │   │
│  │    ├── 对应的 Agent 列表、任务类型分布                           │   │
│  │    └── 质量评分 (自动标注 vs 人工标注比例)                       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 从运行系统自动采集数据的实现

```python
class TrainingDataCollector:
    """训练数据采集器 - 从运行系统中自动采集和标注训练数据"""

    def __init__(
        self,
        langfuse_client: LangFuseClient,
        db_session: AsyncSession,
        audit_log_service: AuditLogService,
    ):
        self.langfuse = langfuse_client
        self.db = db_session
        self.audit_log = audit_log_service

    # ==================== L1 指令遵循数据 ====================
    async def collect_instruction_data(
        self,
        start_date: date,
        end_date: date,
        quality_threshold: float = 0.7,
    ) -> list[InstructionSample]:
        """
        从成功完成的任务中采集指令遵循训练数据。

        逻辑:
        - 筛选守门通过 (approved) 的任务
        - 提取 System Prompt (instruction) + AI 输出 (output)
        - AI 输出已经是符合格式的 JSON，天然适合做训练数据
        """
        # 1. 从 LangFuse 查询成功完成的 Agent 调用
        traces = await self.langfuse.get_traces(
            agent_ids=ALL_AGENT_IDS,
            start_date=start_date,
            end_date=end_date,
            filters={"success": True, "output_format": "json"},
        )

        samples = []
        for trace in traces:
            # 2. 检查守门结果（只采用被审批通过的）
            approval = await self.audit_log.get_approval(
                case_id=trace.case_id,
                stage=trace.stage,
            )
            if approval and approval.result != "approved":
                continue  # 跳过被驳回或修改的

            # 3. 构建 instruction-output 对
            sample = InstructionSample(
                instruction=trace.system_prompt,   # System Prompt 作为 instruction
                input=self._format_user_input(trace),  # 用户输入
                output=trace.output,               # AI 输出（JSON 格式，已验证）
                source="auto",
                agent_id=trace.agent_id,
                quality_score=self._calc_quality(trace, approval),
            )
            samples.append(sample)

        # 4. 过滤低质量样本
        samples = [s for s in samples if s.quality_score >= quality_threshold]

        return samples

    # ==================== L3 工具使用数据 ====================
    async def collect_tool_use_data(
        self,
        start_date: date,
        end_date: date,
    ) -> list[ToolUseSample]:
        """
        从 ReAct 循环中采集工具使用训练数据。

        逻辑:
        - 提取完整的多轮 tool calling 序列
        - 只采集最终任务成功的序列
        """
        traces = await self.langfuse.get_traces(
            agent_ids=TOOL_USING_AGENT_IDS,
            start_date=start_date,
            end_date=end_date,
            filters={"has_tool_calls": True, "success": True},
        )

        samples = []
        for trace in traces:
            # 提取完整的 messages 序列（含 tool_calls）
            messages = self._extract_react_messages(trace)

            # 只保留有效的工具调用序列
            if self._is_valid_tool_sequence(messages):
                sample = ToolUseSample(
                    messages=messages,
                    agent_id=trace.agent_id,
                    tools_used=[t.name for t in trace.tool_calls],
                    success=True,
                    source="auto",
                )
                samples.append(sample)

        return samples

    # ==================== L4 偏好对齐数据 ====================
    async def collect_preference_data(
        self,
        start_date: date,
        end_date: date,
    ) -> list[PreferenceSample]:
        """
        从碳基守门记录中采集偏好对齐数据。

        逻辑:
        - approved: AI 输出=chosen, 不需要 rejected (但可与他案对比)
        - rejected: AI 输出=rejected, 后续重新生成的通过版本=chosen
        - modified: AI 原始输出=rejected, 碳基修改版=chosen
        """
        approvals = await self.audit_log.get_approvals_with_diff(
            start_date=start_date,
            end_date=end_date,
        )

        samples = []
        for approval in approvals:
            if approval.result == "modified" and approval.modified_output:
                # 修改场景：AI 原始输出 vs 人工修改版
                samples.append(PreferenceSample(
                    prompt=approval.system_prompt,
                    chosen=approval.modified_output,   # 人工修改后 = 正例
                    rejected=approval.ai_output,        # AI 原始 = 负例
                    source="manual_modification",
                ))
            elif approval.result == "rejected":
                # 驳回场景：找到该阶段后续通过的版本
                subsequent_approved = await self._find_subsequent_approved(
                    approval.case_id, approval.stage
                )
                if subsequent_approved:
                    samples.append(PreferenceSample(
                        prompt=approval.system_prompt,
                        chosen=subsequent_approved.ai_output,  # 后续通过版 = 正例
                        rejected=approval.ai_output,            # 被驳回版 = 负例
                        source="rejection_retry",
                    ))

        return samples

    def _calc_quality(
        self, trace: Trace, approval: Approval
    ) -> float:
        """计算样本质量评分"""
        score = 0.0
        # JSON 格式是否完整
        if self._is_valid_json(trace.output):
            score += 0.3
        # 所有必填字段是否都有值
        if self._all_fields_filled(trace.output, trace.agent_id):
            score += 0.3
        # 守门结果 (approved=满分, modified=0.5, rejected=0)
        score += {"approved": 0.4, "modified": 0.2, "rejected": 0}[approval.result]
        return score
```

### 3.3 数据质量保障

```
┌─────────────────────────────────────────────────────────────────────┐
│                      数据质量保障机制                                   │
│                                                                      │
│  自动化质量检查 (每次数据采集后执行):                                   │
│  ├── JSON Schema 校验: 输出是否符合目标格式                             │
│  ├── 字段完整性: 必填字段是否都有值                                     │
│  ├── Token 长度分布: 排除异常长/短的样本 (3σ 原则)                      │
│  ├── 内容重复度: 相似度 > 0.95 的样本视为重复并去重                     │
│  ├── 敏感数据扫描: 检查是否含有未脱敏的 PII                             │
│  └── Agent 分布均衡: 确保 14 个 Agent 的样本量相对均衡                 │
│                                                                      │
│  人工质量抽检 (每周):                                                  │
│  ├── 随机抽取 50 条样本 → 风控专家审核                                  │
│  ├── 标记质量等级 (A/B/C)                                              │
│  ├── 收集标注反馈 → 更新自动化质量规则                                  │
│  └── 质量 KPI: A 级 > 60%, A+B 级 > 85%                                │
│                                                                      │
│  数据防护:                                                            │
│  ├── 所有训练数据存储在 MinIO 隔离 Bucket                               │
│  ├── 数据仅用于训练，不对外传输                                        │
│  ├── 训练任务结束后清理 GPU 集群上的中间数据                            │
│  └── 审计日志记录每次数据采集操作                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 四、训练基础设施

### 4.1 训练架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                      训练基础设施架构                                   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    训练编排层 (Training Orchestrator)             │   │
│  │                                                                  │   │
│  │  TrainingPipeline:                                               │   │
│  │    ├── 触发: 定时 (每月/每季度) 或 手动 (数据量达到阈值)          │   │
│  │    ├── 流程: 数据采集 → 清洗 → 格式转换 → 训练 → 评估 → 部署     │   │
│  │    └── 通知: 训练完成/失败 → Elink + 邮件通知                    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    训练执行层 (Training Executor)                 │   │
│  │                                                                  │   │
│  │  环境选择:                                                       │   │
│  │                                                                  │   │
│  │  方案 A: 云端 API 微调 (推荐初期使用)                              │   │
│  │  ├── DeepSeek Fine-tuning API (如提供)                            │   │
│  │  ├── 阿里云 PAI 平台 (通义千问微调)                               │   │
│  │  ├── 优点: 免运维, 快速启动                                       │   │
│  │  └── 缺点: 数据传出, 成本随数据量增长                             │   │
│  │                                                                  │   │
│  │  方案 B: 自建 GPU 训练集群 (推荐长期使用)                          │   │
│  │  ├── 框架: LLaMA-Factory / Axolotl / DeepSpeed                   │   │
│  │  ├── GPU: 4-8× NVIDIA A100 80G 或 H100                           │   │
│  │  ├── 模型: 从 HuggingFace 下载基础模型                            │   │
│  │  ├── 训练: LoRA/QLoRA (低资源) 或 Full Fine-tuning (全量)        │   │
│  │  ├── 优点: 数据不出网, 完全控制, 长期成本低                       │   │
│  │  └── 缺点: 需运维, 初始投入大                                     │   │
│  │                                                                  │   │
│  │  方案 C: 混合方案 (推荐)                                          │   │
│  │  ├── Phase 1-2: 用云端 API 快速验证效果                           │   │
│  │  ├── Phase 3-4: 在自建 GPU 集群上做深度微调                       │   │
│  │  └── 迁移时机: 月训练成本 > GPU 租赁成本时                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    模型存储与版本管理 (Model Registry)             │   │
│  │                                                                  │   │
│  │  模型命名规范: {base_model}-{ft_type}-{version}-{date}          │   │
│  │  示例: deepseek-v4-l1-instr-v2-20260601                          │   │
│  │                                                                   │   │
│  │  存储: MinIO bucket: hermes-models                                │   │
│  │  存储内容:                                                        │   │
│  │    ├── LoRA adapters (低资源微调权重)                              │   │
│  │    ├── 合并后的完整模型 (Full fine-tuning)                         │   │
│  │    ├── 训练配置 (config.yaml)                                     │   │
│  │    ├── 训练指标 (loss curve, eval metrics)                       │   │
│  │    └── 数据集版本引用 (训练用了哪些数据)                           │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 训练技术方案选择

| 微调层级 | 推荐技术 | 参数规模 | GPU 需求 | 训练时间 | 推理成本 |
|----------|---------|---------|---------|---------|---------|
| **L1 指令遵循** | LoRA (rank=64) | ~0.1% 基座参数 | 1-2× A100 | 2-4h | 无变化（合并后） |
| **L2 领域知识** | QLoRA + CPT | ~0.5% 基座参数 | 4-8× A100 | 24-72h | 无变化（合并后） |
| **L3 工具使用** | LoRA (rank=128) | ~0.2% 基座参数 | 2-4× A100 | 4-8h | 无变化（合并后） |
| **L4 偏好对齐** | DPO (LoRA rank=64) | ~0.1% 基座参数 | 2-4× A100 | 4-6h | 无变化（合并后） |

**为什么优先选 LoRA/QLoRA**：
1. 显存需求低，1-2 张 A100 即可开始
2. 训练速度快，L1 指令微调可在几小时内完成
3. 权重文件小（~100MB vs 完整模型 ~100GB），存储和分发方便
4. 可叠加多个 LoRA Adapter（基础模型 + L1 Adapter + L3 Adapter）
5. 试验成本低，可快速迭代不同超参数

### 4.3 训练 Pipeline 代码示意

```python
class TrainingPipeline:
    """微调训练 Pipeline"""

    def __init__(
        self,
        data_collector: TrainingDataCollector,
        model_registry: ModelRegistry,
        compute_provider: str,  # "cloud" | "self-hosted"
    ):
        self.data_collector = data_collector
        self.model_registry = model_registry
        self.compute_provider = compute_provider

    async def run(
        self,
        ft_type: FineTuneType,      # L1/L2/L3/L4
        base_model: str,             # "deepseek-v4-pro" / "qwen3.7-plus"
        dataset_version: str | None = None,
        dry_run: bool = False,
    ) -> TrainingResult:
        """
        执行完整的微调 Pipeline
        """
        # ============ Step 1: 数据准备 ============
        logger.info(f"Step 1/6: 准备 {ft_type} 训练数据...")

        if dataset_version:
            # 使用已有数据集版本
            dataset = await self.model_registry.load_dataset(dataset_version)
        else:
            # 从运行系统自动采集
            collector_map = {
                FineTuneType.L1: self.data_collector.collect_instruction_data,
                FineTuneType.L3: self.data_collector.collect_tool_use_data,
                FineTuneType.L4: self.data_collector.collect_preference_data,
                # L2 需要额外的人工标注数据
            }
            raw_data = await collector_map[ft_type](...)
            dataset = self._clean_and_format(raw_data, ft_type)

        logger.info(f"    数据量: {len(dataset.train)} train / "
                    f"{len(dataset.val)} val / {len(dataset.test)} test")

        # ============ Step 2: 数据上传 ============
        logger.info("Step 2/6: 上传训练数据...")
        dataset_uri = await self._upload_dataset(dataset)

        # ============ Step 3: 启动训练 ============
        if dry_run:
            return TrainingResult(status="dry_run")

        logger.info(f"Step 3/6: 启动 {ft_type} 微调训练...")
        job = await self._launch_training_job(
            base_model=base_model,
            dataset_uri=dataset_uri,
            ft_type=ft_type,
            training_config=self._get_training_config(ft_type),
        )

        # ============ Step 4: 等待完成 ============
        logger.info("Step 4/6: 等待训练完成...")
        result = await self._wait_for_completion(job)

        if not result.success:
            raise TrainingFailedError(result.error)

        logger.info(f"    训练完成, loss: {result.final_loss:.4f}, "
                    f"耗时: {result.duration_min:.0f}min")

        # ============ Step 5: 自动评估 ============
        logger.info("Step 5/6: 在 Golden Test Set 上评估...")
        eval_results = await self._evaluate(
            model_path=result.model_path,
            ft_type=ft_type,
            test_set=dataset.test,
        )

        # 检查是否通过质量门禁
        checks = self._run_quality_gates(ft_type, eval_results)
        if not all(checks.values()):
            failed = [k for k, v in checks.items() if not v]
            raise QualityGateFailedError(f"质量门禁未通过: {failed}")

        # ============ Step 6: 注册模型 ============
        logger.info("Step 6/6: 注册模型到 Model Registry...")
        model_version = await self.model_registry.register(
            model_path=result.model_path,
            ft_type=ft_type,
            base_model=base_model,
            dataset_version=dataset.version,
            eval_results=eval_results,
            metadata={
                "train_samples": len(dataset.train),
                "final_loss": result.final_loss,
                "duration_min": result.duration_min,
            },
        )

        return TrainingResult(
            status="success",
            model_version=model_version,
            eval_results=eval_results,
        )

    def _run_quality_gates(
        self, ft_type: FineTuneType, eval_results: dict
    ) -> dict[str, bool]:
        """质量门禁检查"""
        gates = {
            FineTuneType.L1: {
                "json_schema_compliance": eval_results["json_schema_rate"] >= 0.95,
                "field_completeness": eval_results["field_completeness"] >= 0.90,
                "format_error_rate": eval_results["format_error_rate"] <= 0.05,
            },
            FineTuneType.L3: {
                "tool_selection_accuracy": eval_results["tool_acc"] >= 0.85,
                "arg_correctness": eval_results["arg_acc"] >= 0.80,
                "task_success_rate": eval_results["task_success"] >= 0.90,
            },
            # L2, L4 的门禁条件略...
        }
        return gates.get(ft_type, {})
```

---

## 五、评估框架

### 5.1 多维度评估体系

```
┌─────────────────────────────────────────────────────────────────────┐
│                      微调评估框架                                       │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 维度 1: 自动化基准评估 (Benchmark Evaluation)                     │   │
│  │ ──────────────────────────────────────────────────────────── │   │
│  │                                                                │   │
│  │ Golden Test Set: 每个 Agent 的 3-5 个标准测试用例                │   │
│  │   ├── 评估方式: 微调前 vs 微调后 分别跑全部 Golden Test Set      │   │
│  │   ├── 评估指标: JSON Schema 遵循率 / 字段完整性 / 标量值准确率   │   │
│  │   └── 门禁: 所有 Agent 的指标不得退化 > 5%                       │   │
│  │                                                                │   │
│  │ Agent 专项评测集: 每个 Agent 100-200 条专项测试用例              │   │
│  │   ├── 覆盖任务类型的各种变体                                      │   │
│  │   └── 包含边界案例和异常输入                                      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 维度 2: 人工评估 (Human Evaluation)                               │   │
│  │ ──────────────────────────────────────────────────────────── │   │
│  │                                                                │   │
│  │ 盲评对比:                                                       │   │
│  │   ├── 评测员: 2-3 位风控专家                                    │   │
│  │   ├── 评测量: 每个 Agent 随机抽取 30 个真实案例                   │   │
│  │   ├── 对比方式: 同时展示微调前/微调后的输出 (随机顺序，盲评)      │   │
│  │   ├── 评分维度: 准确性 / 完整性 / 可操作性 / 专业度 (1-5分)      │   │
│  │   └── 门禁: 微调后评分 ≥ 微调前评分                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 维度 3: 在线评估 (Online A/B Testing)                             │   │
│  │ ──────────────────────────────────────────────────────────── │   │
│  │                                                                │   │
│  │ 灰度发布期间的在线指标对比:                                      │   │
│  │   ├── 碳基采纳率 (approved/all)                                 │   │
│  │   ├── 碳基驳回率 (rejected/all)                                 │   │
│  │   ├── 碳基修改率 (modified/all)                                 │   │
│  │   ├── AI 输出到达守门后的人工修改幅度                             │   │
│  │   ├── 从提交到审批通过的平均耗时                                  │   │
│  │   └── LLM Token 消耗 (Prompt 是否因微调而可以缩短)              │   │
│  │                                                                │   │
│  │ 统计显著性检验:                                                  │   │
│  │   └── 至少积累 200+ 次交互后检验 p < 0.05                       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 评估结果报告模板

```python
class FineTuningEvaluationReport:
    """微调评估报告"""

    model_version: str              # "deepseek-v4-l1-instr-v2-20260601"
    base_model: str                 # "deepseek-v4-pro"
    ft_type: FineTuneType           # L1
    dataset_version: str

    # ============ 自动化评测 ============
    benchmark: dict = {
        # Golden Test Set 结果
        "golden_test_set": {
            "total_cases": 62,               # 14 Agent × ~4.4 cases
            "passed_before": 43,             # 微调前通过数
            "passed_after": 58,              # 微调后通过数
            "improvement": "+24.2%",
        },
        # 分 Agent 指标
        "per_agent_metrics": [
            {
                "agent_id": "intake-agent",
                "json_schema_rate": {"before": 0.68, "after": 0.97, "delta": "+0.29"},
                "field_completeness": {"before": 0.82, "after": 0.96, "delta": "+0.14"},
                "format_error_rate": {"before": 0.21, "after": 0.03, "delta": "-0.18"},
            },
            # ... 其余 13 个 Agent
        ],
        # 退化检测
        "regression_check": {
            "agents_with_regression": [],    # 任何 Agent 指标退化 > 5%
            "passed": True,
        }
    }

    # ============ 人工评测 ============
    human_eval: dict = {
        "evaluators": 3,
        "samples_per_agent": 30,
        "blind_test": {
            "win_rate": 0.72,           # 微调后更优的比例
            "tie_rate": 0.21,            # 持平
            "lose_rate": 0.07,           # 微调前更优
        },
        "average_score": {
            "accuracy": {"before": 3.2, "after": 4.1, "delta": "+0.9"},
            "completeness": {"before": 3.5, "after": 4.0, "delta": "+0.5"},
            "actionability": {"before": 3.0, "after": 3.8, "delta": "+0.8"},
            "professionalism": {"before": 3.3, "after": 3.9, "delta": "+0.6"},
        },
    }

    # ============ 质量门禁结果 ============
    quality_gates: dict = {
        "json_schema_rate >= 0.95": True,
        "field_completeness >= 0.90": True,
        "format_error_rate <= 0.05": True,
        "no_regression": True,
        "human_eval_win_rate >= 0.50": True,
        "all_passed": True,
    }
```

---

## 六、部署与回滚策略

### 6.1 部署架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    微调模型部署架构                                     │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    LLM Adapter 层 (模型路由)                      │   │
│  │                                                                  │   │
│  │  class LLMAdapter:                                               │   │
│  │                                                                  │   │
│  │      # 模型路由配置                                               │   │
│  │      MODEL_ROUTING = {                                            │   │
│  │          # 默认: 使用微调模型                                      │   │
│  │          "default": "deepseek-v4-l1-instr-v2-20260601",           │   │
│  │                                                                   │   │
│  │          # 灰度: 10% 流量用新微调模型                              │   │
│  │          "canary": {                                               │   │
│  │              "model": "deepseek-v4-l3-tool-v1-20260701",          │   │
│  │              "traffic_ratio": 0.1,                                 │   │
│  │              "hash_key": "task_id",                                │   │
│  │          },                                                        │   │
│  │                                                                   │   │
│  │          # 特定 Agent 可指定专用模型                               │   │
│  │          "agent_overrides": {                                      │   │
│  │              "risk-analysis-agent": "deepseek-v4-l1-instr-v3",    │   │
│  │          },                                                        │   │
│  │      }                                                             │   │
│  │                                                                   │   │
│  │      async def invoke(self, messages, agent_id, ...):             │   │
│  │          # 1. 确定使用哪个模型                                     │   │
│  │          model = self._resolve_model(agent_id, task_id)           │   │
│  │                                                                   │   │
│  │          # 2. 加载对应的 Adapter (LoRA weights)                    │   │
│  │          adapter = self.model_registry.load(model)                │   │
│  │                                                                   │   │
│  │          # 3. 调用推理                                             │   │
│  │          return await adapter.invoke(messages)                    │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 金丝雀部署流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                    微调模型金丝雀部署流程                                │
│                                                                      │
│  Step 1: 模型注册 (Model Registry)                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  训练完成 → 质量门禁通过 → 注册为 "staging" 状态                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  Step 2: Staging 环境验证 (非生产流量, 1-2 天)                         │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  在 Staging 环境使用脱敏数据跑全部 Golden Test Set + 专项评测集  │   │
│  │  验证点: 所有指标不得退化 > 2%                                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  Step 3: 金丝雀 5% (生产环境, 3 天)                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  按 task_id 哈希, 5% 流量路由到新模型                           │   │
│  │  监控: 碳基采纳率、驳回率、Token 消耗、P95 延迟                  │   │
│  │  回滚条件: 采纳率下降 > 5% | 驳回率上升 > 3% | P95 延迟 > 2x    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼ (金丝雀 5% 通过)                                               │
│  Step 4: 金丝雀 20% (生产环境, 3 天)                                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  扩大到 20% 流量, 持续监控                                      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼ (金丝雀 20% 通过)                                               │
│  Step 5: 全量发布                                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  100% 流量切换到新模型                                          │   │
│  │  旧模型保留为 "rollback" 备用 (保留 30 天)                      │   │
│  │  Model Registry 更新状态: "production"                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼ (全量后监控 7 天)                                               │
│  Step 6: 归档旧模型                                                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  确认新模型稳定运行 7 天 → 旧模型从生产环境移除                  │   │
│  │  旧模型移至冷存储归档 (用于未来回归对比)                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.3 回滚机制

```python
class ModelRollbackManager:
    """模型回滚管理器"""

    # 回滚触发条件
    ROLLBACK_TRIGGERS = {
        "approval_rate_drop": 0.05,       # 采纳率下降 5%
        "rejection_rate_rise": 0.03,      # 驳回率上升 3%
        "p95_latency_2x": True,           # P95 延迟超过旧模型 2 倍
        "format_error_spike": 0.10,       # 格式错误率超过 10%
        "manual_trigger": True,           # 人工触发
    }

    async def check_and_rollback(
        self,
        new_model: str,
        old_model: str,
        monitoring_window: timedelta = timedelta(hours=1),
    ) -> RollbackDecision:
        """检查是否需要回滚"""

        # 1. 拉取新模型的在线指标
        new_metrics = await self.get_online_metrics(
            model=new_model,
            window=monitoring_window,
        )

        # 2. 拉取旧模型的基线指标
        baseline_metrics = await self.get_baseline_metrics()

        # 3. 逐项检查
        triggers_fired = []

        if (baseline_metrics.approval_rate - new_metrics.approval_rate
                > self.ROLLBACK_TRIGGERS["approval_rate_drop"]):
            triggers_fired.append(
                f"采纳率下降: {new_metrics.approval_rate:.2%} vs "
                f"基线 {baseline_metrics.approval_rate:.2%}"
            )

        if (new_metrics.rejection_rate - baseline_metrics.rejection_rate
                > self.ROLLBACK_TRIGGERS["rejection_rate_rise"]):
            triggers_fired.append(
                f"驳回率上升: {new_metrics.rejection_rate:.2%} vs "
                f"基线 {baseline_metrics.rejection_rate:.2%}"
            )

        if (new_metrics.p95_latency_ms >
                baseline_metrics.p95_latency_ms * 2):
            triggers_fired.append(
                f"P95 延迟翻倍: {new_metrics.p95_latency_ms}ms vs "
                f"基线 {baseline_metrics.p95_latency_ms}ms"
            )

        # 4. 决策
        if triggers_fired:
            logger.warning(f"回滚触发条件满足: {triggers_fired}")

            # 自动回滚 (P0/P1 级别问题)
            if self._is_critical(triggers_fired):
                await self.execute_rollback(new_model, old_model)
                return RollbackDecision(action="auto_rollback", reasons=triggers_fired)

            # 告警通知 (P2/P3 级别问题)
            await self.send_alert(triggers_fired)
            return RollbackDecision(action="alert", reasons=triggers_fired)

        return RollbackDecision(action="continue")

    async def execute_rollback(self, new_model: str, old_model: str):
        """执行回滚"""
        # 1. 更新模型路由: 100% 流量切回旧模型
        await self.llm_adapter.update_routing({
            "default": old_model,
            "canary": None,  # 取消灰度
        })

        # 2. 标记新模型为 "rolled_back"
        await self.model_registry.update_status(new_model, "rolled_back")

        # 3. 发送回滚完成通知
        await self.send_notification(
            level="P1",
            title=f"模型回滚完成: {new_model} → {old_model}",
            detail=f"回滚原因: {self._rollback_reasons}",
        )
```

---

## 七、持续优化闭环

### 7.1 微调驱动的持续学习飞轮

```
┌─────────────────────────────────────────────────────────────────────┐
│                    微调持续优化飞轮                                    │
│                                                                      │
│                         ┌──────────────┐                             │
│                         │   线上运行    │                             │
│                         │  (生产环境)   │                             │
│                         └──────┬───────┘                             │
│                                │                                     │
│              ┌─────────────────┼─────────────────┐                   │
│              │                 │                 │                   │
│              ▼                 ▼                 ▼                   │
│  ┌───────────────────┐ ┌──────────────┐ ┌──────────────┐           │
│  │  LangFuse 追踪     │ │ 碳基守门记录  │ │ 用户反馈      │           │
│  │  (LLM 调用轨迹)    │ │ (approved/   │ │ (案件/任务    │           │
│  │  (Tool 调用序列)   │ │  rejected/   │ │  结果评价)    │           │
│  │  (Token 消耗)     │ │  modified)   │ │              │           │
│  └────────┬──────────┘ └──────┬───────┘ └──────┬───────┘           │
│           │                   │                 │                    │
│           └───────────────────┼─────────────────┘                    │
│                               │                                      │
│                               ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    数据采集与清洗                               │    │
│  │  ├── L1 指令遵循: 自动从通过的任务采集 instruction-output 对    │    │
│  │  ├── L3 工具使用: 从成功轨迹中提取工具调用链                    │    │
│  │  ├── L4 偏好数据: 从守门对比中提取 chosen/rejected 对           │    │
│  │  └── 质量过滤 + PII 脱敏 + 去重                                │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                      │
│                               ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    数据积累到阈值                               │    │
│  │  L1: 每次 > 2,000 条新数据 → 触发增量微调                       │    │
│  │  L3: 每次 > 5,000 条新工具序列 → 触发增量微调                   │    │
│  │  L4: 每次 > 3,000 条新偏好对 → 触发偏好优化                     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                      │
│                               ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    训练 + 评估 + 灰度                          │    │
│  │  → Quality Gates → Staging验证 → 金丝雀5%→20%→100%          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                      │
│                               └────────→ 回到 "线上运行"             │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 训练频率建议

| 微调层级 | 触发频率 | 触发条件 | 训练成本 (单次) |
|----------|---------|---------|---------------|
| **L1 指令遵循** | 每月 | 新增 > 2,000 条或格式遵循率 < 90% | ¥200-500 |
| **L3 工具使用** | 每季度 | 新增 > 5,000 条或工具准确率 < 85% | ¥500-1,000 |
| **L2 领域知识** | 每半年 | 新增大量制度法规 (如等保升级/新法规) | ¥2,000-5,000 |
| **L4 偏好对齐** | 每季度 | 新增 > 3,000 条偏好对 | ¥500-1,000 |

---

## 八、微调 vs RAG vs Prompt 工程决策框架

### 8.1 何时选择微调

```
┌─────────────────────────────────────────────────────────────────────┐
│               微调 vs RAG vs Prompt 工程 决策框架                      │
│                                                                      │
│  问题: 我的 AI 输出不够好，应该用哪种方式改进？                          │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 症状 1: 输出格式经常不符合期望的 JSON Schema                     │   │
│  │   ↓                                                            │   │
│  │   判断: 已尝试 Prompt 中加示例 → 边际改善小                      │   │
│  │   ↓                                                            │   │
│  │   ✅ 推荐: L1 指令遵循微调                                      │   │
│  │   理由: 格式遵循是"怎么输出"的问题，微调最直接                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 症状 2: 工具选择经常出错 (如该查 KB 却直接推理)                   │   │
│  │   ↓                                                            │   │
│  │   判断: 已优化 Tool Description → 仍频繁选错                     │   │
│  │   ↓                                                            │   │
│  │   ✅ 推荐: L3 工具使用微调                                      │   │
│  │   理由: 工具选择的模式可以训练进模型参数                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 症状 3: 对新发布的法规/制度不了解                                │   │
│  │   ↓                                                            │   │
│  │   判断: 这是"新知识"问题                                         │   │
│  │   ↓                                                            │   │
│  │   ❌ 不推荐微调                                                   │   │
│  │   ✅ 推荐: RAG — 将新法规加入知识库索引                          │   │
│  │   理由: 微调无法让模型实时掌握新知识，RAG 是最佳选择              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 症状 4: AI 推理逻辑/风格不符合风控专家预期                        │   │
│  │   ↓                                                            │   │
│  │   判断: 收集到足够多的碳基守门偏好数据                            │   │
│  │   ↓                                                            │   │
│  │   ✅ 推荐: L4 偏好对齐微调 (DPO)                                │   │
│  │   理由: 偏好对齐需要大量对比数据，微调是唯一有效手段              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 症状 5: Prompt 越来越长 (> 15K tokens) 但效果提升不大了          │   │
│  │   ↓                                                            │   │
│  │   判断: 提示词工程的边际效益递减                                  │   │
│  │   ↓                                                            │   │
│  │   ✅ 推荐: L1 + L2 微调 → 缩减 Prompt 长度 → 降低推理成本       │   │
│  │   理由: 将高频使用的知识和指令训练进模型，缩短 Prompt            │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 成本效益分析

| 方案 | 初始投入 | 月度成本 | 响应延迟 | 质量上限 | 灵活性 |
|------|---------|---------|---------|---------|--------|
| **纯 Prompt 工程** | ¥0 | ¥0 | 无增加 | 中 | 极高 |
| **RAG 增强** | 知识库构建 | ¥500-2,000 (Embedding API) | +200ms (检索) | 高 | 高 |
| **L1 指令微调** | ¥2,000-5,000 (训练) | ¥0 | 无增加 | 高 | 中 |
| **L3 工具微调** | ¥3,000-8,000 (训练) | ¥0 | 无增加 | 高 | 中 |
| **L2 领域微调** | ¥10,000-30,000 (训练) | ¥0 | 无增加 | 很高 | 低 |
| **L4 偏好微调** | ¥5,000-10,000 (训练) | ¥0 | 无增加 | 很高 | 中 |

> 结论：微调是一次性投入，但可以显著缩短 Prompt（降低月度 Token 消耗），长期看净成本更低。

---

## 九、实施路线图

### 9.1 分阶段实施计划

```
Phase 1: 基础设施搭建 (Month 1-2)
├── 搭建训练数据采集管道 (TrainingDataCollector)
├── 搭建 Model Registry (基于 MinIO)
├── 部署模型路由能力到 LLM Adapter
├── 基础数据积累: 开始采集 LangFuse 轨迹 + 守门记录
└── 目标: 积累 ≥ 5,000 条指令遵循数据

Phase 2: L1 指令遵循微调 (Month 3-4)
├── 数据: 自动采集 10,000+ 条 instruction-output 对
├── 训练: LoRA/QLoRA, 1-2× A100, 2-4h
├── 评估: Golden Test Set 全量回归
├── 部署: 金丝雀 5%→20%→100%
└── 目标: JSON Schema 遵循率 70% → 95%+

Phase 3: L3 工具使用微调 (Month 5-8)
├── 数据: 积累 3 个月的工具调用轨迹 (≥ 15,000 条)
├── 训练: LoRA rank=128, 2-4× A100, 4-8h
├── 评估: 工具选择准确率基线提升
├── 部署: 叠加到 L1 模型上 (L1 Adapter + L3 Adapter)
└── 目标: 工具选择准确率 75% → 90%+

Phase 4: L2 领域知识微调 (Month 9-14)
├── 数据: 知识库 QA 对 + 历史案件推理链 (≥ 30,000 条)
├── 人工标注: 2 位风控专家 × 每周 4h × 6 个月
├── 训练: QLoRA + CPT, 4-8× A100, 24-72h
├── 评估: 法规引用准确率 / 专业建议合理性
└── 目标: 法规引用准确率 80% → 93%+

Phase 5: L4 偏好对齐微调 (Month 15+)
├── 数据: 积累 12+ 个月的守门对比数据 (≥ 10,000 对)
├── 训练: DPO LoRA, 2-4× A100, 4-6h
├── 评估: 碳基采纳率持续提升
└── 目标: 碳基采纳率 70% → 85%+
```

### 9.2 投入估算

| 阶段 | 时间 | 人力 | GPU 资源 | 一次性成本 |
|------|------|------|---------|----------|
| Phase 1 | 2 个月 | 1 AI 工程师 | CPU 服务器 (已有) | ¥0 |
| Phase 2 | 2 个月 | 1 AI 工程师 | 云 GPU 租赁 (A100 × 2, 10h) | ¥500-1,000 |
| Phase 3 | 3 个月 | 1 AI 工程师 | 云 GPU 租赁 (A100 × 4, 20h) | ¥1,000-3,000 |
| Phase 4 | 6 个月 | 1 AI 工程师 + 2 风控专家 (part-time) | 云 GPU 租赁或自建 (A100 × 8, 100h) | ¥10,000-50,000 |
| Phase 5 | 持续 | 1 AI 工程师 | 云 GPU 租赁 (A100 × 4, 10h/次) | ¥1,000-3,000/次 |

---

## 附录 A：微调环境技术选型

| 组件 | 选型 | 用途 |
|------|------|------|
| **训练框架** | LLaMA-Factory | 统一微调入口，支持 LoRA/QLoRA/Full FT/DPO |
| **模型下载** | HuggingFace Hub (mirror) | 获取基础模型权重 |
| **数据格式** | ChatML (sharegpt) | 标准对话格式 |
| **分布式训练** | DeepSpeed ZeRO-3 | 大模型分布式训练 |
| **实验追踪** | MLflow / W&B | 训练超参数和指标记录 |
| **模型服务** | vLLM | 微调后的模型推理部署 |
| **GPU 调度** | K8s + GPU Operator | GPU 资源管理和调度 |

## 附录 B：与功能性架构的关系

本文档描述的微调体系是 [功能性架构文档](functional-architecture.md) 中以下功能域的增强：

| 功能域 | 微调增强 |
|--------|---------|
| 意图识别 | L3 工具微调可提升 Tool Calling 阶段的工具选择准确率 |
| 记忆系统 | L2 领域微调可提升 L4 组织记忆的检索利用率 |
| RAG 召回 | 微调后模型更能理解检索到的上下文，减少"读了但不用" |
| 提示词管理 | 微调后 Prompt 可以缩短（去掉 Few-shot 示例和冗余约束） |
| 上下文工程 | 微调后上下文窗口压力降低，裁剪需求减少 |
| LLM 网关 | 模型路由新增微调模型，与基础模型并行运行 |
| 性能评估 | 评估体系新增微调前后的对比维度 |

## 附录 C：文档修订历史

| 版本 | 日期 | 修订说明 |
|------|------|----------|
| v1.0 | 2026-06-10 | 初始版本：覆盖 4 层微调目标定义、训练数据管道、训练基础设施、评估框架、金丝雀部署、回滚策略、持续优化飞轮、决策框架、实施路线图 |
