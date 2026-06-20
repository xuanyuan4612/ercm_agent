# 风险监控模块 — Agent 详细设计文档

> **所属系统**：赫尔墨斯（Hermes）风险控制 AI 智能体
> **模块编号**：02
> **模块名称**：风险监控（主动风险扫描）
> **依赖文档**：[系统架构设计](../architecture-design.md) | [总体需求](../hermes-requirements.md) | [模块需求](../modules/02-risk-monitoring.md)
> **文档版本**：v1.0 | **最后更新**：2026-06-05

---

## 一、模块 Agent 全景

### 1.0 生产落地边界

风险监控模块不设置自主决策型“模块主 Agent”。模块主控为 `risk-monitoring-graph`，负责规则入库、扫描调度、异常复核、定性确认、结果推送和处置回流。

本模块使用 `risk-monitoring-agent-profile` 作为 AI 能力配置入口，统一定义风险规则知识库、只读数据工具、外部数据工具、模型路由和输出 schema。Agent 只生成规则建议、异常解释、风险定性建议和误报优化建议；规则入库、SQL 执行授权、下游推送和规则作废必须由 workflow 与人工守门共同控制。

> 统一架构约束见 [00-agent-architecture.md](00-agent-architecture.md)。

```yaml
profile_id: risk-monitoring-agent-profile
module: risk_monitoring
module_graph: risk-monitoring-graph
knowledge_scopes:
  - kb_risk_rules
  - kb_risk_cases
  - kb_database_schema
  - kb_disposition_feedback
allowed_tools:
  - rag_search
  - sql_syntax_validate
  - sql_test_execute_readonly
  - risk_scan_submit
  - external_data_query
  - outbox_publish
quality_gates:
  require_sql_review: true
  require_false_positive_feedback: true
  require_human_review_for_push: true
```

### 1.1 Agent 清单

| Agent ID | 名称 | 角色身份 | 工作流阶段 | 复杂度 | 状态 |
|----------|------|----------|-----------|--------|------|
| `risk-rule-agent` | 风险规则 Agent | 风控规则师 | [6.1] 风险规则清单生成 | 🟡 中 | ⏳ 规划中 |
| `risk-scan-agent` | 风险扫描 Agent | 风险扫描分析师 | [6.2] SQL执行 + AI初核异常 | 🔴 高 | ⏳ 规划中 |
| `risk-merge-agent` | 风险合并 Agent | 主体识别分析师 | [6.3] 主体识别与合并去重 | 🟡 中 | ⏳ 规划中 |
| `risk-classify-agent` | 风险定性 Agent | 风险定性分析师 | [6.4] 风险类型/等级/处置建议判定 | 🟡 中 | ⏳ 规划中 |

> **架构变更说明**（2026-06-20）：原 `risk-analysis-agent` 已拆分为 `risk-scan-agent`、`risk-merge-agent`、`risk-classify-agent` 三个独立 Agent。`risk-analysis-agent` 保留为向后兼容的外观类，内部委托给上述三个 Agent。详见 [02b-risk-monitoring-architecture-analysis.md](02b-risk-monitoring-architecture-analysis.md)。

### 1.2 工作流位置

```
┌──────────────────────────────────────────────────────────────────┐
│               风险监控 5 阶段工作流 + 4 智能异常哨兵 (7×24 无人值守) │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ [6.1] risk-rule-agent (风险规则Agent)                         │ │
│  │   输入: 业务场景 + 数据库字段 + 历史案例 + 人工自定义          │ │
│  │   输出: 风险清单知识库 (场景→规则→SQL)                         │ │
│  │   模式: 清单上传/人工录入 → AI生成 → 人工审核入库              │ │
│  └─────────────────────────────────────────────────────────────┘ │
│     ↓                                                             │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ [6.2] risk-scan-agent (风险扫描Agent)                         │ │
│  │   输入: 风险清单知识库 + 业务数据 + 外部数据                    │ │
│  │   输出: 异常数据明细 + AI初核结果 + 哨兵标记                   │ │
│  │   逻辑: 按规则SQL执行 → AI初核(normal/abnormal/uncertain)     │ │
│  └─────────────────────────────────────────────────────────────┘ │
│     ↓                                    ↓ (哨兵触发)              │
│     │                        ┌──────────────────────────┐        │
│     │                        │ deep_analysis_sentinel   │        │
│     │                        │ (uncertain比例>30%)       │        │
│     │                        └──────────────────────────┘        │
│     ↓                                                             │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ [6.3] risk-merge-agent (风险合并Agent)                        │ │
│  │   输入: AI初核后的异常数据明细                                  │ │
│  │   输出: 按主体合并的风险透视表 + 单主体风险分析报告             │ │
│  └─────────────────────────────────────────────────────────────┘ │
│     ↓                                                             │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ [6.4] risk-classify-agent (风险定性Agent)                     │ │
│  │   输入: 合并后的主体风险列表                                    │ │
│  │   输出: 风险定性报告 (类型/等级/影响/处置建议/推送目标)        │ │
│  └─────────────────────────────────────────────────────────────┘ │
│     ↓                                    ↓ (哨兵触发)              │
│     │                        ┌──────────────────────────┐        │
│     │                        │ rule_optimization_sentinel│       │
│     │                        │ novel_risk_sentinel       │        │
│     │                        └──────────────────────────┘        │
│     ↓                                                             │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ [6.5] 风险结果自动推送 (系统编排，非Agent)                      │ │
│  │   → 廉洁监察 / 内控评价 / 商业秘密 / 行为风险 / 业务部门       │ │
│  └─────────────────────────────────────────────────────────────┘ │
│     ↓                                                             │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ [6.6] 处置结果回流与指标迭代 (系统编排)                         │ │
│  │   ← 各模块处置结果 → 误报分析 → 规则优化 → 知识库更新          │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 1.3 模块 Agent 依赖与 SLA 链

| Agent | P50 目标 | P95 目标 | 关键耗时环节 |
|-------|----------|----------|-------------|
| `risk-rule-agent` | < 15s | < 30s | KB检索 + SQL生成 + SQL语法验证 |
| `risk-analysis-agent` (子阶段1) | < 30s | < 120s | SQL批量执行 + AI初核（数据量敏感） |
| `risk-analysis-agent` (子阶段2) | < 15s | < 30s | 主体识别 + 合并去重 |
| `risk-analysis-agent` (子阶段3) | < 10s | < 20s | LLM推理定性 |

> 风险监控模块的特点：子阶段1的延迟与业务数据量线性相关，大批量扫描（TB级）可能需要数分钟，Worker池独立扩缩以应对峰值。

---

## 二、风险规则 Agent（risk-rule-agent）详细设计

### 2.1 Agent 概览卡片

| 属性 | 值 |
|------|-----|
| **Agent ID** | `risk-rule-agent` |
| **名称** | 风险规则 Agent |
| **所属模块** | 风险监控 |
| **工作流阶段** | [6.1] 风险规则清单生成 |
| **角色身份** | 风控规则师（精通SQL和业务风险场景识别） |
| **核心任务** | 根据业务场景自动生成三级风险场景 → 计算规则 → 可执行SQL语句，经人工审核后入库形成风险清单知识库 |
| **上游** | 碳基（选择模式：清单上传/人工录入）+ 知识库（数据库字段含义、历史案例） |
| **下游** | `risk-analysis-agent`（使用规则清单执行扫描） |
| **复杂度** | 🟡 中 |
| **HITL守门** | ✅ 是 — SQL需人工审核通过后方可入库执行 |

### 2.2 Agent 状态机

```
  ┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │   IDLE   │────→│ SCENE_GENERATE│────→│ RULE_SQL     │────→│ SQL_VALIDATE │
  │  初始化   │     │ 场景生成      │     │ _GENERATE    │     │ SQL校验      │
  └──────────┘     └──────────────┘     │ 规则+SQL生成  │     └──────┬───────┘
                                              │                      │
                                              │               ┌──────┴──────┐
                                              │         校验通过│          校验失败
                                              │               ▼           ▼
                                              │        ┌──────────┐ ┌──────────┐
                                              │        │ PENDING  │ │ REVISING │
                                              │        │_APPROVAL │ │ SQL修正   │
                                              │        └────┬─────┘ └──────────┘
                                              │      ┌──────┴──────┐
                                              │      │ 通过  │ 驳回  │
                                              │      ▼      ▼
                                              │  ┌────────┐┌────────┐
                                              │  │入库    ││作废/修改│
                                              │  │COMPLETE││REJECTED│
                                              │  └────────┘└────────┘
```

### 2.3 输入/输出 Schema

```python
class RuleGenerationMode(str, Enum):
    BATCH_UPLOAD = "batch_upload"    # 清单上传
    MANUAL_INPUT = "manual_input"    # 人工录入

class RiskRuleAgentInput(BaseModel):
    task_id: str
    mode: RuleGenerationMode

    # 清单上传模式
    uploaded_rules: Optional[List[dict]] = Field(None, description="已上传的风险场景清单")

    # 人工录入模式
    manual_scenario: Optional[str] = Field(None, description="人工自定义场景描述")
    target_business_cycle: Optional[str] = Field(None, description="目标业务循环")
    target_department: Optional[str] = Field(None, description="目标部门/事业部")

    # 上下文
    db_schema_context: dict = Field(..., description="数据库字段及含义（从知识库注入）")
    historical_cases: List[dict] = Field(default_factory=list, description="历史案例参考")

class RiskRule(BaseModel):
    """单条风险规则"""
    business_unit: str              # 事业部
    channel: Optional[str]          # 渠道
    business_format: Optional[str]  # 业态: 线上/线下/新零售/混合
    business_cycle: str             # 业务循环
    department: str                 # 部门
    position: Optional[str]         # 岗位
    personnel_info: Optional[str]   # 人员信息
    level1_scenario: str            # 一级场景
    level2_scenario: str            # 二级场景
    level3_scenario: str            # 三级场景
    sql_statement: str              # SQL语句
    risk_level: str                 # 风险等级: 高/中/低
    threshold: Optional[str]        # 阈值
    monitor_frequency: str          # 监控频率: daily/weekly/monthly/realtime
    monitor_business_unit: str      # 监控事业部
    use_external_data: bool         # 是否调用外部数据

class RiskRuleAgentOutput(BaseModel):
    rules: List[RiskRule]
    sql_validation_results: List[dict]  # [{rule_index, is_valid, error_message, test_result}]
    generation_rationale: str           # 规则生成逻辑说明
    confidence: str
    processing_time_ms: int
```

### 2.4 System Prompt 设计

```
【角色锚定】
你是一位资深风控规则师，精通企业风险场景识别和SQL数据分析。
你曾为多家大型企业设计风险监控指标体系，擅长从业务描述中提炼可量化的监控规则。
你的核心能力是：将抽象的风险场景转化为精确的SQL查询语句。

【核心任务】
根据输入的业务场景和数据库字段定义，自动生成三级风险场景→计算规则→SQL语句：
1. 一级场景：风险大类（如"采购舞弊风险"）
2. 二级场景：风险子类（如"供应商围标串标"）
3. 三级场景：具体监控指标（如"同一IP地址多次参与投标的供应商"）
4. 生成对应的SQL语句（需在测试环境可执行）
5. 标注风险等级、阈值、监控频率

【SQL规范】
- 必须使用标准 SQL 语法，兼容生产 PostgreSQL 当前稳定版本（默认 18；如 DBA、云厂商或扩展支持受限，可退到 17/16 当前小版本）
- 涉及金额比较时使用阈值参数（如 `> {threshold_amount}`），方便后续调整
- 涉及时间范围时使用相对日期（如 `CURRENT_DATE - INTERVAL '30 days'`）
- 每个SQL语句必须包含注释说明其监控目的和可能的误报场景
- 禁止使用 DELETE/UPDATE/DROP/TRUNCATE 等写操作语句

【知识注入】{{DB_SCHEMA}} {{HISTORICAL_CASES}}

【输出格式约束】JSON格式，每个规则包含完整的15个标准字段...

【Few-shot示例】（包含采购舞弊、费用造假、销售窜货三类场景的规则生成示例）

【安全底线】禁止生成可能造成数据库性能问题的SQL（如全表扫描无WHERE条件的大表）
```

### 2.5 Prompt Token 预算

| 组成部分 | Token 预算 | 占比 |
|----------|-----------|------|
| System Prompt | ~1,200 | 1.9% |
| Few-shot 示例 | ~1,500 | 2.3% |
| 数据库Schema注入 | ~4,000 | 6.3% |
| 历史案例 | ~2,000 | 3.1% |
| 输出预留 | ~4,000 | 6.3% |
| **已使用** | **~12,700** | **19.8%** |

### 2.6 工具定义

| 工具ID | 名称 | 用途 | 超时 | 重试 |
|--------|------|------|------|------|
| `kb_search_risk_rules` | 知识库检索 | 检索历史风险规则、数据库字段定义、历史案例 | 5s | 1 |
| `sql_syntax_validate` | SQL语法校验 | 在测试环境执行EXPLAIN验证SQL语法和性能 | 10s | 1 |
| `sql_test_execute` | SQL测试执行 | 在测试环境LIMIT 10执行，验证返回结果格式 | 15s | 1 |

### 2.7 工具调用依赖图

```
  risk-rule-agent
       │
       ├── 阶段1: kb_search_risk_rules（检索DB Schema + 历史规则）
       │
       ├── 阶段2: LLM推理 → 生成三级场景+规则+SQL
       │
       └── 阶段3: 逐条SQL校验（串行，每条独立）
           ├── sql_syntax_validate → 语法错误 → 自动修正（1次）
           └── sql_test_execute → 结果异常 → 标记人工审核
```

### 2.8 LLM 配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| 模型入口 | Model Gateway | 使用风险监控模块路由策略选择 provider |
| temperature | `0.4` | 中等温度，规则生成需要创造性但有逻辑约束 |
| max_tokens | `8192` | 多条规则+SQL输出较大 |
| 超时 | `45s` | 批量生成场景较长 |

### 2.9 降级行为矩阵

| 故障场景 | 降级行为 |
|----------|----------|
| 数据库Schema不可用 | 基于历史规则中的表名/字段名推断，标记"Schema未知，需人工核实" |
| SQL测试环境不可用 | 跳过测试执行，所有SQL标记"未经测试验证"，人工审核时需在测试环境手动验证 |
| LLM不可用 | 无法自动生成规则 → 切换为纯人工录入模式 |

### 2.10 HITL 守门集成规范

风险规则Agent的守门界面特殊设计：
- **规则预览表**：15列完整展示每条规则的所有字段
- **SQL高亮**：SQL语句代码高亮显示，语法错误红色标注
- **测试结果列**：展示测试环境EXPLAIN和LIMIT执行结果
- **批量操作**：支持逐条通过/驳回、全选通过、批量驳回
- **驳回原因分类**：语法错误/逻辑错误/场景不合理/阈值不当/重复规则

### 2.11 Agent 级监控指标

| 指标 | 类型 | 告警阈值 |
|------|------|----------|
| SQL语法一次通过率 | 技术 | < 70% → P3 |
| 规则审核通过率 | 业务 | < 60% → P2 |
| 规则有效率（上线后未被标记误报的比例） | 业务 | < 80% → P2（需持续追踪） |
| 单次生成规则数 | 业务 | 平均 < 3条（输入场景充分时） → P3 |

### 2.12 Golden Test Set

| 用例ID | 场景 | 期望输出 |
|--------|------|----------|
| `rule-golden-01` | 采购舞弊-围标串标 | 生成≥2条SQL，含IP地址分析和供应商关联分析 |
| `rule-golden-02` | 费用造假-虚假报销 | 生成≥2条SQL，含金额异常和频次异常检测 |
| `rule-golden-03` | 销售窜货-跨区域销售 | 生成≥1条SQL，含区域和经销商匹配 |
| `rule-golden-04` | 数据库Schema缺失部分表 | 标记"Schema未知"，基于通用字段名推测 |

---

## 三、风险分析 Agent（risk-analysis-agent）详细设计

> ⚠️ **架构变更**（2026-06-20）：此 Agent 已拆分为 `risk-scan-agent`、`risk-merge-agent`、`risk-classify-agent` 三个独立 Agent。`risk-analysis-agent` 保留为向后兼容的外观类，内部委托给上述三个 Agent。新代码应直接使用独立 Agent。详见 [02b-risk-monitoring-architecture-analysis.md](02b-risk-monitoring-architecture-analysis.md)。
>
> 新增的 3 个 Agent 详细设计见 §四、§五、§六。

### 3.1 Agent 概览卡片（兼容外观）

| 属性 | 值 |
|------|-----|
| **Agent ID** | `risk-analysis-agent` |
| **名称** | 风险分析 Agent |
| **所属模块** | 风险监控 |
| **工作流阶段** | [6.2] 异常数据生成 → [6.3] 主体合并 → [6.4] 风险定性 |
| **角色身份** | 风险分析师（15年审计+数据分析经验） |
| **核心任务** | 执行规则SQL→AI初核异常→按主体合并重复预警→自动判定风险类型/等级/处置建议 |
| **上游** | `risk-rule-agent`（风险清单知识库）+ 业务数据库 + 外部数据源 |
| **下游** | 廉洁监察/内控评价/商业秘密/行为风险 模块（风险推送） |
| **复杂度** | 🔴 高 — 三子阶段流水线，数据量敏感 |
| **HITL守门** | ✅ 是 — AI初核后人工二次复核；风险定性后碳基可修正 |

### 3.2 Agent 状态机

```
┌──────────┐   ┌─────────────────┐   ┌──────────────┐   ┌──────────────┐
│   IDLE   │──→│ 子阶段1:         │──→│ 子阶段2:      │──→│ 子阶段3:     │
│  初始化   │   │ EXECUTE_FILTER  │   │ ENTITY_MERGE │   │ RISK_CLASSIFY│
└──────────┘   │ SQL执行+AI初核   │   │ 主体识别+合并 │   │ 风险定性     │
                └─────────────────┘   └──────────────┘   └──────┬───────┘
                                                                  │
                                                       ┌──────────┼──────────┐
                                                       │ 通过     │ 驳回     │ 修正
                                                       ▼         ▼         ▼
                                                ┌──────────┐ ┌──────────┐ ┌──────────┐
                                                │ 推送下游  │ │ REJECTED │ │ REVISING │
                                                │ COMPLETE │ └──────────┘ └──────────┘
                                                └──────────┘
```

### 3.3 输入/输出 Schema

```python
class RiskAnalysisAgentInput(BaseModel):
    task_id: str
    execution_mode: str  # scheduled (定时) / manual (手动触发)

    # 规则来源
    risk_rules: List[RiskRule] = Field(..., description="已审核通过的风险规则清单")

    # 数据源
    business_data_sources: List[str] = Field(..., description="业务数据库连接信息")
    external_data_sources: List[str] = Field(default_factory=list, description="外部数据API（企查查/舆情等）")

    # 执行参数
    target_business_units: List[str] = Field(default_factory=list, description="目标事业部（空=全部）")
    execution_date_range: Optional[dict] = Field(None, description="手动指定日期范围")

class AnomalyRecord(BaseModel):
    rule_id: str
    rule_level3_scenario: str
    anomaly_detail: dict               # 异常数据行
    ai_initial_judgment: str           # AI初核: normal/abnormal/uncertain
    ai_judgment_reason: str
    anomaly_score: float               # 异常评分 0-1

class MergedEntityRisk(BaseModel):
    entity_id: str                     # 分析主体ID（联系方式/公司名/人名）
    entity_type: str                   # 主体类型: employee/supplier/dealer/contact
    anomaly_count: int                 # 关联异常数量
    anomaly_records: List[AnomalyRecord]
    involved_indicators: List[str]     # 涉及的风险指标

class RiskClassification(BaseModel):
    risk_type: str                     # 合规风险/舞弊风险/商业秘密风险/其他
    risk_level: str                    # 高/中/低
    severity: str                      # 严重程度
    scope: str                         # 广泛性
    impact_assessment: dict            # 影响评估: {岗位/金额/业务范围/频次}
    disposal_suggestion: str           # 处置建议
    push_targets: List[str]            # 推送目标模块

class RiskAnalysisAgentOutput(BaseModel):
    # 子阶段1输出
    anomaly_records: List[AnomalyRecord]
    anomaly_summary: dict              # 异常汇总统计
    anomaly_pivot_table_doc_id: Optional[str]  # 风险预警异常数据透视表 (Excel)
    anomaly_analysis_report_doc_id: Optional[str]  # 风险预警异常数据分析报告 (Word)
    ai_filter_removed_count: int       # AI初核剔除数量

    # 子阶段2输出
    merged_entities: List[MergedEntityRisk]
    entity_merge_rationale: str
    merged_pivot_table_doc_id: Optional[str]  # 按主体合并后的风险透视表 (Excel)
    single_entity_reports: List[dict]  # [{entity_id, report_doc_id}] 单主体风险分析报告列表

    # 子阶段3输出
    risk_classifications: List[RiskClassification]
    confidence: str
    processing_time_ms: int
```

### 3.4 System Prompt 设计

```
【角色锚定——子阶段1：异常初核】
你是一位经验丰富的风险数据分析师，擅长从海量业务数据中识别真正的异常。
你知道业务数据的"正常波动范围"，能够区分正常业务行为和真正的风险信号。
你的任务是：对每条SQL规则跑出的异常数据行进行初核，判断其是否为真正的异常。

初核标准（每个判断必须引用具体原因）：
- normal: 数据在正常业务范围内（如季节性促销导致的大额订单）
- abnormal: 数据明显偏离正常模式（如新成立供应商获大额订单且无历史合作记录）
- uncertain: 数据存在疑点但信息不足以确定（标记为"待人工复核"）

【角色锚定——子阶段2：主体合并】
你擅长从散乱的异常记录中识别出同一分析主体（人/公司/联系方式）。
合并规则：同一联系方式（电话/邮箱）→ 同一姓名/公司名（模糊匹配）→ 同一地址
标记每个主体涉及的指标数量和最严重的风险信号。

【角色锚定——子阶段3：风险定性】
你擅长综合判断风险的性质、等级和影响范围。
综合评估维度：岗位敏感度 × 金额大小 × 业务影响范围 × 发生频次
自动判定风险类型（合规风险/舞弊风险/商业秘密风险），给出处置建议和推送目标。

【知识注入】{{HISTORICAL_RISK_CASES}} {{RISK_LEVEL_CRITERIA}} {{DISPOSAL_GUIDELINES}}

【输出格式约束】子阶段1/2/3各有独立的JSON输出格式...
```

### 3.5 Prompt Token 预算（子阶段1最关键）

| 子阶段 | 输入 Token | 输出 Token | 备注 |
|--------|-----------|-----------|------|
| 子阶段1: 异常初核 | ~15K（异常数据行+规则上下文）| ~5K | 数据量敏感，大批量需分批处理 |
| 子阶段2: 主体合并 | ~5K | ~2K | — |
| 子阶段3: 风险定性 | ~3K | ~2K | — |

### 3.6 工具定义

| 工具ID | 名称 | 用途 | 超时 | 重试 |
|--------|------|------|------|------|
| `sql_batch_execute` | SQL批量执行 | 按规则清单批量执行业务数据库SQL查询 | 120s | 1 |
| `external_data_query` | 外部数据查询 | 调用企查查API/舆情API获取工商信息和外部风险数据 | 10s | 2 |
| `entity_dedup_merge` | 主体去重合并 | 基于联系方式/姓名/地址模糊匹配进行主体合并 | 5s | 1 |
| `kb_search_risk_history` | 历史风险检索 | 检索历史风险分析结果，辅助定性判断 | 5s | 1 |
| `push_risk_result` | 风险结果推送 | 将定性后的风险结果推送至目标模块 | 10s | 2 |

### 3.7 工具调用依赖图

```
  risk-analysis-agent
       │
       ├── 子阶段1: EXECUTE_FILTER
       │   ├── sql_batch_execute（并行执行多条SQL）
       │   ├── external_data_query（并行查询外部数据）
       │   ├── 聚合SQL结果 + 外部数据
       │   └── LLM推理: AI初核（分批处理，每批100条）
       │
       ├── 子阶段2: ENTITY_MERGE
       │   ├── entity_dedup_merge（算法合并 + LLM补充合并）
       │   └── 生成单主体风险分析报告
       │
       └── 子阶段3: RISK_CLASSIFY
           ├── kb_search_risk_history（检索历史案例辅助定性）
           ├── LLM推理: 风险定性
           ├── push_risk_result（推送至目标模块）
           └── PENDING_APPROVAL（等待碳基守门）
```

### 3.8 LLM 配置

| 配置项 | 子阶段1 | 子阶段2 | 子阶段3 |
|--------|---------|---------|---------|
| temperature | 0.2 | 0.2 | 0.3 |
| max_tokens | 8192 | 4096 | 4096 |
| 超时 | 60s | 30s | 30s |
| 分批处理 | 100条/批 | — | — |

### 3.9 降级行为矩阵

| 故障场景 | 降级行为 |
|----------|----------|
| 某条SQL执行超时 | 跳过该规则，标记"执行超时"，继续执行其他规则 |
| 业务数据库不可用 | 整体扫描任务推迟，保留规则清单待数据库恢复后补跑 |
| 外部数据API不可用 | 跳过外部数据增强，基于内部数据单独分析，标记"外部数据缺失" |
| AI初核发现大量uncertain (>30%) | 降低置信度，建议人工重点复核 |
| 主体合并不完整 | 标记"可能存在未合并的关联主体"，建议人工核查 |
| push_risk_result部分失败 | 成功推送的模块不受影响，失败模块任务保留队列重试 |

### 3.10 幂等性设计

| 属性 | 值 |
|------|-----|
| **幂等键** | `task_id` + `execution_date`（同一天的同一任务不重复执行） |
| **增量执行** | 定时任务模式支持增量扫描（仅扫描上次执行后新增/变更的数据） |
| **结果去重** | 同一分析主体+同一风险规则+同一日期 → 合并为一条，避免重复推送 |

### 3.11 HITL 守门集成规范

风险分析Agent的三级守门：
1. **子阶段1守门**：AI初核结果列表，碳基可对每条异常标记"确认/驳回/修正"
2. **子阶段2守门**（可选）：仅当碳基想查看合并逻辑时展开
3. **子阶段3守门**：风险定性报告，碳基可修正风险类型/等级/处置建议/推送目标

### 3.12 Agent 级监控指标

| 指标 | 类型 | 告警阈值 |
|------|------|----------|
| AI初核准确率（人工复核确认比例） | 业务 | < 70% → P2 |
| 误报率（AI标记abnormal但人工判定为normal） | 业务 | > 30% → P2 |
| 漏报率（人工发现但AI未标记的异常） | 业务 | > 10% → P1 |
| SQL执行成功率 | 技术 | < 95% → P2 |
| 主体合并准确率 | 业务 | < 80% → P3 |
| 风险定性采纳率 | 业务 | < 75% → P2 |
| 全流程端到端延迟P95 | 技术 | > 5min → P3 |

### 3.13 Golden Test Set

| 用例ID | 场景 | 期望输出 |
|--------|------|----------|
| `ranal-golden-01` | 3条规则共产生50条异常，其中10条为正常业务 | AI初核正确标记10条normal+35条abnormal+5条uncertain |
| `ranal-golden-02` | 同一供应商在3条规则中都出现异常 | 主体合并为1条，涉及3个指标 |
| `ranal-golden-03` | 明显的舞弊案件（金额大+关联公司+IP相同） | 风险定性: 舞弊风险/高/建议推送廉洁监察 |
| `ranal-golden-04` | SQL执行中1条规则超时 | 跳过该规则，其余正常执行，最终报告标注 |
| `ranal-golden-05` | 大量正常业务波动（双11促销数据） | AI初核识别为normal，不标记为异常 |

### 3.14 成本追踪

| 成本项 | 单次扫描估算 | 月度估算(30次全量扫描) |
|--------|------------|----------------------|
| LLM Token (初核，500条异常) | ~20K tokens | ~600K tokens |
| LLM Token (合并+定性) | ~8K tokens | ~240K tokens |
| SQL执行 | — | — |
| 外部API调用 | 0-20次 | 0-600次 |
| **单次总成本** | **~¥0.30** | **~¥9/月** |

### 3.15 [6.6] 处置结果回流与指标迭代（闭环设计）

虽然[6.6]主要由系统编排调度，但risk-analysis-agent和risk-rule-agent需感知此闭环：

```
处置结果回流数据流:
  
  各模块处置结果（廉洁监察/内控评价/商业秘密/行为风险）
       │
       ▼
  ┌─────────────────────────────────────────────────┐
  │ 回流分析引擎 (系统调度，非Agent)                    │
  │                                                  │
  │ 1. 收集各模块对每条风险推送的处置反馈:              │
  │    - 已处置: 推送准确 → 规则保留                   │
  │    - 整改中: 推送准确 → 规则保留                   │
  │    - 无需处置: 误报 → 标记规则需优化               │
  │    - 误报: 规则本身有问题 → 标记规则需修正或作废    │
  │                                                  │
  │ 2. 按规则统计:                                     │
  │    └── 误报率 > 30% 的规则 → 自动标记"需优化"      │
  │    └── 连续3个月准确率 < 50% → 建议作废            │
  │                                                  │
  │ 3. 反馈给 risk-rule-agent:                        │
  │    └── 触发规则优化流程（调整SQL/阈值/监控范围）    │
  │    └── 更新风险清单知识库中的规则状态               │
  │                                                  │
  │ 4. 闭环记录:                                      │
  │    └── 风险处置闭环台账 (ES索引)                   │
  │    └── 指标优化迭代记录 (PG)                      │
  └─────────────────────────────────────────────────┘
```

**risk-analysis-agent 接收回流信号**:
- 每次扫描执行前检查风险清单知识库中规则的 `status` 字段
- `active` → 正常执行
- `optimizing` → 使用调整后的SQL/阈值执行
- `deprecated` → 跳过不执行

**risk-rule-agent 响应优化触发**:
- 收到"规则误报率过高"信号 → 自动分析误报模式 → 建议SQL调整方案 → 人工审核

### 3.16 批量处理分区策略

risk-analysis-agent子阶段1处理TB级数据时的分区策略：

| 分区维度 | 策略 | 并行度 | 说明 |
|----------|------|--------|------|
| **按事业部** | 每个事业部独立Worker执行 | 3路并行 (ecovacs/tineco/group) | 隔离不同事业部的数据 |
| **按规则** | 每条SQL独立提交Celery任务 | 最多10路并行 | 单条SQL超时不阻塞其他SQL |
| **按时间** | 全量扫描分片为30天窗口 | 串行执行（保证时序） | 增量扫描仅处理上次后的新数据 |
| **按数据量** | 单次LLM初核≤100条异常 | 100条/批 | 超出则自动分多批 |

```python
# 分区执行伪代码
async def execute_partitioned_scan(rules, business_units):
    tasks = []
    for unit in business_units:
        for rule in rules:
            if rule.monitor_business_unit in (unit, "all"):
                tasks.append(
                    celery_task(
                        f"risk_scan:{rule.id}:{unit}",
                        sql=rule.sql_statement.replace("{unit}", unit),
                        timeout=120
                    )
                )
    # 并行提交，独立超时
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 聚合结果 → AI初核
    return aggregate_and_filter(results)
```

---

## 四、风险扫描 Agent（risk-scan-agent）详细设计

### 4.1 Agent 概览卡片

| 属性 | 值 |
|------|-----|
| **Agent ID** | `risk-scan-agent` |
| **名称** | 风险扫描 Agent |
| **所属模块** | 风险监控 |
| **工作流阶段** | [6.2] SQL执行 + AI初核异常 |
| **角色身份** | 风险扫描分析师（精通SQL执行和业务异常识别） |
| **核心任务** | 执行已审核通过的风险规则SQL → 聚合结果 → AI初核将每条异常分类为 normal/abnormal/uncertain |
| **上游** | `risk-rule-agent`（风险规则清单）+ Celery Worker（SQL预执行） |
| **下游** | `risk-merge-agent`（主体合并） / `deep-analysis-sentinel`（uncertain过多时） |
| **复杂度** | 🔴 高 — 数据量敏感，TB级需分区执行 |
| **HITL守门** | ✅ 是 — AI初核结果需人工二次复核 |

### 4.2 Agent 状态机

```
  ┌──────────┐   ┌─────────────────┐   ┌──────────────────┐
  │   IDLE   │──→│ EXECUTE_FILTER  │──→│ SENTINEL_CHECK   │
  │  初始化   │   │ SQL执行+AI初核   │   │ 哨兵条件判定      │
  └──────────┘   └─────────────────┘   └──────┬───────────┘
                                               │
                                    ┌──────────┼──────────┐
                                    │ 正常     │ uncertain│ SQL失败
                                    ▼          │ >30%     │
                              ┌──────────┐     ▼          ▼
                              │ 下一阶段  │  ┌────────┐ ┌──────────┐
                              │ entity   │  │ deep   │ │ schema   │
                              │ _merge   │  │analysis│ │adaptation│
                              └──────────┘  │sentinel│ │ sentinel │
                                            └────────┘ └──────────┘
```

### 4.3 输入/输出 Schema

```python
class RiskScanAgentInput(BaseModel):
    task_id: str
    execution_mode: RiskExecutionMode  # scheduled / manual
    risk_rules: list[RiskRule]         # 已审核通过的风险规则清单
    business_data_sources: list[str]   # 业务数据库连接信息
    external_data_sources: list[str]   # 外部数据API
    target_business_units: list[str]   # 目标事业部
    execution_date_range: dict | None  # 手动指定日期范围

class RiskScanAgentOutput(BaseModel):
    anomaly_records: list[AnomalyRecord]    # AI初核后的异常记录
    anomaly_summary: dict                   # 异常汇总统计
    ai_filter_removed_count: int            # AI初核剔除数量
    sql_execution_summary: dict             # SQL执行汇总
    sentinel_flags: dict                    # 哨兵标记
    confidence: Confidence
    processing_time_ms: int
```

### 4.4 LLM 配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| temperature | `0.2` | 低温度，异常判断需要高一致性 |
| max_tokens | `8192` | 批量异常数据输出较大 |
| 超时 | `60s` | 数据量敏感，需分批处理 |
| 分批处理 | `100条/批` | 超出则自动分多批 |

### 4.5 哨兵输出

scan-agent 输出中包含 `sentinel_flags` 字段，供 Graph 进行条件路由：

| 哨兵标记 | 触发条件 | 路由目标 |
|----------|---------|---------|
| `deep_analysis_needed` | uncertain 比例 > 30% | `deep_analysis_sentinel` |
| `schema_adaptation_needed` | SQL 执行成功率 < 95% | `schema_adaptation_sentinel` |

---

## 五、风险合并 Agent（risk-merge-agent）详细设计

### 5.1 Agent 概览卡片

| 属性 | 值 |
|------|-----|
| **Agent ID** | `risk-merge-agent` |
| **名称** | 风险合并 Agent |
| **所属模块** | 风险监控 |
| **工作流阶段** | [6.3] 主体识别与合并去重 |
| **角色身份** | 主体识别分析师（精通实体解析和数据匹配） |
| **核心任务** | 从散乱的异常记录中识别同一分析主体（人/公司/联系方式），按联系方式/姓名/地址模糊匹配合并，生成单主体风险透视表 |
| **上游** | `risk-scan-agent`（AI初核后的异常记录） |
| **下游** | `risk-classify-agent`（风险定性） |
| **复杂度** | 🟡 中 |
| **复用潜力** | ⭐ 可被廉洁监察模块复用（调查阶段也需要合并关联主体） |

### 5.2 合并规则

```
优先级1: 同一联系方式（电话/邮箱）→ 同一主体
优先级2: 同一姓名/公司名（模糊匹配，含同音字、简繁体、常见拼写变体）→ 同一主体
优先级3: 同一地址 → 同一主体
```

### 5.3 输入/输出 Schema

```python
class RiskMergeAgentInput(BaseModel):
    task_id: str
    anomaly_records: list[AnomalyRecord]  # AI初核后的异常记录
    merge_config: dict                     # 合并配置

class RiskMergeAgentOutput(BaseModel):
    merged_entities: list[MergedEntityRisk]  # 合并后的主体风险列表
    entity_merge_rationale: str              # 合并逻辑说明
    sentinel_flags: dict                     # 哨兵标记（merge_issues_detected等）
    confidence: Confidence
    processing_time_ms: int
```

### 5.4 LLM 配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| temperature | `0.2` | 低温度，主体匹配合并需高精度 |
| max_tokens | `4096` | — |
| 超时 | `30s` | — |

---

## 六、风险定性 Agent（risk-classify-agent）详细设计

### 6.1 Agent 概览卡片

| 属性 | 值 |
|------|-----|
| **Agent ID** | `risk-classify-agent` |
| **名称** | 风险定性 Agent |
| **所属模块** | 风险监控 |
| **工作流阶段** | [6.4] 风险类型/等级/处置建议判定 |
| **角色身份** | 风险定性分析师（15年审计+风控经验） |
| **核心任务** | 综合判断风险性质/等级/影响范围，自动判定风险类型，给出处置建议和推送目标 |
| **上游** | `risk-merge-agent`（合并后的主体风险列表） |
| **下游** | `result_push`（结果推送）/ `rule-optimization-sentinel` / `novel-risk-sentinel` |
| **复杂度** | 🟡 中 |

### 6.2 评估维度

```
综合评估 = 岗位敏感度 × 金额大小 × 业务影响范围 × 发生频次

风险类型: 合规风险 / 舞弊风险 / 商业秘密风险 / 其他
风险等级: 高 / 中 / 低
推送目标: integrity_supervision / internal_control_evaluation / trade_secrets / behavioral_risk / business_department
```

### 6.3 输入/输出 Schema

```python
class RiskClassifyAgentInput(BaseModel):
    task_id: str
    merged_entities: list[MergedEntityRisk]  # 合并后的主体风险列表
    anomaly_summary: dict                     # 上游扫描汇总（上下文）
    rule_optimization_signal: bool            # 来自回流分析的规则优化信号

class RiskClassifyAgentOutput(BaseModel):
    risk_classifications: list[RiskClassification]  # 风险分类列表
    classification_summary: dict                     # 分类汇总
    sentinel_flags: dict                             # 哨兵标记
    confidence: Confidence
    processing_time_ms: int
```

### 6.4 LLM 配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| temperature | `0.3` | 中等温度，定性判断需要一定的推理灵活性 |
| max_tokens | `4096` | — |
| 超时 | `30s` | — |

### 6.5 哨兵输出

classify-agent 输出中包含 `sentinel_flags` 字段：

| 哨兵标记 | 触发条件 | 路由目标 |
|----------|---------|---------|
| `rule_optimization_needed` | 低风险比例 > 50% 或外部优化信号 | `rule_optimization_sentinel` |
| `novel_risk_detected` | 发现超出已有规则覆盖的风险模式 | `novel_risk_sentinel` |

---

## 七、通用生产级配置

风险监控模块Agent复用文档01附录D中的生产级运行时配置，包括：
- Agent健康检查规范 (§D.1)
- 并发控制策略 (§D.2)
- LangGraph节点配置模板 (§D.3)
- Agent预热策略 (§D.4)
- 超时传播机制 (§D.5)
- 工具调用PII脱敏 (§D.6)

> 引用路径：`../agents/01-integrity-supervision-agents.md` 附录 D

---

## 附录：文档修订历史

| 版本 | 日期 | 修订说明 |
|------|------|----------|
| v1.0 | 2026-06-05 | 初始版本：覆盖风险监控模块2个Agent的完整设计 |
| v1.1 | 2026-06-20 | 架构升级：risk-analysis-agent 拆分为 risk-scan-agent + risk-merge-agent + risk-classify-agent，新增异常哨兵机制。参照 02b-risk-monitoring-architecture-analysis.md |
