# 内控评价模块 — Agent 详细设计文档（含共享Agent完整设计）

> **所属系统**：赫尔墨斯（Hermes）风险控制 AI 智能体
> **模块编号**：03
> **模块名称**：内控评价（合规评价）
> **⚠ 重要**：本文档包含三个跨模块共享Agent的完整设计 — 审计方案Agent、审计检查Agent、访谈Agent。其他模块（专项审计、离任审计）仅需定义差异化参数。
> **依赖文档**：[系统架构设计](../architecture-design.md) | [总体需求](../hermes-requirements.md) | [模块需求](../modules/03-internal-control-evaluation.md)
> **文档版本**：v1.0 | **最后更新**：2026-06-05

---

## 一、模块 Agent 全景

### 1.1 Agent 清单

| Agent ID | 名称 | 角色身份 | 共享范围 | 复杂度 | 状态 |
|----------|------|----------|----------|--------|------|
| `audit-plan-agent` | 审计方案 Agent ⭐ | 审计规划师 | 内控评价 + 专项审计 + 离任审计 | 🔴 高 | ⏳ 规划中 |
| `audit-check-agent` | 审计检查 Agent ⭐ | 审计执行师 | 内控评价 + 专项审计 + 离任审计 | 🔴 高 | ⏳ 规划中 |
| `interview-agent` | 访谈 Agent ⭐ | 访谈协调师 | 内控评价 + 专项审计 + 离任审计 + 廉洁监察 | 🟡 中 | ⏳ 规划中 |

> ⭐ = 跨模块共享Agent，本文档为权威设计来源。其他模块引用时使用 `@see doc/agents/03-*-agents.md` 并定义差异化参数。

### 1.2 工作流位置

```
┌──────────────────────────────────────────────────────────────────┐
│               内控评价 13 步骤工作流 + 19 个业务循环                │
│                                                                   │
│  立项                                                             │
│    ↓                                                              │
│  ┌─────────────────────┐    ┌─────────────────────┐              │
│  │ audit-plan-agent    │    │ interview-agent     │              │
│  │ 审计方案生成(5部分)  │    │ 访谈人员清单+计划    │              │
│  │ [7.2]               │    │ [7.3]               │              │
│  └────────┬────────────┘    └────────┬────────────┘              │
│           │                          │                            │
│           └──────────┬───────────────┘                            │
│                      ↓                                            │
│  ┌──────────────────────────────────────────┐                    │
│  │ interview-agent: 访谈问卷生成 [7.4]        │                    │
│  └──────────────────────────────────────────┘                    │
│                      ↓                                            │
│  ┌──────────────────────────────────────────┐                    │
│  │ 完善风控矩阵 [7.5] → 拆分测试底稿 [7.6]    │                    │
│  └──────────────────────────────────────────┘                    │
│                      ↓                                            │
│  ┌──────────────────────────────────────────┐                    │
│  │ audit-check-agent: 设计缺陷评估 [7.7]      │                    │
│  └──────────────────────────────────────────┘                    │
│                      ↓                                            │
│  ┌──────────────────────────────────────────┐                    │
│  │ 资料需求清单 [7.8]                         │                    │
│  └──────────────────────────────────────────┘                    │
│                      ↓                                            │
│  ┌──────────────────────────────────────────┐                    │
│  │ audit-check-agent: 执行缺陷评估 [7.9]      │                    │
│  └──────────────────────────────────────────┘                    │
│                      ↓                                            │
│  ┌──────────────────────────────────────────┐                    │
│  │ 缺陷确认 [7.10] → 总体打分 [7.11]          │                    │
│  └──────────────────────────────────────────┘                    │
│                      ↓                                            │
│  ┌──────────────────────────────────────────┐                    │
│  │ 出具内控评价报告 [7.12]                    │                    │
│  └──────────────────────────────────────────┘                    │
└──────────────────────────────────────────────────────────────────┘
```

### 1.3 模块 Agent 依赖与 SLA 链

| Agent | P50 目标 | P95 目标 | 关键耗时 |
|-------|----------|----------|----------|
| `audit-plan-agent` | < 15s | < 30s | KB检索(5部分方案材料) + LLM推理 |
| `interview-agent` (人员匹配+计划) | < 10s | < 20s | 组织架构检索 + 岗位职责匹配 |
| `interview-agent` (问卷生成) | < 10s | < 20s | KB检索(历史问卷) + LLM推理 |
| `audit-check-agent` (设计缺陷) | < 20s | < 40s | 制度文档逐份分析 + 矩阵对比 |
| `audit-check-agent` (执行缺陷) | < 30s | < 60s | 系统数据/手动数据对比 + 穿行测试结果分析 |

---

## 二、审计方案 Agent（audit-plan-agent）⭐ 跨模块共享

### 2.1 Agent 概览卡片

| 属性 | 值 |
|------|-----|
| **Agent ID** | `audit-plan-agent` |
| **名称** | 审计方案 Agent |
| **角色身份** | 审计规划师（10年审计经验，熟悉各类审计方法论） |
| **核心任务** | 根据审计目的/重点/范围，自动生成标准化审计方案（含范围、目标、方法、程序、抽样策略、时间安排、人员分工） |
| **共享范围** | 内控评价（13步骤+19循环）、专项审计（5阶段）、离任审计（6阶段） |
| **复杂度** | 🔴 高 — 三种审计类型的方案结构差异大，需要模块化组装 |
| **HITL守门** | ✅ 是 |

### 2.2 共享接口契约（统一输入/输出）

审计方案Agent被三个模块调用，每种模块传入不同的参数组合：

```python
class AuditType(str, Enum):
    INTERNAL_CONTROL = "ic_evaluation"   # 内控评价
    SPECIAL_AUDIT = "special_audit"         # 专项审计
    EXIT_AUDIT = "exit_audit"              # 离任审计

class AuditPlanAgentInput(BaseModel):
    """统一输入接口"""
    task_id: str
    audit_type: AuditType                    # 审计类型 → 决定方案模板
    client: Client

    # === 通用参数 ===
    audit_objective: str                     # 审计目的
    audit_focus: List[str]                   # 审计重点
    audit_period: str                        # 审计期间
    audited_entity: str                      # 被审计单位/部门
    project_leader: str                      # 项目组长
    project_members: List[str]               # 项目组员

    # === 内控评价专用参数 ===
    business_cycles: Optional[List[str]] = None          # 业务循环列表（19个循环中选择）
    control_activities: Optional[List[dict]] = None       # 标准控制活动选择
    evaluation_criteria: Optional[str] = None             # 评价依据

    # === 专项审计专用参数 ===
    audit_method_preference: Optional[str] = None         # 审计方法偏好
    sampling_requirements: Optional[str] = None           # 抽样要求

    # === 离任审计专用参数 ===
    departing_person_info: Optional[dict] = None          # 被审计人信息
    position_duties: Optional[List[str]] = None           # 岗位职责列表
    tenure_years: Optional[float] = None                  # 本岗位任职年限

    context_version: str = "1.0"
```

```python
class AuditPlan(BaseModel):
    """统一输出结构"""
    # 5部分核心方案
    project_basic_info: dict                 # 项目基本信息
    evaluation_basis: List[str]              # 评价依据/审计依据
    audit_scope: dict                        # 审计范围（职责范围+业务范围）
    audit_implementation_rules: List[dict]   # 审计实施细则（目标+关键控制点+测试程序+时间+人员）
    deficiency_criteria: dict                # 缺陷认定标准

    # 审计方案附加
    sampling_strategy: Optional[dict]        # 抽样策略
    timeline: dict                           # 时间安排
    personnel_assignment: dict               # 人员分工

    # 元数据
    referenced_historical_plans: List[str]   # 引用的历史方案ID
    confidence: str
```

### 2.3 System Prompt 设计

```
【角色锚定】
你是一位有10年审计经验的审计规划师，精通COSO内控框架和各类审计方法论。
你曾为多家大型企业设计审计方案，涵盖内控评价、专项审计、离任审计等多种类型。
你的专长是根据审计目的和目标，快速匹配最佳审计策略，生成可落地的详细审计方案。

【核心任务】
根据审计类型和输入参数，生成包含5部分的完整审计方案：
1. 项目基本信息
2. 审计依据/评价依据
3. 审计范围
4. 审计实施细则（含目标、关键控制点识别、测试程序、时间安排、人员分工）
5. 缺陷认定标准

【审计类型差异】
- ic_evaluation: 覆盖19个业务循环，按控制活动底表生成设计测试+执行测试方案
- special_audit: 聚焦审计目的和重点，检索关联历史方案进行优化
- exit_audit: 读取岗位职责→在业务方案库中检索强关联内容→在个人方案库中检索通用检查项
  - 审计期间计算：1年<本岗位≤5年→向前计算三年；>5年→向前计算一年

【知识注入】{{KB_AUDIT_PLAN}} {{HISTORICAL_PLANS}} {{REGULATIONS}}

【Few-shot示例】（内控评价/专项审计/离任审计各1例）

【安全底线】标准安全约束
```

### 2.4 模块差异化参数速查表

| 参数 | 内控评价 | 专项审计 | 离任审计 |
|------|----------|----------|----------|
| `audit_type` | `ic_evaluation` | `special_audit` | `exit_audit` |
| 必填额外参数 | `business_cycles`, `control_activities` | `sampling_requirements` | `departing_person_info`, `position_duties` |
| 方案模板 | 内控评价方案模板(含19循环矩阵) | 专项审计方案模板 | 离任审计方案模板 |
| 知识库分区 | `kb_ic_plan` | `kb_sa_plan` | `kb_ea_plan` + `kb_ea_position` |
| 匹配逻辑 | 按业务循环匹配历史方案 | 按审计目的/重点关键词匹配 | 按岗位职责→业务方案 + 个人通用方案 |
| 抽样策略 | 按控制频率计算样本量 | AI根据数据量和风险程度建议 | 同专项审计 + 任职年限修正 |

### 2.5 工具定义

| 工具ID | 名称 | 用途 | 超时 |
|--------|------|------|------|
| `kb_search_audit_plan` | 审计方案知识库检索 | 检索历史审计方案、方案模板、法规依据 | 5s |
| `position_duty_match` | 岗位职责匹配（离任审计专用） | 读取岗位职责→在业务方案库中检索强关联内容 | 5s |
| `sampling_calculator` | 抽样计算器 | 根据业务量级和风险程度计算样本量和抽样方法 | 3s |
| `doc_generate_audit_plan` | 审计方案文档生成 | 按模板生成完整审计方案Word文档 | 15s（异步） |

### 2.6-2.12（其他维度摘要）

| 维度 | 关键设计 |
|------|----------|
| **LLM配置** | temperature=0.3, max_tokens=8192 |
| **Token预算** | System ~1200 + Few-shot ~1500 + KB ~4000 + 参数 ~2000 + 输出 ~4000 ≈ 12,700 (19.8%) |
| **降级** | 历史方案不可用→通用模板生成；人员匹配失败→标记"需人工确定访谈范围" |
| **幂等** | `task_id` + `audit_type` + `audit_period` |

---

## 三、审计检查 Agent（audit-check-agent）⭐ 跨模块共享

### 3.1 Agent 概览卡片

| 属性 | 值 |
|------|-----|
| **Agent ID** | `audit-check-agent` |
| **名称** | 审计检查 Agent |
| **角色身份** | 审计执行师（15年审计实务经验） |
| **核心任务** | 执行设计缺陷评估（制度比对）和执行缺陷评估（穿行测试+数据分析），输出缺陷清单+底稿+打分 |
| **共享范围** | 内控评价、专项审计、离任审计 |
| **复杂度** | 🔴 高 — 设计缺陷+执行缺陷双轨评估，含打分逻辑 |
| **HITL守门** | ✅ 是 |

### 3.2 共享接口契约

```python
class CheckType(str, Enum):
    DESIGN = "design"          # 设计缺陷评估
    EXECUTION = "execution"    # 执行缺陷评估

class AuditCheckAgentInput(BaseModel):
    task_id: str
    audit_type: AuditType
    check_type: CheckType

    # 审计方案（上游输出）
    audit_plan: AuditPlan

    # 设计缺陷评估专用
    design_test_matrix: Optional[List[dict]] = None    # 设计测试底稿（含制度编号、名称）
    policy_documents: Optional[List[str]] = None        # 制度文档ID列表
    historical_design_deficiencies: Optional[List[dict]] = None

    # 执行缺陷评估专用
    execution_test_results: Optional[List[dict]] = None # 系统对接数据/穿行测试结果
    manual_upload_data: Optional[List[dict]] = None      # 手动上传数据
    historical_execution_deficiencies: Optional[List[dict]] = None

    # 评分标准
    scoring_criteria: dict                              # 设计缺陷/执行缺陷评分标准

class Deficiency(BaseModel):
    deficiency_id: str
    deficiency_type: str              # 设计缺陷/执行缺陷
    deficiency_category: str          # 缺陷类型细分
    description: str                  # 缺陷描述
    related_policy: Optional[str]     # 关联制度编号
    related_control: str              # 关联控制活动
    business_cycle: str               # 所属业务循环
    severity_score: float             # 严重程度评分
    impact_assessment: str            # 影响评估
    suggestion: str                   # 整改建议
    responsible_dept: str             # 责任部门

class AuditCheckAgentOutput(BaseModel):
    deficiencies: List[Deficiency]
    total_score: float                # 总体评分
    score_breakdown: dict             # 评分明细
    working_paper_doc_id: Optional[str]  # 底稿文档
    confidence: str
```

### 3.3 System Prompt 设计（设计缺陷评估）

```
【角色锚定——设计缺陷评估】
你是一位内控设计评估专家，精通COSO框架和《企业内部控制基本规范》。
你的任务是：逐份阅读制度文档，比照风控矩阵中的控制活动要求，识别制度设计的缺陷。

评估维度：
1. 制度缺失：控制活动没有对应的制度文件支撑
2. 制度冲突：不同制度对同一控制活动的描述不一致
3. 制度过时：制度内容与现行组织架构/流程不符
4. 制度模糊：控制要求不具体，无法指导实际操作
5. 职责分离不足：授权、执行、记录、保管未有效分离

评分标准参照：{{SCORING_CRITERIA}}

【角色锚定——执行缺陷评估】
你是内控执行测试专家。根据穿行测试结果和数据分析，判断控制活动是否被有效执行。

评估维度：
1. 控制未执行：制度要求的控制活动在实际操作中缺失
2. 执行不及时：超过制度规定的时限
3. 执行不完整：控制活动部分执行但遗漏关键步骤
4. 执行人不符合：控制活动由未经授权的人员执行
5. 证据缺失：无法提供控制执行的记录或证据

【知识注入】{{POLICY_DOCS}} {{HISTORICAL_DEFICIENCIES}} {{SCORING_CRITERIA}}

【Few-shot示例】（设计缺陷/执行缺陷各2个正例）
```

### 3.4 工具定义

| 工具ID | 名称 | 用途 | 超时 |
|--------|------|------|------|
| `policy_doc_analyze` | 制度文档分析 | 逐份解析制度文档，提取控制相关条款 | 10s/份 |
| `kb_search_deficiencies` | 历史缺陷检索 | 检索历史设计缺陷和执行缺陷 | 5s |
| `control_matrix_compare` | 风控矩阵对比 | 将制度条款与风控矩阵逐项对比 | 10s |
| `scoring_engine` | 评分引擎 | 根据评分标准对缺陷进行自动打分 | 3s |
| `doc_generate_working_paper` | 底稿生成 | 生成审计工作底稿（Excel） | 15s（异步） |

### 3.5 关键设计要点

| 维度 | 设计 |
|------|------|
| **LLM配置** | temperature=0.2, max_tokens=8192 |
| **分批处理** | 19个循环的制度文件分批注入，每批≤5份 |
| **降级** | 制度文档不可用→标记"制度文件缺失，无法完成设计缺陷评估"，建议先补充制度 |
| **打分一致性** | 使用scoring_engine工具而非LLM推理打分，保证同类型缺陷评分一致 |
| **Golden Test Set** | 含已知设计缺陷和执行缺陷的标准测试案例各3个 |

---

## 四、访谈 Agent（interview-agent）⭐ 跨模块共享

### 4.1 Agent 概览卡片

| 属性 | 值 |
|------|-----|
| **Agent ID** | `interview-agent` |
| **名称** | 访谈 Agent |
| **角色身份** | 访谈协调师（精通审计访谈方法论和问卷设计） |
| **核心任务** | 匹配访谈人员→生成访谈计划→生成结构化访谈问卷→分析访谈结论完整性→判断是否需要补充提问 |
| **共享范围** | 内控评价 + 专项审计 + 离任审计 + 廉洁监察（最广泛共享的Agent） |
| **复杂度** | 🟡 中 |
| **HITL守门** | ✅ 是（访谈计划和问卷均需碳基确认） |

### 4.2 共享接口契约

```python
class InterviewAgentInput(BaseModel):
    task_id: str
    calling_module: str           # 调用模块: ic_evaluation/special_audit/exit_audit/integrity

    # 访谈上下文
    audit_plan_summary: str       # 审计方案摘要（含需访谈的业务领域）
    previous_findings: Optional[List[str]]  # 前期发现（如有）

    # 人员匹配参数
    target_departments: List[str]           # 目标部门
    target_positions: List[str]             # 目标岗位
    personnel_pool: Optional[List[dict]]    # 可选人员池（来自组织架构）

    # 问卷参数（按模块差异化）
    question_focus_areas: List[str]         # 问题聚焦领域

class InterviewQuestionnaire(BaseModel):
    target_person: str
    position: str
    department: str
    interview_strategy: str       # 访谈策略（如 "先开放式后聚焦式"）
    questions: List[dict]         # [{order, question, purpose, expected_info}]
    estimated_duration_min: int

class InterviewAgentOutput(BaseModel):
    interview_plan: dict          # {personnel_list: [...], schedule: [...], strategy: "..."}
    questionnaires: List[InterviewQuestionnaire]
    interview_conclusion_analysis: Optional[str]  # 访谈后：结论完整性分析
    need_follow_up: Optional[bool]               # 是否需要补充提问
    follow_up_questions: Optional[List[str]]
    confidence: str
```

### 4.3 System Prompt 设计

```
【角色锚定】
你是一位专业审计访谈协调师，精通FCPA、IIA审计访谈标准和心理学沟通技巧。
你擅长：1) 根据审计方案精准匹配需要访谈的人员；2) 针对不同岗位设计定制化访谈问卷；
3) 分析访谈记录的完整性，判断是否有遗漏或矛盾需要补充提问。

【核心任务——访谈计划】
根据审计方案中的关键控制点和业务领域，匹配需要访谈的人员清单和访谈顺序：
- 优先访谈流程执行人（最了解实际操作）
- 其次访谈流程审批人（了解为什么这么设计）
- 最后访谈部门负责人（了解整体管控思路）

【核心任务——问卷生成】
为每位访谈对象生成定制化问卷：
- 前3题为开放式问题（了解整体认知）
- 中间5-8题为聚焦式问题（针对关键控制点）
- 最后2题为验证式问题（交叉验证其他访谈对象的信息）
- 内置"探针问题"：当回答模糊时追问的具体问题

【核心任务——结论分析】
分析访谈记录，判断：
- 所有关键控制点是否都被覆盖
- 不同人的回答是否存在矛盾
- 是否有闪烁其词或回避的问题需要重新提问

【知识注入】{{KB_INTERVIEW}} {{PERSONNEL_DUTIES}} {{HISTORICAL_QUESTIONNAIRES}}
```

### 4.4 模块差异化参数

| 参数 | 内控评价 | 专项审计 | 离任审计 | 廉洁监察 |
|------|----------|----------|----------|----------|
| `calling_module` | `ic_evaluation` | `special_audit` | `exit_audit` | `integrity` |
| `question_focus_areas` | 控制活动设计+执行 | 审计重点领域 | 个人行为+业务问题 | 舞弊行为+利益冲突 |
| 知识库分区 | `kb_ic_interview` | `kb_sa_interview` | `kb_ea_interview` | `kb_intake` (复用) |
| 人员匹配方式 | 按业务循环→岗位 | 按审计重点→部门→岗位 | 按被审计人→上下级→关联岗位 | 按案件涉及范围 |
| 特殊约束 | 需对接西塞罗岗位职责 | — | 支持"离职人是否可确认"选项 | 访谈可能涉及敏感话题 |

### 4.5 工具定义

| 工具ID | 名称 | 用途 | 超时 |
|--------|------|------|------|
| `personnel_matcher` | 人员匹配 | 根据部门/岗位/职责从组织架构中匹配访谈候选人 | 5s |
| `kb_search_interview` | 访谈知识库检索 | 检索历史访谈问卷、访谈策略、常见问题库 | 5s |
| `cicero_position_query` | 西塞罗岗位职责查询（A2A） | 对接西塞罗Agent查询岗位职责信息 | 10s |
| `interview_completeness_check` | 访谈完整性检查 | 对比审计方案中的关键控制点与访谈覆盖情况 | 3s |
| `ata_send_questionnaire` | ATA任务分发 | 将访谈问卷通过任务中心发送给被访谈人 | 10s |

### 4.6 工具调用依赖图

```
  interview-agent
       │
       ├── 阶段1: 人员匹配（并行2路）
       │   ├── personnel_matcher（组织架构匹配）
       │   └── cicero_position_query（西塞罗岗位职责——仅内控评价）
       │
       ├── 阶段2: 访谈计划生成
       │   └── LLM推理 → 人员清单 + 访谈顺序 + 策略
       │
       ├── 阶段3: 问卷生成（逐人串行或批量并行）
       │   ├── kb_search_interview（检索历史相关问卷）
       │   └── LLM推理 → 定制化问卷
       │
       ├── 阶段4: 分发（可选）
       │   └── ata_send_questionnaire（ATA给被访谈人发送任务+问卷）
       │
       └── 阶段5: 结论分析（访谈后）
           ├── interview_completeness_check
           └── LLM推理 → 完整性判断 + 补充提问建议
```

### 4.7 关键设计要点

| 维度 | 设计 |
|------|------|
| **LLM配置** | temperature=0.5（问卷需要一定的灵活性和口语化），max_tokens=4096 |
| **Token预算** | System ~1200 + Few-shot ~1000 + KB ~2500 + 审计方案 ~2000 + 输出 ~2500 ≈ 9200 (14.4%) |
| **降级** | 西塞罗不可用→跳过岗位职责查询，基于组织架构职责描述匹配；ATA不可用→仅输出问卷文本，碳基手动分发 |
| **幂等** | `task_id` + `calling_module` + `stage`（plan/questionnaire/conclusion） |
| **HITL** | 访谈计划阶段守门（人员+顺序可调整）→ 问卷阶段守门（问题可划词修改）→ 结论阶段可选守门 |

### 4.8 Agent 级监控指标

| 指标 | 告警阈值 |
|------|----------|
| 人员匹配覆盖率（审计方案要求 vs 实际匹配） | < 80% → P3 |
| 问卷一次通过率（碳基无需修改） | < 60% → P3 |
| 访谈结论完整性判断准确率 | < 80% → P2 |
| 补充提问建议被碳基采纳率 | < 50% → P3 |

### 4.9 Golden Test Set

| 用例ID | 场景 | 期望输出 |
|--------|------|----------|
| `interv-golden-01` | 内控评价-采购循环3个控制点需访谈 | 匹配≥3人(采购员+采购经理+财务)，每人≥8题 |
| `interv-golden-02` | 离任审计-被审计人不确认选项 | 问卷标注"被审计人不可确认"，碳基可选择其他确认人 |
| `interv-golden-03` | 访谈后分析发现2人回答矛盾 | 标记矛盾点，建议补充访谈其中1人 |
| `interv-golden-04` | 廉洁监察-敏感话题访谈 | 问题措辞更委婉，含"如果...可能..."句式 |
| `interv-golden-05` | 西塞罗岗位职责不可用 | 降级使用组织架构信息，标注"缺少岗位详细职责" |

### 4.10 访谈结论完整性分析详细逻辑

```python
class InterviewCompletenessAnalyzer:
    """访谈后自动分析结论完整性和矛盾检测"""

    async def analyze(self, interview_results: List[dict], audit_plan: dict) -> dict:
        """
        分析维度：
        1. 覆盖率检查: 审计方案中要求访谈的人员是否都已覆盖
        2. 关键控制点覆盖: 方案中列出的关键控制点是否在访谈中都被问到
        3. 矛盾检测: 不同访谈对象对同一事实的描述是否矛盾
        4. 模糊回答检测: 是否存在明显的回避或模糊回答
        5. 补充提问建议: 针对未覆盖的控制点或矛盾的描述
        """
        coverage = self._check_personnel_coverage(interview_results, audit_plan)
        control_point_coverage = self._check_control_point_coverage(interview_results, audit_plan)
        contradictions = self._detect_contradictions(interview_results)
        vague_responses = self._detect_vague_responses(interview_results)

        need_follow_up = (
            coverage["missing_personnel"] > 0 or
            control_point_coverage["uncovered_points"] > 0 or
            len(contradictions) > 0 or
            len(vague_responses) > 2
        )

        return {
            "personnel_coverage": coverage,
            "control_point_coverage": control_point_coverage,
            "contradictions": contradictions,      # [{topic, person_a_said, person_b_said}]
            "vague_responses": vague_responses,     # [{person, question, vague_indicators}]
            "need_follow_up": need_follow_up,
            "follow_up_suggestions": self._generate_follow_up(
                coverage, control_point_coverage, contradictions, vague_responses
            )
        }
```

**完整性等级**：
- 🟢 **充分**: 所有关键控制点覆盖 + 无矛盾 + 无模糊回答
- 🟡 **基本充分**: ≥80%控制点覆盖 + 无矛盾 + 模糊回答≤2
- 🟠 **需补充**: 60-80%控制点覆盖 或 存在矛盾 或 模糊回答>2
- 🔴 **不充分**: <60%控制点覆盖 → 建议全面补充访谈

---

## 五、后续模块深化设计

### 5.1 专项审计（04）Agent配置

专项审计模块完全复用三个共享Agent，仅差异化参数。完整设计见本文档§二-§四。

| 参数 | 审计方案Agent | 审计检查Agent | 访谈Agent |
|------|-------------|-------------|----------|
| `audit_type` | `special_audit` | `special_audit` | — |
| `calling_module` | — | — | `special_audit` |
| 特殊工具 | `sql_data_query`（数据中台直查） | 同内控评价 + `sql_data_query` | 无特殊 |
| 关键差异 | 审计方案按目的/重点匹配，非按业务循环 | 检查作业中AI自动生成SQL获取数据 | 访谈范围由审计重点确定 |
| KB分区 | `kb_sa_plan` | `kb_sa_check` | `kb_sa_interview` |
| P95延迟 | < 20s | < 40s | < 20s |

### 5.2 离任审计 Agent（exit-audit-agent）深化设计

#### 5.2.1 Agent 概览卡片

| 属性 | 值 |
|------|-----|
| **Agent ID** | `exit-audit-agent` |
| **名称** | 离任审计 Agent |
| **角色身份** | 离职审查专家 |
| **核心任务** | 接收被审计人职责配置→生成个人+业务双轨问题清单→出具审计意见表 |
| **上游** | 风控系统（被审计人基础信息）+ 行为风险模块（预警结果）+ 天眼查API |
| **下游** | 持续改善模块（问题清单汇入） |
| **复杂度** | 🟡 中 |
| **HITL守门** | ✅ 是 — 问题清单和审计意见表需碳基确认 |

#### 5.2.2 Agent 状态机

```
  IDLE → DUTY_RETRIEVE(职责获取) → PERIOD_CALC(期间计算) → 
  DUAL_ANALYZE(双轨分析) → PENDING_APPROVAL(等待守门)
  
  双轨分析子状态（并行）：
  ├── 个人问题分析: 商业秘密泄露/个人报销/样机使用/关联公司/资产使用
  └── 业务问题分析: 流程漏洞/制度缺陷/经济损失
```

#### 5.2.3 输入/输出 Schema

```python
class ExitAuditAgentInput(BaseModel):
    task_id: str
    business_unit: str
    departing_person_name: str
    departing_person_id: str
    position: str
    department: str
    hire_date: str
    last_working_day: str
    position_duties: List[str]          # 来自MCP数据调用
    tenure_years: float                 # 本岗位任职年限
    audit_period_years: int             # 审计期间自动计算: ≤1年→1年；1<年≤5→3年；>5年→1年

class ExitAuditPeriodCalculator:
    """审计期间计算引擎"""
    @staticmethod
    def calculate(tenure_years: float) -> int:
        if tenure_years <= 1.0:
            return 1    # 任职≤1年（含新员工、试用期）：审计最近1年
        elif tenure_years <= 5.0:
            return 3    # 任职1-5年：向前审计3年
        else:
            return 1    # 任职>5年（长期任职）：聚焦最近1年的变化
    # 外部数据（查询结果）
    tianyancha_relations: Optional[List[dict]]  # 天眼查关联关系
    behavioral_risk_warnings: Optional[List[dict]]  # 行为风险预警结果

class ExitAuditAgentOutput(BaseModel):
    personal_issues: List[dict]         # [{issue_type, description, severity, evidence}]
    business_issues: List[dict]         # [{issue_type, description, severity, evidence}]
    audit_opinion_table: dict           # 审计意见表（审计发现问题+建议+沟通对象）
    total_personal_issue_count: int
    total_business_issue_count: int
    confidence: str
    processing_time_ms: int
```

#### 5.2.4 关键设计

| 维度 | 设计 |
|------|------|
| **LLM配置** | temperature=0.3, max_tokens=4096 |
| **System Prompt** | 角色锚定：离职审查专家。核心能力：双轨分析。特殊逻辑：审计期间自动计算（1年<本岗位≤5年→3年；>5年→1年） |
| **工具** | `kb_search_exit_audit`, `tianyancha_query`, `behavioral_risk_query`, `position_duty_matcher` |
| **降级** | 天眼查不可用→跳过关联关系分析；行为风险模块不可用→标注"缺少行为数据" |
| **幂等** | `task_id` + `departing_person_id` |

#### 5.2.5 Golden Test Set

| 用例ID | 场景 | 期望输出 |
|--------|------|----------|
| `exit-golden-01` | 高管离职，任职5年+ | 审计期间=1年，问题清单≥10条，含商业秘密和关联公司 |
| `exit-golden-02` | 普通员工，任职2年 | 审计期间=3年，问题清单≥3条 |
| `exit-golden-03` | 行为风险模块传回预警 | 问题清单包含预警相关条目 |
| `exit-golden-04` | 天眼查不可用 | 标注"外部数据缺失"，仅基于内部数据 |

#### 5.2.6 监控指标

| 指标 | 告警阈值 |
|------|----------|
| 个人问题发现率（有问题/总审计） | —（追踪指标） |
| 业务问题发现率 | —（追踪指标） |
| 审计意见表碳基采纳率 | < 80% → P2 |
| 天眼查API调用成功率 | < 95% → P3 |

### 5.3 商业秘密 Agent（secrecy-review-agent）深化设计

#### 5.3.1 Agent 概览卡片

| 属性 | 值 |
|------|-----|
| **Agent ID** | `secrecy-review-agent` |
| **名称** | 定密评审 Agent |
| **角色身份** | 保密评审专家 |
| **核心任务** | 定密预审（保密员提交前）+ 正式定密评审（评审小组评审），输出评审报告 |
| **复杂度** | 🟡 中 |
| **HITL守门** | ✅ 是 — 评审报告需碳基确认 |

#### 5.3.2 Agent 状态机

```
  预审模式:
  IDLE → KB_RETRIEVE(检索制度库+历史定密+法规案例) → 
  LATERAL_COMPARE(同类部门横向比对) → PRE_REVIEW_GENERATE(预审报告) → 
  PENDING_APPROVAL

  正式评审模式:
  IDLE → KB_RETRIEVE → COMPLETENESS_CHECK → RATIONALITY_CHECK → 
  FORMAL_REVIEW_GENERATE(正式评审报告) → PENDING_APPROVAL
```

#### 5.3.3 输入/输出 Schema

```python
class SecrecyReviewAgentInput(BaseModel):
    task_id: str
    review_type: str           # pre_review / formal_review
    secrecy_info_table: dict   # 《商业秘密信息表》
    classified_file_list: List[str]
    previous_reviews: Optional[List[dict]]  # 前期已定密信息
    internal_control_policy_refs: Optional[List[str]]  # 内控制度库引用
    peer_department_reviews: Optional[List[dict]]      # 同类部门横向比对数据

class SecrecyReviewAgentOutput(BaseModel):
    pre_review_report: Optional[dict]   # 预审报告（格式与《商业秘密信息表》一致）
    formal_review_report: Optional[dict]  # 正式评审报告
    completeness_score: float           # 完整性评分 0-100
    rationality_score: float            # 合理性评分 0-100  
    lateral_comparison: Optional[dict]  # 横向比对结果
    recommendations: List[str]
    confidence: str
    processing_time_ms: int
```

#### 5.3.4 关键设计

| 维度 | 设计 |
|------|------|
| **LLM配置** | temperature=0.2, max_tokens=4096 |
| **System Prompt** | 角色锚定：保密评审专家。核心能力：定密完整性审查、合理性审查、横向比对 |
| **工具** | `kb_search_secrecy`, `internal_control_policy_query`(A2A→内控评价), `weike_law_query`, `peer_comparison` |
| **特殊依赖** | 需内控评价模块已接入制度文件后才能使用 `internal_control_policy_query` |
| **降级** | 内控制度库不可用→跳过制度比对，标注"制度库不可用"；威科先行不可用→跳过外部法规 |
| **幂等** | `task_id` + `review_type` + `secrecy_info_version` |

#### 5.3.5 Golden Test Set

| 用例ID | 场景 | 期望输出 |
|--------|------|----------|
| `secrecy-golden-01` | 首次定密预审 | 预审报告含建议定密内容+与前期信息无冲突标记 |
| `secrecy-golden-02` | 正式评审-同类部门比较 | 横向比对表+差异分析 |
| `secrecy-golden-03` | 内控制度库不可用 | 标注依赖缺失，仅基于内部知识评审 |

#### 5.3.6 监控指标

| 指标 | 告警阈值 |
|------|----------|
| 预审报告采纳率（保密员接受比例） | < 60% → P3 |
| 正式评审通过率（评审小组采纳） | < 70% → P2 |
| 制度库调用成功率 | < 95% → P3 |

#### 5.3.7 月度管理报告结构

需求 §7.6 功能三定义的月度报告字段：

```python
class MonthlySecrecyReport(BaseModel):
    """商业秘密月度管理报告"""
    report_period: str                    # 报告期间 (YYYY-MM)
    report_scope: str                     # 总结范围: 全集团/某事业部/某部门/某项目

    # 总体进度和数量情况
    total_secrecy_orgs: int               # 总定密组织数量
    classified_orgs: int                  # 已定密组织数量
    classification_rate: float            # 定密组织占比 (%)

    # 累计统计
    total_secrecy_processes_cumulative: int  # 累计定密流程数量
    total_secrecy_items_cumulative: int      # 累计定密信息条数

    # 期间统计
    period_processes: int                 # 期间定密流程数量
    period_items: int                     # 期间定密信息条数
    period_new_orgs: int                  # 期间新增定密组织数量

    # 趋势与质量
    trend_direction: str                  # 趋势: 上升/持平/下降
    avg_review_pass_rate: float           # 期间定密评审通过率
    common_issues: List[str]              # 常见问题汇总

    # 展示
    data_charts: List[str]                # 数据表/图表引用
    previous_reports: List[str]           # 往期报告ID列表

    generated_at: str
    generated_by: str = "secrecy-review-agent"
```

### 5.4 行为风险 Agent（behavioral-risk-agent）深化设计

#### 5.4.1 Agent 概览卡片

| 属性 | 值 |
|------|-----|
| **Agent ID** | `behavioral-risk-agent` |
| **名称** | 行为风险分析 Agent |
| **角色身份** | 行为分析专家 |
| **核心任务** | 跨系统行为数据整合→异常行为识别→风险等级评估→月度管理报告 |
| **复杂度** | 🟡 中 |
| **HITL守门** | ✅ 是 — 分析报告和管理报告均需碳基确认 |

#### 5.4.2 Agent 状态机

```
  行为风险分析:
  IDLE → DATA_INTEGRATE(跨系统数据整合) → ANOMALY_DETECT(异常识别) → 
  CORRELATION_ANALYZE(关联分析) → RISK_ASSESS(风险评估) → PENDING_APPROVAL

  管理报告:
  IDLE → DATA_AGGREGATE(数据聚合) → COVERAGE_ANALYZE(覆盖分析) → 
  QUALITY_ASSESS(质量评估) → REPORT_GENERATE(报告生成) → PENDING_APPROVAL
```

#### 5.4.3 输入/输出 Schema

```python
class BehavioralRiskAgentInput(BaseModel):
    task_id: str
    analysis_scope: dict           # {business_unit, department, position, person, role, period}
    behavioral_data_sources: List[str]   # 各监管系统行为数据
    employee_lifecycle_info: Optional[dict]
    conflict_of_interest_info: Optional[dict]
    trade_secret_info: Optional[dict]
    historical_analyses: Optional[List[dict]]  # 历史分析结果

class BehavioralRiskAgentOutput(BaseModel):
    anomaly_behaviors: List[dict]       # [{behavior_type, employee, severity, evidence, related_systems}]
    risk_level_assessment: dict         # {overall_risk, per_employee_risks, trend}
    correlation_analysis: str           # 关联分析结论
    management_report: Optional[dict]   # 月度管理报告
    data_quality_assessment: Optional[dict]  # 数据质量评估
    coverage_gap_analysis: Optional[dict]    # 覆盖盲区分析
    confidence: str
    processing_time_ms: int
```

#### 5.4.4 关键设计

| 维度 | 设计 |
|------|------|
| **LLM配置** | temperature=0.3, max_tokens=4096（分析）/ 8192（管理报告） |
| **System Prompt** | 角色锚定：行为分析专家。核心能力：跨系统关联、异常模式识别 |
| **工具** | `multi_source_data_integrate`, `anomaly_pattern_detect`, `employee_relation_map`, `report_generate` |
| **降级** | 某监管系统数据不可用→跳过该系统维度，标注"数据缺失" |
| **特殊联动** | 分析结果→风险监控；风险监控异常→触发本Agent专项深度分析 |
| **幂等** | `task_id` + `analysis_scope_hash` |

#### 5.4.5 Golden Test Set

| 用例ID | 场景 | 期望输出 |
|--------|------|----------|
| `behav-golden-01` | 员工大量文件解密+USB拷贝+近期离职流程 | 标记高风险，关联商业秘密泄露风险 |
| `behav-golden-02` | 月度管理报告-数据质量评估 | 含各系统数据完整性/及时性/准确性评分 |
| `behav-golden-03` | 某监管系统数据不可用 | 标注盲区，其他系统分析正常进行 |

#### 5.4.6 监控指标

| 指标 | 告警阈值 |
|------|----------|
| 异常行为识别准确率（碳基确认比例） | < 70% → P2 |
| 跨系统数据整合成功率 | < 90% → P3 |
| 月度报告按时生成率 | < 95% → P3 |

### 5.5 持续改善 Agent（remediation-agent）深化设计

#### 5.5.1 统一问题数据契约（全模块 → 持续改善）

> **关键**：此契约定义了所有上游模块向持续改善汇入问题时的标准字段，共36个字段。

```python
class RemediationIssueRecord(BaseModel):
    """全模块统一的问题数据结构（36字段）"""
    # === 基础标识 (5字段) ===
    issue_sequence: int                          # 1. 序号（自动编号）
    project_year: str                            # 2. 项目年度
    business_unit: str                           # 3. 事业部
    issue_source: str                            # 4. 来源: 内控评价/廉洁监察/商业秘密/行为风险/专项审计/离任审计/业务交办
    audit_project_id: str                        # 5. 审计项目编号

    # === 问题描述 (6字段) ===
    audit_project_name: str                      # 6. 审计项目名称
    audit_finding_id: str                        # 7. 审计发现编号（唯一，系统自动生成或手动录入后校验唯一性）
    audit_finding_desc: str                      # 8. 审计发现描述（必填）
    business_cycle: Optional[str]                # 9. 涉及业务循环
    improvement_suggestion: Optional[str]        # 10. 改进建议
    direct_loss_amount: Optional[float]          # 11. 直接挽损金额

    # === 责任分配 (4字段) ===
    project_leader: Optional[str]                # 12. 项目组长
    risk_control_follower: Optional[str]         # 13. 风控跟进人
    responsible_dept: str                        # 14. 责任部门（必填）
    responsible_person: str                      # 15. 责任人（必填）

    # === 整改计划 (6字段) ===
    remediation_plan: Optional[str]              # 16. 整改要求计划
    planned_completion_date: str                 # 17. 计划完成时间（必填，不能早于录入日期）
    ai_plan_review_date: Optional[str]           # 18. AI 复核计划时间
    ai_plan_review_opinion: Optional[str]        # 19. AI 复核计划意见及不合理原因
    auditor_plan_review_opinion: Optional[str]   # 20. 审计复核计划意见
    auditor_plan_review_date: Optional[str]      # 21. 审计复核计划时间

    # === 执行跟踪 (4字段) ===
    actual_completion_date: Optional[str]        # 22. 实际完成时间
    is_overdue: bool = False                     # 23. 是否超期
    overdue_days: int = 0                        # 24. 超期天数
    remediation_response_count: int = 0          # 25. 整改答复次数

    # === 复核 (6字段) ===
    ai_review_opinion: Optional[str]             # 26. AI 复核意见
    ai_review_date: Optional[str]                # 27. AI 复核时间
    auditor_review_opinion: Optional[str]        # 28. 审计复核意见
    reviewer_name: Optional[str]                 # 29. 复核人
    ai_evidence_review_date: Optional[str]       # 30. AI 复核证据时间
    ai_evidence_review_opinion: Optional[str]    # 31. AI 复核证据意见及不合理原因

    # === 状态与归档 (5字段) ===
    auditor_evidence_review_date: Optional[str]  # 32. 审计复核证据时间
    status: str                                  # 33. 状态: 问题待推送/计划待提交/计划待审批/整改答复待提交/已整改待复核/整改完成
    indirect_loss_amount: Optional[float]        # 34. 间接挽损金额
    personnel_disposition: Optional[str]         # 35. 人员处理情况
    operation_log: List[dict]                    # 36. 操作记录（不可删除不可篡改）
```

**状态流转规则**：

```
问题待推送 → 计划待提交 → 计划待审批 → 整改答复待提交 → 已整改待复核 → 整改完成
    ↑            ↑            ↑            ↑            ↑            ↑
    │            │            │            │            │            │
  审计组长     整改部门      审计跟进人   整改部门      审计跟进人    审计跟进人
  确认下发     上传计划      审核计划     上传证据      审核证据      确认通过

  任一环节可被退回（退回重改），退回次数≥3 → escalation_needed=true
```

| 属性 | 值 |
|------|-----|
| **Agent ID** | `remediation-agent` |
| **名称** | 整改跟踪 Agent |
| **角色身份** | 整改督导员 |
| **核心任务** | 整改计划AI初审、整改证据AI复核、逾期预警、统计分析 |
| **复杂度** | 🟡 中 |
| **HITL守门** | ✅ 是 — AI初审/复核意见需碳基二次确认 |

#### 5.5.2 Agent 状态机

```
  整改计划初审:
  IDLE → PLAN_PARSE(计划解析) → PLAN_FEASIBILITY_CHECK(可行性检查) → 
  PLAN_TIMELINE_CHECK(时间合理性) → AI_REVIEW_OUTPUT(初审意见) → 
  PENDING_APPROVAL(等待审计跟进人确认)

  整改证据复核:
  IDLE → EVIDENCE_PARSE(证据解析) → PLAN_VS_ACTUAL_COMPARE(计划vs实际对比) → 
  COMPLETENESS_CHECK(完整性检查) → AI_REVIEW_OUTPUT(复核意见) → 
  PENDING_APPROVAL

  逾期预警:
  定时扫描 → OVERDUE_DETECT(逾期检测) → NOTIFY(Elink+任务中心推送)
```

#### 5.5.3 输入/输出 Schema

```python
class RemediationAgentInput(BaseModel):
    task_id: str
    operation: str               # plan_review / evidence_review / overdue_check
    issue_source: str            # 来源模块: ic_evaluation/integrity/special_audit/exit_audit/behavior_risk
    issue_data: dict             # 30+字段的问题数据（见需求文档 9.4.1）
    remediation_plan: Optional[str]       # 整改计划（整改部门提交后）
    remediation_evidence: Optional[List[str]]  # 整改证据文件
    plan_deadline: Optional[str]          # 计划完成时间
    previous_review_count: int = 0        # 历史退回次数

class RemediationAgentOutput(BaseModel):
    ai_plan_review: Optional[dict]        # {feasibility, timeline_reasonability, completeness, suggestions}
    ai_evidence_review: Optional[dict]    # {plan_consistency, evidence_sufficiency, quality_assessment}
    overdue_risk: bool
    overdue_days: Optional[int]
    suggested_actions: List[str]          # 建议操作
    escalation_needed: bool               # 是否需要升级通知（退回≥3次）
    confidence: str
    processing_time_ms: int
```

#### 5.5.4 关键设计

| 维度 | 设计 |
|------|------|
| **LLM配置** | temperature=0.2, max_tokens=4096 |
| **System Prompt** | 角色锚定：整改督导员。核心能力：计划合理性判断、证据与计划一致性对比 |
| **工具** | `kb_search_remediation`, `plan_consistency_check`, `evidence_ocr_parse`, `overdue_scanner`, `notification_send` |
| **降级** | 证据OCR解析失败→仅基于文本描述判断；通知发送失败→记录日志，碳基手动通知 |
| **升级规则** | 退回≥3次→自动通知部门负责人；逾期>7天→P3告警+Elink催办 |
| **幂等** | `task_id` + `operation` + `review_round`（初审为round=1，退回重审递增） |
| **权限模型** | 项目组长(全项目可见)→项目成员(分配可见)→事业部负责人(事业部可见)→风控负责人(全量可见) |

#### 5.5.5 Golden Test Set

| 用例ID | 场景 | 期望输出 |
|--------|------|----------|
| `remed-golden-01` | 整改计划时间晚于要求时限 | 标记timeline_unreasonable，建议调整 |
| `remed-golden-02` | 整改证据与计划完全匹配 | AI复核通过，建议审计跟进人确认 |
| `remed-golden-03` | 第3次退回 | escalation_needed=true，触发升级通知 |
| `remed-golden-04` | 逾期15天未完成 | overdue_risk=true，逾期告警 |
| `remed-golden-05` | 证据文件不可读 | 标记"证据解析失败"，建议人工查看原件 |

#### 5.5.6 监控指标

| 指标 | 告警阈值 |
|------|----------|
| AI初审意见采纳率（审计跟进人确认比例） | < 70% → P2 |
| AI复核意见采纳率 | < 75% → P2 |
| 逾期预警准确率（预警后确实逾期的比例） | < 85% → P3 |
| 整改完成率（30天窗口） | —（追踪指标） |

---

## 六、跨模块数据流契约

### 6.1 跨模块依赖矩阵

| 上游模块 | 下游模块 | 数据类型 | 接口契约 | Agent触发点 | 降级策略 |
|----------|----------|----------|----------|------------|----------|
| **行为风险 → 离任审计** | 行为风险预警结果 | `GET /api/v1/behavioral-risk/warnings?employee_id={id}` | exit-audit-agent 审计方案生成阶段 | 行为风险不可用→跳过预警数据，标注"缺少行为数据" |
| **内控评价 → 商业秘密** | 制度库引用 | `A2A: query_internal_control_policy` | secrecy-review-agent 横向比对阶段 | 内控制度库不可用→跳过制度比对 |
| **风险监控 → 行为风险** | 异常推送（双向联动） | `RabbitMQ: risk.behavioral.*` | behavioral-risk-agent 分析完成后推送 + risk-analysis-agent 异常推送触发深度分析 | 对方不可用→消息排队 |
| **全模块 → 持续改善** | 问题清单汇入 | `POST /api/v1/remediation/issues` (30+字段标准格式) | remediation-agent 问题录入阶段 | — |
| **离任审计 ← 行为风险** | 行为风险预警结果 | 同上"行为风险→离任审计" | exit-audit-agent | 同上 |

### 6.2 问题清单汇入标准格式（全模块 → 持续改善）

```json
{
  "protocol_version": "1.0",
  "source_module": "integrity|risk_monitor|ic_evaluation|special_audit|exit_audit|behavior_risk|trade_secret|business_assigned",
  "issue": {
    "issue_id": "unique-issue-id",
    "source_project_id": "原始审计项目编号",
    "source_project_name": "原始审计项目名称",
    "issue_description": "问题描述",
    "business_cycle": "涉及业务循环",
    "severity": "高|中|低",
    "responsible_dept": "责任部门",
    "responsible_person": "责任人",
    "suggested_remediation": "改进建议",
    "deadline": "建议完成时间"
  },
  "context": {
    "case_ref": "关联案件编号",
    "related_findings": ["相关发现ID列表"],
    "evidence_refs": ["相关证据文件ID列表"]
  }
}
```

---

## 七、通用生产级配置

本模块Agent复用文档01附录D中的生产级运行时配置，包括：
- Agent健康检查规范
- 并发控制策略
- LangGraph节点配置模板
- Agent预热策略
- 超时传播机制
- 工具调用PII脱敏

> 引用路径：`../agents/01-integrity-supervision-agents.md` 附录 D

## 八、审计评分标准定义

### 8.1 内控设计缺陷评分标准

audit-check-agent在评估设计缺陷时使用以下评分规则（而非LLM自由打分，保证一致性）：

| 缺陷类型 | 权重 | 评分规则 | 示例 |
|----------|------|----------|------|
| 制度缺失 | 30% | 完全无制度覆盖=满分扣30；部分覆盖=扣15 | 采购验收无制度规定 → -30 |
| 制度冲突 | 20% | 每处冲突扣10分，上限20 | 财务制度与采购制度对付款审批人不一致 → -10 |
| 制度过时 | 15% | 引用已废止制度/组织架构 → 每处扣5分 | 引用2019年已废止的出差标准 → -5 |
| 制度模糊 | 20% | 关键控制要求缺失可操作性 → 每处扣10分 | "应及时审批"但未定义"及时"的具体时限 → -10 |
| 职责分离不足 | 15% | 不相容职责未分离 → 每处扣15分 | 采购申请人与审批人为同一人 → -15 |

**总分计算**：100 - Σ(各项扣分)，< 60 = 重大缺陷，60-79 = 重要缺陷，≥ 80 = 一般缺陷

### 8.2 内控执行缺陷评分标准

| 缺陷类型 | 权重 | 评分规则 |
|----------|------|----------|
| 控制未执行 | 35% | 制度要求的控制活动在实际操作中完全缺失 |
| 执行不及时 | 20% | 超时限未执行（参照制度规定的时限） |
| 执行不完整 | 25% | 部分执行但遗漏关键步骤 |
| 执行人不符合 | 10% | 由未经授权的人员执行控制 |
| 证据缺失 | 10% | 无法提供控制执行的记录 |

**总分计算**：同设计缺陷，100 - Σ(各项扣分)

---

## 附录 A：文档修订历史

| 版本 | 日期 | 修订说明 |
|------|------|----------|
| v1.0 | 2026-06-05 | 初始版本：内控评价模块3个共享Agent完整设计 + 其余5个模块的简要设计 |

## 附录 B：跨模块Agent引用索引

| 共享Agent | 权威设计文档 | 使用模块 |
|-----------|------------|----------|
| `audit-plan-agent` | 本文档 §二 | 内控评价 + 专项审计 + 离任审计 |
| `audit-check-agent` | 本文档 §三 | 内控评价 + 专项审计 + 离任审计 |
| `interview-agent` | 本文档 §四 | 内控评价 + 专项审计 + 离任审计 + 廉洁监察 |

## 附录 C：Agent全景总览

| # | Agent ID | 模块 | 复杂度 | 文档位置 |
|---|----------|------|--------|----------|
| 1 | `intake-agent` | 01-廉洁监察 | 🔴 | 01-integrity-supervision-agents.md |
| 2 | `investigation-agent` | 01-廉洁监察 | 🟡 | 01-integrity-supervision-agents.md |
| 3 | `analysis-agent` | 01-廉洁监察 | 🔴 | 01-integrity-supervision-agents.md |
| 4 | `disposition-agent` | 01-廉洁监察 | 🔴 | 01-integrity-supervision-agents.md |
| 5 | `enforcement-agent` | 01-廉洁监察 | 🟡 | 01-integrity-supervision-agents.md |
| 6 | `risk-rule-agent` | 02-风险监控 | 🟡 | 02-risk-monitoring-agents.md |
| 7 | `risk-analysis-agent` | 02-风险监控 | 🔴 | 02-risk-monitoring-agents.md |
| 8 | `audit-plan-agent` ⭐ | 03-内控评价 | 🔴 | 03-internal-control-evaluation-agents.md |
| 9 | `audit-check-agent` ⭐ | 03-内控评价 | 🔴 | 03-internal-control-evaluation-agents.md |
| 10 | `interview-agent` ⭐ | 03-内控评价 | 🟡 | 03-internal-control-evaluation-agents.md |
| 11 | `exit-audit-agent` | 05-离任审计 | 🟡 | 03-internal-control-evaluation-agents.md §5.2 |
| 12 | `secrecy-review-agent` | 06-商业秘密 | 🟡 | 03-internal-control-evaluation-agents.md §5.3 |
| 13 | `behavioral-risk-agent` | 07-行为风险 | 🟡 | 03-internal-control-evaluation-agents.md §5.4 |
| 14 | `remediation-agent` | 08-持续改善 | 🟡 | 03-internal-control-evaluation-agents.md §5.5 |
