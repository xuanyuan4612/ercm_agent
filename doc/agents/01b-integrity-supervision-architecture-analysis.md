# 廉洁监察模块 Multi-Agent 架构分析

> **所属系统**：赫尔墨斯（Hermes）风险控制 AI 智能体
> **模块编号**：01
> **模块名称**：廉洁监察（反舞弊调查）
> **依赖文档**：[Agent 架构总则](00-agent-architecture.md) | [廉洁监察 Agent 详细设计](01-integrity-supervision-agents.md) | [风险监控架构分析](02b-risk-monitoring-architecture-analysis.md)
> **文档版本**：v1.1
> **最后更新**：2026-06-28

> **状态说明**：本文档保留为架构分析与方案论证材料。其生产落地结论（Pipeline + HITL + 证据驱动回退循环、并行辅助 Agent、复杂度评估器、非 Supervisor 约束）已合入 [01-integrity-supervision-agents.md](01-integrity-supervision-agents.md)，后续实施以 01 主设计文档为准。

---

## 一、问题提出

廉洁监察模块与风险监控模块在本质上有根本性差异：

| 维度 | 廉洁监察 | 风险监控 |
|------|---------|---------|
| 驱动方式 | 案件驱动（被动响应举报） | 定时调度（主动扫描，7×24） |
| 处理对象 | 单个高价值案件 | 海量业务数据 |
| 决策性质 | 法律定性 + 人员处罚 | 异常识别 + 风险分级 |
| 错误代价 | 极高 — 冤枉好人或放过舞弊 | 高 — 误报浪费人力，漏报风险敞口 |
| 人工参与 | 每阶段必须（6 道 HITL 守门） | 仅高风险时需人工复核 |
| 外部通信 | 双向 A2A（龟宝/西塞罗/波特） | 单向推送 |
| 输入模态 | 多模态（文本/音频/图片/文档） | 纯结构化 SQL 数据 |
| 运行周期 | 数天到数周 | 数分钟到数小时 |
| Agent 数量 | 6（每阶段 1 个） | 4 + 4 哨兵 |

本文档分析廉洁监察最适合的 multi-agent 架构模式。

---

## 二、四种候选架构方案

### 方案 A：确定性 Pipeline + HITL 守门（当前方案）

```
LangGraph StateGraph (确定性流程控制)
  intake → investigation → analysis → disposition → enforcement → post_report
     │                                  │
     ├── END (不立案/转交)              ├── END (不追责)
     │                                  ├── 刑事 → 报案书
     │                                  ├── 民事 → A2A 西塞罗
     │                                  └── 内部 → enforcement
     │
     └── 每阶段 HITL 守门 (6 道门)
```

**优点**：
- 完全可审计 — 每步决策可追溯至具体人和具体原因
- 人工守门确保法律/人事决策不会由 AI 自动做出
- 条件路由是确定性代码，不是 LLM 决策
- 每阶段独立，Agent 可独立测试、独立降级

**缺点**：
- 缺乏证据不足时的自动回退机制（分析阶段发现证据不足，不能自动触发补充调查）
- 6 道守门可能成为瓶颈（简单案件也需全流程）
- 不支持并行调查（多嫌疑人/多指控无法并行处理）

---

### 方案 B：Supervisor 路由 + 专家 Worker（CrewAI/AutoGen 风格）

```
Supervisor Agent (LLM)
  ├── 动态决策：当前需要取证？还是法律分析？
  ├── Worker: 取证专家
  ├── Worker: 法律分析专家
  ├── Worker: 访谈专家
  └── Worker: 文书撰写专家
```

**优点**：
- 灵活应对复杂案件的动态需求
- 可并行调度多个 Worker

**缺点（致命）**：
- **法律风险不可接受**：Supervisor 的 LLM 决策决定"是否追责"→ 无人类可追溯的决策链路
- **违反架构总则**：明确禁止"自主决策型主 Agent"
- **A2A 通信冲突**：Supervisor 和外部 Agent（龟宝/西塞罗/波特）之间的通信协议不一致
- 在法律/人事决策场景中，AI 路由决策无法通过合规审计

---

### 方案 C：Pipeline + 证据驱动回退循环（推荐）

```
主干 Pipeline (确定性 LangGraph)
  intake ──→ investigation ──→ analysis ──→ disposition ──→ enforcement ──→ post_report
    │            ↑                 │                                     │
    │            │                 │ 证据不足? ───→ 回退到 investigation   │
    │            │                 │                                     │
    ├── END      │                 ├── END (不追责)                       │
    │            │                 ├── 刑事 → 报案书                      │
    │            │                 ├── 民事 → A2A 西塞罗                  │
    │            │                 └── 内部 → enforcement                  │
    │            │                                                        │
    │            └── 补充调查 (evidence_supplement_needed)                 │
    │                                                                     │
    └── 案件复杂度路由 (简单案件 → 快速通道，复杂案件 → 完整流程)           │

并行辅助层 (不控制流程，只提供建议)
  ┌──────────────────────────────────────────────┐
  │ 调查策略顾问 (Investigation Strategy Advisor) │
  │   - 并行运行，分析证据链完整性                  │
  │   - 建议替代调查方向                            │
  │   - 输出：调查建议（走 HITL 审核后才生效）       │
  └──────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────┐
  │ 案件复杂度评估器 (Case Complexity Assessor)    │
  │   - 在 intake 阶段并行运行                     │
  │   - 评估：涉案金额/涉及人数/跨部门/跨境         │
  │   - 输出：complexity_level → 路由决策           │
  └──────────────────────────────────────────────┘
```

核心思想：**主干保持确定性 Pipeline + HITL，但增加两个受控的灵活度提升机制**：

1. **证据驱动回退循环**：当 AnalysisAgent 判定证据不足时，自动触发补充调查（回到 investigation），而非坐等人工发现
2. **并行辅助 Agent**：调查策略顾问和案件复杂度评估器并行运行，输出建议走 HITL，不控制流程

**优点**：
- 保留 Pipeline 的确定性和可审计性
- 证据回退循环解决了"证据不足无法自动补救"的核心痛点
- 案件复杂度路由避免简单案件走全流程
- 辅助 Agent 只提建议，不改流程 — 符合架构约束

**代价**：
- 回退循环可能造成无限循环（需要最大回退次数限制）
- 复杂度评估器需要准确的分类标准

---

### 方案 D：混合架构 — 简单案件快速通道 + 复杂案件全流程

```
intake (案件受理)
    │
    ├── 复杂度评估 (CaseComplexityAssessor)
    │       │
    │       ├── low → 快速通道: intake → analysis → disposition → END
    │       │                    (跳过 investigation, 仅做书面审核)
    │       │
    │       └── medium/high → 完整流程: intake → investigation → analysis
    │                              → disposition → enforcement → post_report
    │
    └── 每阶段 HITL 守门 (复杂度越高，守门越严格)
```

**优点**：
- 显著减少简单案件的流转时间
- 资源聚焦在复杂案件上

**代价**：
- 复杂度分类器的准确性直接影响案件处理质量
- 增加了路由复杂度

---

## 三、推荐方案：方案 C（Pipeline + 证据驱动回退循环）

### 3.1 为什么不是方案 A（纯 Pipeline）

方案 A 在正常案件流程中运行良好，但存在三个核心缺陷：

**缺陷 1：证据不足无自动补救**
```
当前: analysis → 证据不足 → disposition → 人工发现证据不足 → 手动重启调查
         ↑                                                      ↓
         └──────────── 可能需要数天 ─────────────────────────────┘
改进: analysis → 证据不足 → evidence_supplement_gate → 自动回退到 investigation
```
在"证据不足→坐等人工发现→手动重启"的当前流程中，案件可能停滞数天。而证据驱动回退可以实现分钟级的自动补救。

**缺陷 2：简单案件也走全流程**
轻微违规（如小额费用报销异常）和重大舞弊（如千万级采购围标）走同样的 6 阶段流程。简单案件需要快速通道。

**缺陷 3：调查策略缺乏 AI 辅助优化**
当前 investigation-agent 生成方案后，如果调查过程中发现新线索，无法动态调整。调查策略顾问可以持续分析证据链完整性，提出补充建议。

### 3.2 为什么不是方案 B（Supervisor 路由）

**法律合规性是硬约束**。廉洁监察涉及：
- 人员处罚（降级/开除/移送司法）
- 供应商黑名单
- 民事/刑事追责

这些决策的每一项都必须有 **明确的人类决策链路**。Supervisor Agent 的 LLM 路由决策无法满足合规审计要求。

此外，方案 B 直接违反了 `00-agent-architecture.md` 的约束："不得新增万能主 Agent"。

### 3.3 为什么不是方案 D（混合快速通道）

方案 D 的思路正确，但可以作为方案 C 的一个**后续优化**，而非独立的架构方案。复杂度评估器可以先在 intake 阶段并行运行收集数据，等分类标准成熟后再启用路由。

### 3.4 廉洁监察 vs 风险监控的架构差异总结

两个模块虽然都用 Pipeline 架构，但增强机制完全不同：

| 维度 | 廉洁监察（方案 C） | 风险监控（方案 C） |
|------|-------------------|-------------------|
| **增强机制** | 证据驱动回退循环 | 智能异常哨兵 |
| **触发条件** | 证据充分性不足 | 执行异常（成功率低/uncertain 过多/误报率高） |
| **响应方式** | 回退到上游阶段（investigation） | 激活旁路哨兵 Agent（不改变主干方向） |
| **循环性** | 支持回退循环（有最大次数限制） | 哨兵处理后继续向前（不循环） |
| **辅助 Agent** | 调查策略顾问（并行建议） | rule-optimization-agent / novel-risk-agent |
| **复杂度评估** | 待实现 | 不需要（所有扫描同等对待） |

---

## 四、证据驱动回退循环的具体设计

### 4.1 回退触发条件

AnalysisAgent 输出中的 `evidence_sufficiency` 字段判定：

```python
class EvidenceSufficiency(StrEnum):
    SUFFICIENT = "sufficient"       # 证据充分 → 继续到 disposition
    PARTIAL = "partial"             # 部分充分 → 继续但降低置信度
    INSUFFICIENT = "insufficient"   # 证据不足 → 触发回退
```

| 触发条件 | 回退目标 | 携带信息 | 最大回退次数 |
|----------|---------|---------|-------------|
| `INSUFFICIENT` | investigation | 缺失证据清单 + 建议调查方向 | 2 |
| `PARTIAL` | 不触发回退，但标记 confidence=LOW | — | — |
| `SUFFICIENT` | 正常流转 | — | — |

### 4.2 回退循环的安全机制

```python
class EvidenceLoopGuard:
    """证据回退循环的安全守护"""
    max_loops: int = 2              # 最大回退次数
    loop_count: int = 0             # 当前回退次数
    previous_evidence_gaps: list    # 之前的证据缺口（避免重复建议）

    def can_loop_back(self) -> bool:
        return self.loop_count < self.max_loops

    def should_escalate(self) -> bool:
        """超过最大回退次数 → 升级为人工决策"""
        return self.loop_count >= self.max_loops
```

当回退次数达到上限后，不再自动回退，而是标记为 `ESCALATED_TO_HUMAN`，通知碳基手动决策：是补充调查、降低标准结案、还是关闭案件。

### 4.3 Graph 改动

在 `graph.py` 中新增：

```python
def route_after_analysis(state: IntegrityState) -> Literal[
    "disposition", "investigation", "human_escalation"
]:
    """分析阶段后的路由：正常流转 / 证据回退 / 人工升级"""
    conclusion = state.get("case_conclusion", {}) or {}
    evidence = conclusion.get("evidence_sufficiency", {})

    if evidence.get("level") == "insufficient":
        loop_count = state.get("evidence_loop_count", 0)
        if loop_count < MAX_EVIDENCE_LOOPS:
            return "investigation"  # 回退到调查
        else:
            return "human_escalation"  # 升级为人工决策

    return "disposition"  # 正常流转
```

---

## 五、调查策略顾问（Investigation Strategy Advisor）设计

### 5.1 角色定义

调查策略顾问是一个**并行辅助 Agent**，不在主干流程中，不控制流转：

| 属性 | 值 |
|------|-----|
| **Agent ID** | `investigation-advisor` |
| **运行模式** | 并行（与主干 Agent 同时运行） |
| **触发时机** | investigation 阶段后持续运行 |
| **输出** | 调查策略建议 → HITL 守门审核后才生效 |
| **权限** | 只读（可读案件上下文，不可修改状态） |

### 5.2 核心功能

```
调查策略顾问的职责：
  1. 证据链完整性分析 — 当前证据是否形成了完整闭环？
  2. 替代调查方向 — 如果当前方向进展缓慢，还有什么其他角度？
  3. 新线索关联 — 新发现的证据是否关联到其他未调查的领域？
  4. 时间线异常 — 关键事件的时间顺序是否有矛盾？
```

### 5.3 与主干的关系

```
investigation ──→ evidence_collection ──→ analysis
       │                                       │
       └──→ investigation-advisor (并行) ──────┘
                │
                └── 输出建议 → HITL 守门 → 碳基决定是否采纳
                                │
                    ┌───────────┼───────────┐
                    │ 采纳      │ 忽略      │ 修改后采纳
                    ▼           ▼           ▼
              更新调查方案   保持不变    合并到方案中
```

---

## 六、案件复杂度评估器（Case Complexity Assessor）设计

### 6.1 评估维度

```python
class CaseComplexityFactors:
    """案件复杂度评估因子"""
    financial_amount: float         # 涉案金额
    involved_persons: int           # 涉及人数
    cross_department: bool          # 是否跨部门
    cross_border: bool              # 是否跨境
    involves_senior_mgmt: bool      # 是否涉及高管
    evidence_types: list[str]       # 证据类型数（越多越复杂）
    legal_jurisdiction: list[str]   # 涉及法律领域数
    has_whistleblower: bool         # 是否有举报人
    case_age_days: int              # 案件持续时间
```

### 6.2 复杂度等级

| 等级 | 条件 | 建议流程 |
|------|------|---------|
| `low` | 单人、金额<10万、单一部门、证据类型≤2 | 快速通道（未来实现） |
| `medium` | 2-5人、金额10-100万、跨部门 | 标准流程（当前） |
| `high` | >5人、金额>100万、跨境、涉及高管 | 完整流程 + 调查顾问增强 |
| `critical` | 金额>1000万、涉及刑事、多司法管辖区 | 完整流程 + 调查顾问 + 优先处理 |

当前阶段，复杂度评估器仅做**信息收集和展示**，不改变路由。路由优化（方案 D 快速通道）留待后续迭代。

---

## 七、与架构总则的一致性检查

| 约束 | 合规说明 |
|------|---------|
| 不得新增万能主 Agent | 调查策略顾问只是并行辅助，不控制流程。复杂度评估器只做信息展示 |
| 不得让 Agent 拥有全模块工具权限 | 顾问 Agent 只有只读权限，不可修改案件状态 |
| 不得让 Agent 输出直接成为业务终态 | 顾问建议必须走 HITL 守门 |
| 不得由 Worker 推进业务阶段 | 回退循环是确定性代码 (`route_after_analysis`)，不是 LLM 决策 |
| 不得在 Prompt 中隐藏审批规则 | 回退条件和复杂度因子是显式代码 |
| 不得编造知识依据 | 顾问 Agent 的建议需引用具体证据/法规 |

---

## 八、实施优先级建议

| 优先级 | 改动 | 原因 |
|--------|------|------|
| **P0** | 证据驱动回退循环 | 解决核心痛点 — 证据不足无法自动补救 |
| **P1** | 调查策略顾问（并行辅助 Agent） | 提升调查质量，不改变主干流程，风险低 |
| **P2** | 案件复杂度评估器（仅信息展示） | 为未来快速通道路由收集数据 |
| **P3** | 简单案件快速通道 | 需要足够数据验证复杂度分类器准确性后再启用 |

---

## 九、关键文件

| 文件 | 改动内容 |
|------|---------|
| `hermes/workflows/integrity/graph.py` | 新增 `route_after_analysis` 条件路由 + 证据回退边 + 回退计数状态 |
| `hermes/agents/integrity/analysis_agent.py` | 输出中新增 `evidence_sufficiency` 结构化字段 |
| `hermes/agents/integrity/schemas.py` | 新增 `EvidenceSufficiency`、`CaseComplexityFactors` Schema |
| `hermes/agents/integrity/investigation_advisor.py` | **新建** — 调查策略顾问 Agent |
| `hermes/agents/integrity/case_complexity.py` | **新建** — 案件复杂度评估器 |
| `doc/agents/01-integrity-supervision-agents.md` | 更新 Agent 清单 + 新增顾问/评估器设计 |

---

## 附录：文档修订历史

| 版本 | 日期 | 修订说明 |
|------|------|----------|
| v1.0 | 2026-06-20 | 初始版本：全面分析廉洁监察模块的 multi-agent 架构适配方案 |
