# 风险监控模块 Multi-Agent 架构分析

> **所属系统**：赫尔墨斯（Hermes）风险控制 AI 智能体
> **模块编号**：02
> **模块名称**：风险监控（主动风险扫描）
> **依赖文档**：[Agent 架构总则](00-agent-architecture.md) | [风险监控 Agent 详细设计](02-risk-monitoring-agents.md)
> **文档版本**：v1.0
> **最后更新**：2026-06-20

---

## 一、问题提出

风险监控模块在 multi-agent 架构上有其独特之处：

- 当前 6 个 Graph 节点但只有 **2 个 Agent**（risk-rule-agent + risk-analysis-agent）
- 其他模块如廉洁监察是 6 节点 **6 Agent**，粒度不一致
- 风险监控是唯一 7×24 无人值守运行、处理 TB 级数据、生成并执行 SQL 的模块

本文档分析风险监控最适合的 multi-agent 架构模式，并给出整体架构和 Agent 粒度两个层面的建议。

---

## 二、整体架构层面：三种方案对比

### 2.1 方案 A：确定性 Pipeline + Stage Agent（当前方案）

```
Module Graph (LangGraph StateGraph, 非 LLM)
  → Stage 1: risk-rule-agent (规则生成)
  → Stage 2: risk-analysis-agent 子阶段1 (SQL执行+AI初核)
  → Stage 3: risk-analysis-agent 子阶段2 (主体合并)
  → Stage 4: risk-analysis-agent 子阶段3 (风险定性)
  → Stage 5: 结果推送 (系统编排)
  → Stage 6: 处置回流 (系统编排)
```

**优点**：
- 流程完全可预测、可审计 — 每步都有 checkpoint
- LLM 只在授权阶段内工作，不能跳阶段
- HITL 守门精确嵌入每个阶段前后
- 批量分区、超时、重试都由确定性逻辑控制

**缺点**：
- 遇到未预见的数据异常（如 Schema 变更、新业务模式）时缺乏自适应能力
- 当 `uncertain` 比例 >30% 时只能标记"降级"，无法自主调整策略

### 2.2 方案 B：Supervisor 路由 + Worker 协作（如 CrewAI/AutoGen 风格）

```
Supervisor Agent (LLM)
  ├── 动态决策：当前需要规则师？还是分析师？
  ├── Worker A: 规则生成专家
  ├── Worker B: SQL 执行专家
  ├── Worker C: 异常分析专家
  └── Worker D: 风险定级专家
```

**优点**：
- 灵活应对非标场景 — Supervisor 可以动态决定"先查外部数据再执行SQL"
- 处理异常时更智能

**缺点（致命）**：
- Supervisor 的 LLM 决策是**单点 AI 故障源** — 一旦错误跳过某个阶段，7×24 模式下没有人类及时发现
- 不可审计 — "为什么这次扫描跳过了主体合并？"无法追溯确定性原因
- Token 成本高 — 每次路由决策都消耗 LLM 调用
- **违反架构总则**：文档明确禁止"自主决策型主 Agent"

### 2.3 方案 C：确定性 Pipeline + 智能异常处理层（推荐）

```
确定性主干 (LangGraph StateGraph, 非 LLM)
  Stage 1 → Stage 2 → Stage 3 → Stage 4 → Stage 5 → Stage 6
                │                    │
                ▼                    ▼
        异常检测哨兵            异常检测哨兵
        (判定: 是否需要         (判定: 是否需要
         动态调整策略)           人工升级)
                │                    │
                ▼                    ▼
        异常处理 Agent         升级决策 Agent
        (仅在此触发,            (仅在此触发,
         不可跳过主干)           不可跳过主干)
```

核心思想：**主干流程保持确定性，但在关键节点设置"异常哨兵"**。

哨兵不是路由决策者，而是**条件触发器**：
- 当 SQL 执行成功率 < 95% → 触发 `schema-adaptation-agent`（尝试推断 Schema 变更）
- 当 AI 初核 `uncertain` 比例 > 30% → 触发 `deep-analysis-agent`（获取更多上下文后重新分析）
- 当某规则连续 3 次误报率 > 50% → 触发 `rule-optimization-agent`（建议规则调整）
- 当发现新型风险模式（超出已有规则覆盖）→ 触发 `novel-risk-agent`（建议新规则）

**优点**：
- 保留了 Pipeline 的确定性和可审计性（主干不动）
- 异常处理层提供了 Pipeline 缺乏的**自适应能力**
- 异常处理 Agent 的权限受限 — 只能生成建议，不能改变流程状态
- 符合现有架构约束（"Agent 只生成建议，Graph 控制流程"）

**代价**：
- 比纯 Pipeline 多一层复杂度（哨兵规则 + 异常 Agent）
- 需要定义清晰的哨兵触发条件和超时

### 2.4 推荐结论

**推荐方案 C（确定性 Pipeline + 智能异常处理层）**。

---

## 三、方案 C 的补充论证

### 3.1 风险监控是唯一的"数据生产者"模块

在 8 个模块中，风险监控是唯一以 **Push（广播推送）** 模式运行的模块：

```
风险监控 ──Push──→ 廉洁监察
          ──Push──→ 内控评价
          ──Push──→ 商业秘密
          ──Push──→ 行为风险
          ──Push──→ 业务部门
```

其他模块（如廉洁监察）是 **Pull（案件驱动）** 模式 —— 由外部举报/审计触发，处理完一个案件就结束。

**架构含义**：风险监控的可靠性是一个**乘数效应**。如果风险监控的架构出错（漏报或误判），4+ 个下游模块会被连锁影响。确定性 Pipeline 确保每一次扫描都完整执行所有 6 个阶段，不会因为 LLM 的一次路由决策跳过关键步骤。

### 3.2 SQL 执行是独有的高风险操作

风险监控是唯一需要**生成并执行 SQL 到生产数据库**的模块。一条幻觉生成的 SQL 可能：

- 造成生产数据库性能问题（全表扫描大表）
- 返回错误数据导致误报/漏报
- 在极端情况下触及敏感数据

**架构含义**：SQL 的生成 → 校验 → 执行 → 结果过滤必须是确定性流程。不能让一个 Supervisor Agent "决定今天跳过 SQL 校验"。这也是为什么当前设计中 `risk-rule-agent` 有专门的 `sql_syntax_validate` 和 `sql_test_execute_readonly` 工具，且 SQL 必须经过人工审核才能入库。

### 3.3 7×24 无人值守的独特成本约束

风险监控是唯一设计为 **7×24 定时自动运行** 的模块（月均 30+ 次全量扫描）。其他模块由人工触发，频率低得多。

**架构含义**：任何多余的 LLM 调用都会被放大 30 倍。方案 B（Supervisor 路由）每次扫描都需要 Supervisor 做路由决策，假设每次 2K tokens × 30 次 = 60K tokens/月纯浪费在"决定调用谁"。方案 A/C 的 LLM 调用只在必要的推理阶段发生。

### 3.4 闭环反馈是架构层面的第二数据流

风险监控是唯一有**处置回流闭环**（Stage 6.6）的模块：

```
扫描 → 推送 → 下游处置 → 结果回流 → 误报分析 → 规则优化 → 下次扫描
```

这不是简单的线性流水线，而是一个**环形结构**。方案 C 的"智能异常哨兵"天然适合承载这个闭环：

- 哨兵检测到某规则误报率 > 30% → 触发 `rule-optimization-agent`
- 哨兵检测到新型风险模式 → 触发 `novel-risk-agent` 建议新规则
- 哨兵检测到 Schema 变更导致 SQL 失败 → 触发 `schema-adaptation-agent`

### 3.5 数据分区与并行是系统工程问题，不是 LLM 问题

风险监控处理 TB 级数据，需要按事业部/规则/时间窗口/批次四维分区并行执行。这是确定性的系统工程 —— 分区策略、超时控制、Celery Worker 池扩缩 —— LLM 无法也不应该参与这种决策。Supervisor Agent 不会比 `asyncio.gather` + Celery 任务队列更擅长并行调度。

---

## 四、Agent 粒度层面：2 Agent vs 4 Agent

### 4.1 现状对比

| 维度 | 廉洁监察 | 风险监控 |
|------|---------|---------|
| Graph 节点数 | 6 | 6 |
| Agent 数量 | 6（每节点 1 Agent） | 2（risk-rule-agent + risk-analysis-agent） |
| Agent 粒度 | 1 Agent : 1 Stage | 1 Agent : 1 Stage（规则）+ 1 Agent : 3 Sub-Stages（分析） |
| 条件路由 | ✅ 有（立案/不立案、追责/不追责） | ❌ 无（全线性） |
| 上下文传递 | 每个阶段输出结构不同 | 核心上下文贯穿始终 |

### 4.2 为什么廉洁监察需要 6 个独立 Agent

廉洁监察的每个阶段需要**完全不同的专业知识**：

| Agent | 核心能力 | 推理性质 |
|-------|---------|---------|
| IntakeAgent | 法律三要素判断，分流决策 | 法律定性 |
| InvestigationAgent | 调查策略规划，访谈设计 | 策略规划 |
| AnalysisAgent | 法务会计分析，资金追踪 | 财务分析 |
| DispositionAgent | 法律条款匹配，责任认定 | 法律判断 |
| EnforcementAgent | 处罚公告撰写，A2A 任务下发 | 执行协调 |
| PostReportAgent | 报案材料撰写，司法协助 | 文书撰写 |

6 个 Agent 处理 6 种不同性质的推理任务，共享上下文极少。

### 4.3 为什么风险监控当前用 2 个 Agent

风险监控的阶段 2-4（扫描→过滤→合并→定性）共享同一个核心能力：**数据分析**。无论初核异常、合并主体、判定风险等级，本质上都是"看懂数据 + 做出判断"。

三个阶段的数据流是渐进增强的：
```
anomaly_records (原始异常行)
  → merged_entities (合并后的主体)
    → risk_classifications (定性后的风险)
```

### 4.4 建议：拆分为 4 个 Agent

虽然 2 Agent 设计在概念上可行，但建议将 `risk-analysis-agent` 拆分为 3 个独立 Agent：

| 拆分理由 | 具体说明 |
|----------|---------|
| **独立可测试性** | 3 个子阶段各有 Golden Test Set，独立 Agent 可单独回归测试 |
| **独立降级策略** | SQL 超时需要重试/跳过，风险定性失败需要标记人工接管 — 完全不同 |
| **LLM 配置独立** | temperature（0.2/0.2/0.3）、max_tokens（8K/4K/4K）各不相同 |
| **独立 SLA 目标** | P95：子阶段1 < 120s, 子阶段2 < 30s, 子阶段3 < 20s |
| **对齐 Graph 节点** | Graph 已有 6 个独立节点，Agent 也应对齐，消除不一致 |
| **后期复用可能** | `risk-merge-agent`（主体合并）可被廉洁监察模块复用 |

#### 建议的 4 Agent 设计

```
risk-rule-agent        → [6.1] 规则生成 + SQL校验
risk-scan-agent        → [6.2] SQL执行 + AI初核异常
risk-merge-agent       → [6.3] 主体识别与合并去重
risk-classify-agent    → [6.4] 风险类型/等级/处置建议判定
[系统编排]              → [6.5] 结果推送
[系统编排]              → [6.6] 处置回流与规则迭代
```

Agent 间的上下文传递仍由 Graph State 管理（不改动 Graph 结构），每个 Agent 只负责单一阶段的推理。保持"Agent 不控制流程"的架构约束。

---

## 五、异常哨兵层的具体设计

哨兵不是路由决策者，而是**条件触发器**。它们监控 Pipeline 各阶段的输出质量，在满足触发条件时激活对应的处理 Agent：

| 哨兵位置 | 触发条件 | 激活的 Agent | 输出 |
|----------|---------|-------------|------|
| risk_scan 之后 | SQL 执行成功率 < 95% | `schema-adaptation-agent` | Schema 变更推断 + SQL 修正建议 → 人工审核 |
| anomaly_filter 之后 | `uncertain` 比例 > 30% | `deep-analysis-agent` | 获取更多上下文后重新分析 → 更新 anomaly_records |
| risk_classify 之后 | 某规则连续 3 次误报率 > 50% | `rule-optimization-agent` | 规则调整建议（SQL/阈值/范围）→ 人工审核 |
| 全流程结束后 | 发现超出已有规则覆盖的风险模式 | `novel-risk-agent` | 新规则建议 → 进入 risk-rule-agent 流程 |
| result_push 之后 | 下游模块反馈"无需处置"比例 > 50% | `rule-optimization-agent` | 规则有效性重新评估 |

哨兵的实现方式：Graph 节点的结构化输出中增加哨兵判定字段，Graph 根据这些字段决定是否 fork 到异常处理子图。

**哨兵的设计约束**：
- 哨兵只生成建议，不直接修改规则或跳过阶段
- 哨兵触发的处理 Agent 输出必须走 HITL 人工守门
- 哨兵触发频率有上限（防止异常场景下无限循环）
- 哨兵判定逻辑是确定性代码，不是 LLM 推理

---

## 六、与架构总则的一致性

本建议完全符合 `00-agent-architecture.md` 的六条设计约束：

| 约束 | 合规说明 |
|------|---------|
| 不得新增万能主 Agent | 方案 C 的哨兵是条件触发器，不是 Agent，不控制流程 |
| 不得让 Agent 拥有全模块工具权限 | 拆分后的每个 Agent 只拿当前阶段必要工具 |
| 不得让 Agent 输出直接成为业务终态 | 哨兵触发的异常处理 Agent 输出仍走 HITL 守门 |
| 不得由 Worker 推进业务阶段 | 哨兵 fork 到异常子图，完成后回到主干，流程仍由 Graph 控制 |
| 不得在 Prompt 中隐藏审批规则 | 哨兵触发条件是显式确定性代码 |
| 不得编造知识依据 | schema-adaptation-agent 需要 KB 检索支持，检索不足输出 knowledge_insufficient |

---

## 七、关键文件

| 文件 | 角色 |
|------|------|
| `hermes/workflows/risk_monitoring/graph.py` | 6 节点 Graph 定义，需增加哨兵条件边 |
| `hermes/agents/risk_monitoring/risk_analysis_agent.py` | 需拆分为 risk-scan-agent + risk-merge-agent + risk-classify-agent |
| `hermes/agents/risk_monitoring/risk_rule_agent.py` | 保持不变 |
| `hermes/schemas/agents/risk_monitoring.py` | 需为新 Agent 定义独立输入/输出 Schema |
| `hermes/agents/profiles.py` | 需更新 `RISK_MONITORING_PROFILE` 的 Agent 清单 |
| `doc/agents/02-risk-monitoring-agents.md` | 需更新 Agent 清单和详细设计 |
| `doc/agents/00-agent-architecture.md` | 架构总则（参考约束，不需修改） |

---

## 附录：文档修订历史

| 版本 | 日期 | 修订说明 |
|------|------|----------|
| v1.0 | 2026-06-20 | 初始版本：全面分析风险监控模块的 multi-agent 架构适配方案 |
