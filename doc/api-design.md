# 赫尔墨斯（Hermes）接口设计文档 v1.0

---

## 一、接口设计规范

### 1.1 URL 规范

| 规则 | 说明 |
|------|------|
| 基础路径 | `/api/v1` |
| 资源命名 | 小写复数名词，如 `/cases`、`/users` |
| 嵌套资源 | 不超过两层，如 `/cases/{case_id}/documents` |
| 查询参数 | 蛇形命名，如 `?page_size=20` |
| 版本策略 | URL 路径版本，`/api/v1`、`/api/v2` |

### 1.2 请求格式

- **Content-Type**: `application/json`（默认）；文件上传使用 `multipart/form-data`
- **字符编码**: UTF-8
- **时间格式**: ISO 8601（`2026-05-19T10:30:00Z`）
- **认证**: `Authorization: Bearer <access_token>`（见第二章）

### 1.3 统一响应格式

**成功响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

**分页响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [ ... ],
    "total": 156,
    "page": 1,
    "page_size": 20
  }
}
```

**错误响应**:
```json
{
  "code": 40401,
  "message": "案件不存在",
  "detail": "case_id=abc-123 not found"
}
```

### 1.4 分页规范

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码，从 1 开始 |
| `page_size` | int | 20 | 每页条数，最大 100 |

分页信息统一包含在 `data` 根节点下，字段为 `items`、`total`、`page`、`page_size`。

### 1.5 版本管理

- 当前版本：`v1`
- 版本升级规则：新增不兼容字段或删除字段时递增大版本；新增兼容字段不增加版本号
- 废弃字段标记：在响应中添加 `_deprecated` 前缀，旧版本保留 2 个版本后移除

### 1.6 安全要求（等保二级）

- 所有请求记录到 `audit_log`（含操作人、IP、User-Agent、操作内容）
- 敏感字段（手机号、邮箱、身份证号）返回时脱敏（`138****1234`）
- DELETE 操作改为软删除（`is_deleted = true`）
- 文件上传限 50MB，API 速率限制 100 req/min per user

---

## 二、认证与授权

### 2.1 认证流程

系统采用 **JWT Bearer Token** 双令牌机制：

```
用户登录 → 获得 access_token（8小时有效）+ refresh_token（7天有效）
     ↓
请求携带 Authorization: Bearer <access_token>
     ↓
access_token 过期 → 调用 /auth/refresh 换取新 access_token
     ↓
refresh_token 过期 → 重新登录
```

### 2.2 角色权限（RBAC）

| 角色 | 权限范围 | 说明 |
|------|----------|------|
| `group` | 所有数据 | 集团角色，可查看全部事业部数据 |
| `ecovacs` | 科沃斯事业部数据 | 仅可查看 `client=ecovacs` 的数据 |
| `tineco` | 添可事业部数据 | 仅可查看 `client=tineco` 的数据 |

行级过滤在应用层实现，所有数据查询按登录角色自动过滤；手动创建资源时只能创建所属角色对应事业部的数据。

### 2.3 认证接口

**POST /api/v1/auth/login** — 用户登录

请求体：
```json
{
  "username": "zhangsan",
  "password": "******"
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "access_token": "eyJhbG...",
    "refresh_token": "eyJhbG...",
    "token_type": "bearer",
    "expires_in": 28800,
    "user_info": {
      "id": "u-001",
      "username": "zhangsan",
      "role": "ecovacs",
      "display_name": "张三"
    }
  }
}
```

**POST /api/v1/auth/refresh** — 刷新令牌

请求体：
```json
{
  "refresh_token": "eyJhbG..."
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "access_token": "eyJhbG...",
    "expires_in": 28800
  }
}
```

**POST /api/v1/auth/logout** — 登出（使 refresh_token 失效）

### 2.4 登录安全规则

- 连续登录失败 5 次，账号锁定 30 分钟
- 密码复杂度：至少 8 位，含大小写字母 + 数字 + 特殊字符
- 令牌在黑名单中立即失效（Redis 维护）

---

## 三、案件管理接口（廉洁监察）

> 路由前缀：`/api/v1/cases` | 标签：`cases`

### 3.1 创建案件

**POST /api/v1/cases**

请求体（系统抓取/人工录入双轨来源）：
```json
{
  "fraud_source": "manual",
  "client": "ecovacs",
  "reported_staff_names": ["李四", "王五"],
  "reported_supplier_names": ["XX供应商"],
  "reported_dealer_names": [],
  "fraud_event_detail": "涉嫌虚报差旅费用，涉及金额约5万元...",
  "proof": "2025年Q3差旅报销单与打卡记录不一致",
  "attachments": ["/uploads/proof_001.pdf"],
  "fraud_tel": "138****1234",
  "fraud_email": "whistle@example.com",
  "fraud_other_info": "匿名举报",
  "risk_control_case_id": "RC20260519001"
}
```

响应 `201`：
```json
{
  "code": 0,
  "data": {
    "id": "c-001",
    "task_id": "SD2026051901",
    "client": "ecovacs",
    "fraud_source": "manual",
    "current_stage": null,
    "status": "pending",
    "created_at": "2026-05-19T10:30:00Z"
  }
}
```

**task_id 生成规则**：来源缩写 + 年月日 + 顺序序号，来源缩写映射：手动=SD、公众号=GZ、邮箱=YX、智能体=ZN、电话=DH。

### 3.2 查询案件列表

**GET /api/v1/cases**

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `client` | string | 否 | 事业部筛选（非集团角色忽略此参数） |
| `source` | string | 否 | 来源筛选：manual/agent/phone/email/wechat |
| `status` | string | 否 | 状态筛选：pending/investigating/disposing/enforcing/closed/transferred |
| `stage` | string | 否 | 当前阶段筛选：intake/investigation/analysis/disposition/enforcement/post_report |
| `keyword` | string | 否 | 关键字搜索（task_id/案件名称模糊匹配） |
| `start_date` | string | 否 | 创建时间起（ISO 8601） |
| `end_date` | string | 否 | 创建时间止 |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20，最大 100 |

响应：
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "c-001",
        "task_id": "SD2026051901",
        "case_code": "EC-2026-0001",
        "client": "ecovacs",
        "fraud_source": "manual",
        "current_stage": "intake",
        "status": "investigating",
        "created_by": "zhangsan",
        "created_at": "2026-05-19T10:30:00Z",
        "updated_at": "2026-05-19T11:00:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

### 3.3 查询案件详情

**GET /api/v1/cases/{case_id}**

响应：
```json
{
  "code": 0,
  "data": {
    "id": "c-001",
    "task_id": "SD2026051901",
    "case_code": "EC-2026-0001",
    "client": "ecovacs",
    "fraud_source": "manual",
    "current_stage": "intake",
    "status": "investigating",
    "fraud_event_detail": "涉嫌虚报差旅费用...",
    "proof": "2025年Q3差旅报销单与打卡记录不一致",
    "attachments": ["/uploads/proof_001.pdf"],
    "fraud_tel": "138****1234",
    "risk_control_case_id": "RC20260519001",
    "workflow_state": { "intake_decision": { "should_investigate": true } },
    "langgraph_thread_id": "thread-c-001",
    "generated_documents": [
      { "id": "doc-001", "type": "intake_report", "name": "材料初判报告.docx", "format": "docx", "created_at": "2026-05-19T11:30:00Z" }
    ],
    "created_by": "zhangsan",
    "created_at": "2026-05-19T10:30:00Z",
    "updated_at": "2026-05-19T12:00:00Z"
  }
}
```

### 3.4 更新案件

**PUT /api/v1/cases/{case_id}**

> 仅允许更新未启动工作流的案件（`status=pending`）。支持划词调整场景下的部分字段更新。

### 3.5 删除案件

**DELETE /api/v1/cases/{case_id}**

> 软删除：设置 `is_deleted=true`，状态变为 `closed`。仅 `status=pending` 或 `status=closed` 的案件可删除。

---

## 四、工作流接口

> 路由前缀：`/api/v1/cases/{case_id}/workflow` | 标签：`workflow`

### 4.1 启动工作流

**POST /api/v1/cases/{case_id}/workflow/start**

启动 LangGraph 工作流，自动运行至第一个 `interrupt` 点（intake 节点），等待碳基守门。

响应 `202`：
```json
{
  "code": 0,
  "data": {
    "thread_id": "thread-c-001",
    "current_stage": "intake",
    "status": "pending_approval"
  }
}
```

### 4.2 恢复工作流

**POST /api/v1/cases/{case_id}/workflow/resume**

碳基守门完成后恢复工作流继续执行，或从意外中断处恢复。

请求体（可选，用于传递守门修改后的状态）：
```json
{
  "human_modifications": {
    "intake": { "should_investigate": true, "should_transfer": false }
  }
}
```

响应 `202`：
```json
{
  "code": 0,
  "data": {
    "thread_id": "thread-c-001",
    "current_stage": "investigation",
    "status": "running"
  }
}
```

### 4.3 查询工作流状态

**GET /api/v1/cases/{case_id}/workflow/status**

响应：
```json
{
  "code": 0,
  "data": {
    "current_stage": "intake",
    "stage_history": [],
    "pending_approval_stage": "intake",
    "error_info": null,
    "needs_human_intervention": false
  }
}
```

### 4.4 查询工作流历史

**GET /api/v1/cases/{case_id}/workflow/history**

响应：
```json
{
  "code": 0,
  "data": [
    {
      "stage_name": "intake",
      "status": "completed",
      "ai_output_type": "intake_report",
      "approval_result": "approved",
      "started_at": "2026-05-19T10:30:00Z",
      "completed_at": "2026-05-19T11:45:00Z"
    },
    {
      "stage_name": "investigation",
      "status": "processing",
      "started_at": "2026-05-19T11:46:00Z",
      "completed_at": null
    }
  ]
}
```

### 4.5 中断工作流

**POST /api/v1/cases/{case_id}/workflow/interrupt**

> 碳基主动中断当前阶段，可用于紧急暂停场景。需要 `group` 角色权限。

### 4.6 工作流阶段定义

工作流六个阶段的名称映射：

| 阶段 key | 阶段名称 | 对应需求文档 |
|----------|----------|-------------|
| `intake` | 材料初判与分流 | [4.1] 案件来源与初筛 |
| `investigation` | 调查方案生成 | [4.2] 智能调查方案筹备 |
| `analysis` | 多维分析与报告 | [4.3] 多样化分析及案件报告撰写 |
| `disposition` | 处置分流与处罚确定 | [4.4] 处置分流及处罚确定 |
| `enforcement` | 处罚执行与跟踪 | [4.5] 处罚执行及跟踪 |
| `post_report` | 报案后续协助 | [4.6] 报案后续协助 |

---

## 五、守门审批接口

> 路由前缀：`/api/v1/cases/{case_id}/approval` | 标签：`approval`

### 5.1 查询待守门内容

**GET /api/v1/cases/{case_id}/approval/pending**

响应：
```json
{
  "code": 0,
  "data": {
    "stage": "intake",
    "ai_output": {
      "should_investigate": true,
      "should_transfer": false,
      "recommended_handling": ["internal"],
      "summary": "根据举报材料分析，被举报人存在虚报差旅费嫌疑..."
    },
    "original_prompt": "请根据以下案件材料...",
    "knowledge_refs": [
      { "doc_id": "kb-001", "title": "公司差旅报销制度 v3.2", "relevance": 0.95 }
    ]
  }
}
```

### 5.2 提交守门决定

**POST /api/v1/cases/{case_id}/approval/{stage}**

请求体：
```json
{
  "action": "approved",
  "modifications": {},
  "comment": "AI分析结论合理，同意继续调查"
}
```

| action 值 | 含义 | 后续行为 |
|-----------|------|----------|
| `approved` | 批准 | 自动 resume 工作流进入下一阶段 |
| `rejected` | 驳回 | 重新执行当前阶段（LLM 接收驳回原因重新生成） |
| `modified` | 修改后通过 | 合并碳基修改内容后继续 |

响应：
```json
{
  "code": 0,
  "data": {
    "status": "approved",
    "next_stage": "investigation"
  }
}
```

### 5.3 划词调整（重新生成）

**POST /api/v1/cases/{case_id}/approval/{stage}/regenerate**

碳基选中 AI 输出的某段文本，提供修改指令，AI 仅重新生成指定部分。

请求体：
```json
{
  "selected_text": "建议对李四进行约谈...",
  "instruction": "改为建议进行书面函询，语气更正式"
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "regenerated_text": "建议向李四发出正式书面函询，要求其在3个工作日内就差旅报销差异作出说明。"
  }
}
```

### 5.4 查询守门历史

**GET /api/v1/cases/{case_id}/approval/history**

返回该案件所有阶段的守门记录（含操作人、操作时间、原始输出、修改内容、审批意见），不可篡改。

---

## 六、风险监控接口

> 路由前缀：`/api/v1/risk-monitor` | 标签：`risk-monitor`

### 6.1 风险规则管理

**POST /api/v1/risk-monitor/rules** — 创建风险规则

请求体：
```json
{
  "client": "ecovacs",
  "business_cycle": "采购付款循环",
  "scene_level1": "供应商管理",
  "scene_level2": "供应商准入",
  "scene_level3": "围串标风险",
  "sql_statement": "SELECT supplier_name, COUNT(*) FROM bid_records WHERE ...",
  "risk_level": "high",
  "threshold": 3,
  "monitor_frequency": "daily",
  "require_external_data": false,
  "channels": ["电商", "线下"],
  "business_formats": ["零售"],
  "departments": ["采购部"],
  "positions": ["采购经理"]
}
```

**GET /api/v1/risk-monitor/rules** — 查询风险规则列表

查询参数：`client`、`risk_level`、`business_cycle`、`is_active`、`page`、`page_size`

**GET /api/v1/risk-monitor/rules/{rule_id}** — 查询规则详情

**PUT /api/v1/risk-monitor/rules/{rule_id}** — 更新规则

**PATCH /api/v1/risk-monitor/rules/{rule_id}/status** — 启用/停用规则

请求体：
```json
{
  "is_active": false,
  "reason": "业务场景变更，该规则不再适用"
}
```

**POST /api/v1/risk-monitor/rules/{rule_id}/validate-sql** — 测试环境验证 SQL

触发 AI 在测试环境执行 SQL，返回是否可执行及预估结果行数。

**POST /api/v1/risk-monitor/rules/{rule_id}/iterate** — 规则迭代优化

请求体：
```json
{
  "optimization_type": "threshold_adjust",
  "new_threshold": 5,
  "reason": "误报率过高，提高阈值"
}
```

### 6.2 风险预警

**GET /api/v1/risk-monitor/alerts** — 查询风险预警列表

查询参数：`client`、`risk_level`、`risk_type`、`status`、`start_date`、`end_date`、`page`、`page_size`

响应：
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "alert-001",
        "rule_id": "rule-001",
        "rule_name": "围串标风险监控",
        "risk_level": "high",
        "risk_type": "舞弊风险",
        "analysis_subject": "XX供应商",
        "subject_type": "supplier",
        "alert_detail": "在过去30天内参与3次以上投标且中标率异常...",
        "involved_amount": 500000.00,
        "status": "pending_review",
        "created_at": "2026-05-19T08:00:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

**GET /api/v1/risk-monitor/alerts/{alert_id}** — 查询预警详情（含主体合并信息、涉及指标列表）

**POST /api/v1/risk-monitor/alerts/{alert_id}/review** — 人工复核

请求体：
```json
{
  "review_result": "confirmed",
  "comment": "确认为异常，建议推送廉洁监察立案",
  "corrected_risk_level": "critical"
}
```

### 6.3 风险分析报告

**GET /api/v1/risk-monitor/reports** — 查询风险分析报告列表

查询参数：`client`、`report_type`（daily/weekly/monthly）、`start_date`、`end_date`、`page`、`page_size`

**GET /api/v1/risk-monitor/reports/{report_id}** — 查询报告详情（含图表数据）

**POST /api/v1/risk-monitor/reports/generate** — 手动触发报告生成

请求体：
```json
{
  "report_type": "weekly",
  "period_start": "2026-05-12",
  "period_end": "2026-05-18",
  "client": "ecovacs"
}
```

### 6.4 风险推送记录

**GET /api/v1/risk-monitor/push-records** — 查询推送记录

查询参数：`alert_id`、`target_module`（cases/internal_control/trade_secret）、`status`、`page`、`page_size`

**POST /api/v1/risk-monitor/alerts/{alert_id}/push** — 手动推送风险至指定模块

请求体：
```json
{
  "target_module": "cases",
  "push_reason": "风险等级高，需立案调查"
}
```

### 6.5 处置结果回流

**POST /api/v1/risk-monitor/disposition-feedback** — 接收处置结果

接收来自廉洁监察、内控评价、商业秘密模块的处置结果反馈，用于指标迭代优化。

请求体：
```json
{
  "alert_id": "alert-001",
  "source_module": "cases",
  "disposition_status": "case_filed",
  "case_id": "c-001",
  "result_summary": "已立案调查"
}
```

---

## 七、内控评价接口

> 路由前缀：`/api/v1/internal-control` | 标签：`internal-control`

### 7.1 评价项目管理

**POST /api/v1/internal-control/projects** — 创建评价项目

请求体：
```json
{
  "project_name": "2026年度Q1内控评价",
  "client": "ecovacs",
  "audit_period_start": "2026-01-01",
  "audit_period_end": "2026-03-31",
  "project_leader": "zhangsan",
  "project_members": ["lisi", "wangwu"],
  "business_cycles": ["采购付款循环", "销售收款循环", "固定资产循环"]
}
```

**GET /api/v1/internal-control/projects** — 查询项目列表

查询参数：`client`、`status`、`project_leader`、`year`、`page`、`page_size`

**GET /api/v1/internal-control/projects/{project_id}** — 查询项目详情

**PUT /api/v1/internal-control/projects/{project_id}** — 更新项目信息

### 7.2 审计方案管理

**POST /api/v1/internal-control/projects/{project_id}/audit-plan** — 生成/更新审计方案

> 调用 AI 生成五部分审计方案：项目基本信息、评价依据、审计范围、审计实施细则、缺陷认定标准。

**GET /api/v1/internal-control/projects/{project_id}/audit-plan** — 查询当前审计方案

### 7.3 访谈管理

**POST /api/v1/internal-control/projects/{project_id}/interviews/plan** — 生成访谈计划

AI 根据审计方案输出访谈人员清单及时间安排。

请求体：
```json
{
  "business_cycles": ["采购付款循环"],
  "matched_positions": ["采购经理", "采购专员", "财务经理"]
}
```

**GET /api/v1/internal-control/projects/{project_id}/interviews** — 查询访谈列表

**POST /api/v1/internal-control/projects/{project_id}/interviews/questionnaire** — 生成访谈问卷

**GET /api/v1/internal-control/projects/{project_id}/interviews/{interview_id}** — 查询访谈详情

**PUT /api/v1/internal-control/projects/{project_id}/interviews/{interview_id}** — 更新访谈记录（上传访谈纪要/录音）

**POST /api/v1/internal-control/projects/{project_id}/interviews/{interview_id}/speech-to-text** — 语音转文字

上传访谈录音文件，返回文字记录与访谈纪要。

### 7.4 风控矩阵与测试底稿

**POST /api/v1/internal-control/projects/{project_id}/risk-matrix** — 完善风控矩阵

根据访谈问卷结果完善项目风控矩阵。

**POST /api/v1/internal-control/projects/{project_id}/risk-matrix/split** — 拆分设计测试底稿与执行测试底稿

### 7.5 缺陷管理

**POST /api/v1/internal-control/projects/{project_id}/defects** — 创建/导入缺陷记录

请求体：
```json
{
  "defect_type": "design",
  "business_cycle": "采购付款循环",
  "defect_description": "供应商准入审批流程缺少第二人复核环节",
  "related_policy_id": "POL-2025-0032",
  "severity": "major"
}
```

**GET /api/v1/internal-control/projects/{project_id}/defects** — 查询缺陷列表

查询参数：`defect_type`（design/execution）、`business_cycle`、`severity`、`status`、`page`、`page_size`

**PUT /api/v1/internal-control/projects/{project_id}/defects/{defect_id}** — 更新缺陷详情

**POST /api/v1/internal-control/projects/{project_id}/defects/{defect_id}/confirm** — 与业务部门确认缺陷

请求体：
```json
{
  "confirmed": true,
  "business_owner_comment": "认可缺陷描述，将在Q2完成整改"
}
```

### 7.6 评分管理

**POST /api/v1/internal-control/projects/{project_id}/scoring/design** — 评估设计缺陷并打分

AI 根据设计测试底稿阅遍相关制度文档，按评分标准输出设计缺陷类型和得分。

**POST /api/v1/internal-control/projects/{project_id}/scoring/execution** — 评估执行缺陷并打分

**GET /api/v1/internal-control/projects/{project_id}/scoring/summary** — 查询综合评分汇总

按事业部和业务循环维度返回评分汇总表。

### 7.7 报告管理

**POST /api/v1/internal-control/projects/{project_id}/report/generate** — 生成内控评价报告

触发 AI 生成标准五章结构报告：项目概述、内部控制整体结论、内部控制运行情况、重要缺陷列示、持续改善推进。

**GET /api/v1/internal-control/projects/{project_id}/report** — 查询最新报告

**POST /api/v1/internal-control/projects/{project_id}/report/approve** — 守门确认报告

---

## 八、专项审计接口

> 路由前缀：`/api/v1/special-audit` | 标签：`special-audit`

### 8.1 审计项目管理

**POST /api/v1/special-audit/projects** — 创建审计项目

请求体：
```json
{
  "project_name": "2026年度营销费用专项审计",
  "client": "ecovacs",
  "audit_purpose": "审查2025年度营销费用使用的合规性与有效性",
  "audit_focus": ["广告投放费用", "促销活动费用", "渠道返利"],
  "audit_period_start": "2025-01-01",
  "audit_period_end": "2025-12-31",
  "project_leader": "zhangsan",
  "project_members": ["lisi"],
  "risk_control_project_id": "RC-PROJ-001"
}
```

**GET /api/v1/special-audit/projects** — 查询审计项目列表

查询参数：`client`、`status`、`project_leader`、`year`、`page`、`page_size`

**GET /api/v1/special-audit/projects/{project_id}** — 查询项目详情

**PUT /api/v1/special-audit/projects/{project_id}** — 更新项目

### 8.2 审计方案生成

**POST /api/v1/special-audit/projects/{project_id}/audit-plan/generate** — 生成审计方案

AI 根据审计目的和重点，结合历史方案库和审计记录，自动生成含审计范围、调研方法、抽样策略、时间计划和人员规划的方案。

**GET /api/v1/special-audit/projects/{project_id}/audit-plan** — 查询审计方案

**PUT /api/v1/special-audit/projects/{project_id}/audit-plan** — 更新审计方案（含划词调整）

### 8.3 访谈管理

**POST /api/v1/special-audit/projects/{project_id}/interviews/plan** — 生成访谈计划

根据审计方案需访谈内容，调用人事 MCP 匹配访谈人员。

**POST /api/v1/special-audit/projects/{project_id}/interviews/questionnaire** — 生成访谈问卷

**POST /api/v1/special-audit/projects/{project_id}/interviews/dispatch** — 下发访谈任务

ATA 向被访谈人员发送访谈问卷任务。

**GET /api/v1/special-audit/projects/{project_id}/interviews** — 查询访谈列表

**PUT /api/v1/special-audit/projects/{project_id}/interviews/{interview_id}/result** — 上传访谈结果

上传线下访谈文字记录，AI 分析完整性并判断是否需要补充提问。

### 8.4 检查作业

**POST /api/v1/special-audit/projects/{project_id}/inspections/plan** — 生成资料检查计划

根据审计方案业务重点，结合资料清单库和业务流程库，输出检查计划。

**POST /api/v1/special-audit/projects/{project_id}/inspections/checklist** — 生成检查清单

**POST /api/v1/special-audit/projects/{project_id}/inspections/execute** — 执行检查

AI 自动生成 SQL 从数据中台获取数据，按检查点发现问题，生成审计底稿和问题清单。

**GET /api/v1/special-audit/projects/{project_id}/inspections** — 查询检查记录

**GET /api/v1/special-audit/projects/{project_id}/inspections/{inspection_id}/workpapers** — 查询审计底稿

### 8.5 问题管理

**POST /api/v1/special-audit/projects/{project_id}/findings** — 创建审计发现

**GET /api/v1/special-audit/projects/{project_id}/findings** — 查询审计发现列表

查询参数：`severity`、`business_cycle`、`status`、`page`、`page_size`

**POST /api/v1/special-audit/projects/{project_id}/findings/dispatch** — 下发问题确认

ATA 将问题清单拆分，逐条下发至各负责人确认。

**PUT /api/v1/special-audit/projects/{project_id}/findings/{finding_id}/confirm** — 确认/驳回问题

请求体：
```json
{
  "confirmed": true,
  "feedback": "该问题属实，将在本月内完成整改"
}
```

### 8.6 报告管理

**POST /api/v1/special-audit/projects/{project_id}/report/generate** — 生成审计报告

请求体：
```json
{
  "include_sections": ["summary", "findings", "recommendations"],
  "template_id": "TPL-AUDIT-001"
}
```

**GET /api/v1/special-audit/projects/{project_id}/report** — 查询/下载审计报告

**POST /api/v1/special-audit/projects/{project_id}/report/approve** — 守门确认报告

---

## 九、离任审计接口

> 路由前缀：`/api/v1/exit-audit` | 标签：`exit-audit`

### 9.1 审计项目管理

**POST /api/v1/exit-audit/projects** — 创建离任审计项目

请求体（来自风控系统 OA/BPM 审批完成后同步推送）：
```json
{
  "client": "ecovacs",
  "departing_person_name": "王五",
  "departing_person_id": "EMP-005",
  "position": "事业部总经理",
  "department": "电商事业部",
  "entry_date": "2018-03-01",
  "last_working_day": "2026-06-30",
  "project_name": "王五离任审计",
  "project_leader": "zhangsan",
  "project_members": ["lisi"],
  "risk_control_project_id": "RC-PROJ-002"
}
```

**GET /api/v1/exit-audit/projects** — 查询审计项目列表

查询参数：`client`、`status`、`departing_person_name`、`year`、`page`、`page_size`

**GET /api/v1/exit-audit/projects/{project_id}** — 查询项目详情

### 9.2 审计方案生成

**POST /api/v1/exit-audit/projects/{project_id}/audit-plan/generate** — 生成审计方案

AI 根据被审计人岗位职责配置和任职时间，匹配审计方案库，自动生成含审计范围（个人职责+业务范围）和抽样方案的计划。

审计期间自动计算：1年<本岗位时间≤5年 → 向前追溯3年；>5年 → 向前追溯1年。

### 9.3 访谈问卷

**POST /api/v1/exit-audit/projects/{project_id}/interviews/questionnaire** — 生成访谈问卷

响应中增加 `departing_person_confirmable` 字段（离职人是否可确认选项），支持下拉框选择审计组长/组员确认问卷。

### 9.4 资料清单

**POST /api/v1/exit-audit/projects/{project_id}/data-requests** — 生成资料需求清单

AI 根据审计方案生成资料清单，请求体中包含 `provider_name`（资料提供人员名称），同一人员的多条资料合并发送至任务中心。

**GET /api/v1/exit-audit/projects/{project_id}/data-requests** — 查询资料需求列表

### 9.5 问题清单

**POST /api/v1/exit-audit/projects/{project_id}/findings/generate** — 生成问题清单

AI 对业务数据、行为数据（含天眼查外部数据、业务系统数据、行为风险预警）进行验证分析，识别风险场景。

输出分为：
- **个人问题清单**：商业秘密泄露、个人报销、样机使用、关联公司、资产使用等
- **业务问题清单**：流程漏洞、制度缺陷、经济损失等

**GET /api/v1/exit-audit/projects/{project_id}/findings** — 查询问题清单

**POST /api/v1/exit-audit/projects/{project_id}/findings/dispatch** — 下发问题确认

### 9.6 报告管理

**POST /api/v1/exit-audit/projects/{project_id}/report/generate** — 生成离任审计报告

生成标准化《离任审计报告书》（个人离任报告 + 离任审计总报告），经守门后推送风控系统。

---

## 十、行为风险接口

> 路由前缀：`/api/v1/behavioral-risk` | 标签：`behavioral-risk`

### 10.1 行为风险分析

**POST /api/v1/behavioral-risk/analysis** — 发起行为风险分析

请求体：
```json
{
  "client": "ecovacs",
  "scope_type": "department",
  "scope_value": "采购部",
  "position": "采购经理",
  "personnel_ids": ["EMP-001", "EMP-002"],
  "role_type": "employee",
  "analysis_period_start": "2026-01-01",
  "analysis_period_end": "2026-06-30",
  "data_sources": ["file_transfer_logs", "decryption_logs", "hr_records"]
}
```

**GET /api/v1/behavioral-risk/analysis** — 查询分析报告列表

查询参数：`client`、`scope_type`、`status`、`start_date`、`end_date`、`page`、`page_size`

响应包含：`report_id`、`analysis_scope`、`abnormal_behavior_count`、`risk_level`、`status`、`created_at`

**GET /api/v1/behavioral-risk/analysis/{report_id}** — 查询分析报告详情

响应包含：完整分析报告，含异常行为识别、风险等级评估、关联分析结论等

### 10.2 管理报告

**POST /api/v1/behavioral-risk/management-report/generate** — 生成行为风险管理报告

请求体：
```json
{
  "report_period": "2026-05",
  "scope": "group",
  "scope_value": null
}
```

`scope` 可选值：`group`（全集团）、`client`（某事业部）、`department`（某部门）

**GET /api/v1/behavioral-risk/management-reports** — 查询往期管理报告

查询参数：`report_period`、`scope`、`page`、`page_size`

### 10.3 历史报告查看

**GET /api/v1/behavioral-risk/history** — 查询历史分析结果

查询参数：`client`、`analysis_type`、`start_date`、`end_date`、`page`、`page_size`

---

## 十一、商业秘密接口

> 路由前缀：`/api/v1/trade-secret` | 标签：`trade-secret`

### 11.1 定密信息预审

**POST /api/v1/trade-secret/pre-review** — 保密员定密建议/预审

保密员填写定密信息后点击【定密信息预审】，风控系统推送本次及往期定密信息至赫尔墨斯。

请求体：
```json
{
  "organization": "电商事业部",
  "organization_type": "department",
  "current_filing": {
    "secret_items": [
      {
        "item_name": "核心定价算法",
        "secret_level": "core",
        "file_list": ["pricing_algo_v3.py", "定价策略文档.docx"],
        "personnel_scope": ["算法团队"],
        "archive_code": "TS-2026-0001"
      }
    ]
  },
  "historical_filings": [],
  "related_policies": ["POL-SEC-001", "POL-IP-003"]
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "review_id": "pr-001",
    "historical_review_summary": {
      "previously_classified_items": [],
      "consistency_check": "本次无重复定密记录"
    },
    "recommendations": {
      "suggested_items": [
        {
          "item_name": "核心定价算法",
          "suggested_secret_level": "core",
          "rationale": "属于公司核心技术秘密，建议维持核心密级"
        }
      ],
      "completeness_check": "建议补充算法使用日志文件的权限控制说明"
    },
    "report_format": "商业秘密信息表模板"
  }
}
```

**POST /api/v1/trade-secret/pre-review/{review_id}/feedback** — 保密员反馈

请求体：
```json
{
  "acceptance_status": "partial",
  "accepted_items": ["核心定价算法-level-core"],
  "rejected_items": [],
  "comment": "补充权限控制说明的建议已采纳"
}
```

### 11.2 定密信息评审

**POST /api/v1/trade-secret/review** — 发起定密信息评审

评审小组通过风控系统【定密信息评审】按钮发起。

请求体：
```json
{
  "organization": "电商事业部",
  "organization_type": "department",
  "review_flow_id": "FLOW-20260519-001",
  "filing_data": { }
}
```

**GET /api/v1/trade-secret/reviews** — 查询评审历史记录

查询参数：`organization`、`review_status`、`start_date`、`end_date`、`page`、`page_size`

**GET /api/v1/trade-secret/reviews/{review_id}** — 查询评审详情

**POST /api/v1/trade-secret/reviews/{review_id}/report/generate** — 生成定密评审报告

响应结构对齐《商业秘密信息表》模板格式，包含涉密信息类型、密级、文件清单、涉密人员范围、存证编号等的完整性、合理性、准确性评审意见。

### 11.3 管理报告

**POST /api/v1/trade-secret/management-report/generate** — 生成商业秘密管理报告

请求体：
```json
{
  "report_period": "2026-05",
  "scope": "group",
  "scope_value": null
}
```

`scope` 可选值：`group`（全集团）、`client`（某事业部）、`department`（某部门）、`project`（某项目）。

响应含数据图表（总定密组织数量、已定密组织数量及占比、总定密流程数量、总定密信息条数、期间内新增数量和进度）。

**GET /api/v1/trade-secret/management-reports** — 查询往期管理报告

---

## 十二、持续改善接口

> 路由前缀：`/api/v1/continuous-improvement` | 标签：`continuous-improvement`

### 12.1 问题管理

**POST /api/v1/continuous-improvement/issues** — 创建/导入问题

支持三种录入方式：从风控系统自动抓取、单条手动录入、Excel 批量导入。

请求体（单条录入，字段对齐固定表头 30+ 字段）：
```json
{
  "project_year": 2026,
  "client": "ecovacs",
  "source": "internal_control",
  "audit_project_id": "AP-001",
  "audit_project_name": "2026年度Q1内控评价",
  "finding_code": "IC-2026-001",
  "finding_description": "采购审批流程缺少第二人复核",
  "business_cycle": "采购付款循环",
  "improvement_suggestion": "在审批流程中增加财务经理复核环节",
  "project_leader": "zhangsan",
  "responsible_department": "采购部",
  "responsible_person": "采购经理-赵六",
  "planned_completion_date": "2026-08-31"
}
```

响应字段含：序号（自动编号）、审计发现编号（唯一，系统生成或手动录入后校验）、AI 复核计划时间、AI 复核意见、审计复核意见、整改答复次数、状态、直接挽损金额、间接挽损金额等全部 30+ 字段。

**GET /api/v1/continuous-improvement/issues** — 查询问题列表

查询参数（丰富的筛选能力）：

| 参数 | 说明 |
|------|------|
| `client` | 事业部 |
| `source` | 来源：internal_control/special_audit/exit_audit/case_handling/risk_monitor |
| `status` | 状态（见下方状态说明） |
| `responsible_department` | 责任部门 |
| `responsible_person` | 责任人 |
| `is_overdue` | 是否超期 |
| `project_year` | 项目年度 |
| `business_cycle` | 业务循环 |
| `keyword` | 关键字搜索 |
| `page`、`page_size` | 分页 |

**GET /api/v1/continuous-improvement/issues/{issue_id}** — 查询问题详情

返回全字段信息 + 全流程操作记录 + 整改材料列表 + 复核意见历史。

**PUT /api/v1/continuous-improvement/issues/{issue_id}** — 更新问题

**POST /api/v1/continuous-improvement/issues/{issue_id}/cancel** — 作废问题

请求体：
```json
{
  "cancel_reason": "经核实为重复录入，原始记录见 IC-2026-001"
}
```

**POST /api/v1/continuous-improvement/issues/import** — Excel 批量导入

请求体：`multipart/form-data`，上传按固定表头模板填写的 Excel 文件。导入后支持手动编辑修改。

### 12.2 整改计划管理

**GET /api/v1/continuous-improvement/issues/{issue_id}/plan** — 查询整改计划

**POST /api/v1/continuous-improvement/issues/{issue_id}/plan** — 提交整改计划

由责任部门负责人在任务中心提交，含具体责任整改人和整改计划/方案附件。

请求体：
```json
{
  "responsible_person": "赵六",
  "plan_description": "1.修改采购审批流程配置；2.增加财务经理节点；3.全量测试",
  "plan_attachments": ["/uploads/rectification_plan.xlsx"],
  "planned_completion_date": "2026-08-31"
}
```

**POST /api/v1/continuous-improvement/issues/{issue_id}/plan/ai-review** — AI 初审整改计划

AI 对业务部门上传的整改计划进行审核并给出意见。

**POST /api/v1/continuous-improvement/issues/{issue_id}/plan/audit-review** — 审计岗审核计划

请求体：
```json
{
  "approved": true,
  "audit_comment": "整改计划合理可行"
}
```

### 12.3 任务下发

**POST /api/v1/continuous-improvement/issues/{issue_id}/dispatch** — 下发整改任务

项目组长确认问题录入无误后一键下发。

- 自动将整改任务推送至对应部门负责人（任务中心）
- 同时推送审计跟进人"计划审核任务"
- 下发后状态自动更新为"计划待提交"
- 部门负责人收到 Elink 通知

**POST /api/v1/continuous-improvement/issues/batch-dispatch** — 批量下发

请求体：
```json
{
  "issue_ids": ["iss-001", "iss-002", "iss-003"]
}
```

**POST /api/v1/continuous-improvement/issues/{issue_id}/urge** — 一键催办

审计岗触发催办，发送督促消息（Elink），记录督促次数和时间。

### 12.4 证据提交

**POST /api/v1/continuous-improvement/issues/{issue_id}/evidence** — 提交整改证据

责任人在任务中心提交整改完成证据，须严格按照已提交的整改计划执行。

请求体：
```json
{
  "evidence_description": "已修改采购审批流程配置并完成测试，详见附件",
  "evidence_attachments": ["/uploads/flow_config.png", "/uploads/test_report.xlsx"],
  "completion_date": "2026-08-15"
}
```

### 12.5 复核与闭环

**POST /api/v1/continuous-improvement/issues/{issue_id}/review/ai** — AI 初审核

AI 依据前期整改计划，对提交的附件进行初审判断。

**POST /api/v1/continuous-improvement/issues/{issue_id}/review/audit** — 审计岗复核

请求体：
```json
{
  "approved": true,
  "audit_opinion": "整改证据充分，确认通过",
  "actual_loss_recovery_amount": 50000.00,
  "indirect_loss_recovery_amount": 200000.00,
  "personnel_handling": "相关责任人已通报批评"
}
```

审批通过 → 状态更新为"整改完成"，自动归档。归档后不可编辑。

不通过 → 填写退回原因 → 状态更新为"退回重改" → 向责任人发送退回提醒。退回次数达 3 次及以上同步通知所在部门负责人。

**POST /api/v1/continuous-improvement/issues/batch-review** — 批量复核

### 12.6 统计分析

**GET /api/v1/continuous-improvement/statistics/summary** — 统计概览

查询参数：`client`、`start_date`、`end_date`

响应：
```json
{
  "code": 0,
  "data": {
    "total_issues": 156,
    "in_progress_count": 42,
    "completed_count": 98,
    "overdue_count": 16,
    "rejected_count": 8,
    "completion_rate": 0.628,
    "overdue_rate": 0.103
  }
}
```

**GET /api/v1/continuous-improvement/statistics/by-department** — 按部门统计

**GET /api/v1/continuous-improvement/statistics/by-source** — 按来源统计

**GET /api/v1/continuous-improvement/statistics/trend** — 整改进度趋势（折线图数据）

**POST /api/v1/continuous-improvement/reports/export** — 导出统计报表

请求体：
```json
{
  "export_format": "excel",
  "filters": { "client": "ecovacs", "start_date": "2026-01-01", "end_date": "2026-12-31" }
}
```

### 12.7 问题状态流水

| 状态 | 含义 | 触发条件 |
|------|------|----------|
| `pending_dispatch` | 问题待推送 | 审计问题清单同步至整改智能体后 |
| `plan_pending` | 计划待提交 | 审计组长下发整改任务，整改部门未上传计划 |
| `plan_under_review` | 计划待审批 | 整改部门上传计划，审计跟进人未审核 |
| `rectification_pending` | 整改答复待提交 | 审计人员已审核计划，整改部门未上传证据 |
| `rectified_under_review` | 已整改待复核 | 整改部门已上传证据，审计跟进人未审核 |
| `completed` | 整改完成 | 审计跟进人复核通过 |
| `returned` | 退回重改 | AI 复核或审计复核不通过 |
| `cancelled` | 已作废 | 手动作废，留痕备查 |

---

## 十三、知识库管理接口

> 路由前缀：`/api/v1/knowledge-bases` | 标签：`knowledge`

### 13.1 知识库列表

**GET /api/v1/knowledge-bases**

响应：
```json
{
  "code": 0,
  "data": [
    { "type": "intake", "name": "初筛知识库", "doc_count": 128, "last_synced": "2026-05-18T00:00:00Z" },
    { "type": "investigation", "name": "调查方案知识库", "doc_count": 56, "last_synced": "2026-05-15T00:00:00Z" },
    { "type": "analysis", "name": "分析报告知识库", "doc_count": 89, "last_synced": "2026-05-18T00:00:00Z" },
    { "type": "disposition", "name": "处置分流知识库", "doc_count": 73, "last_synced": "2026-05-17T00:00:00Z" },
    { "type": "enforcement", "name": "处罚执行知识库", "doc_count": 45, "last_synced": "2026-05-16T00:00:00Z" },
    { "type": "internal_control", "name": "内控评价知识库", "doc_count": 210, "last_synced": "2026-05-18T00:00:00Z" },
    { "type": "special_audit", "name": "专项审计知识库", "doc_count": 67, "last_synced": "2026-05-17T00:00:00Z" },
    { "type": "exit_audit", "name": "离任审计知识库", "doc_count": 42, "last_synced": "2026-05-16T00:00:00Z" },
    { "type": "trade_secret", "name": "商业秘密知识库", "doc_count": 35, "last_synced": "2026-05-15T00:00:00Z" },
    { "type": "behavior_risk", "name": "行为风险知识库", "doc_count": 28, "last_synced": "2026-05-15T00:00:00Z" }
  ]
}
```

### 13.2 文档导入

**POST /api/v1/knowledge-bases/{kb_type}/import**

请求体：`multipart/form-data`

| 字段 | 类型 | 说明 |
|------|------|------|
| `files` | file[] | 支持 docx/xlsx/pdf/txt |
| `replace` | bool | true=替换同名文件 |

响应：
```json
{
  "code": 0,
  "data": {
    "imported_count": 5,
    "updated_count": 2,
    "failed_count": 1,
    "failures": [
      { "filename": "corrupted.docx", "reason": "文件无法解析" }
    ]
  }
}
```

### 13.3 文档管理

**GET /api/v1/knowledge-bases/{kb_type}/documents** — 查询知识库文档列表

查询参数：`keyword`、`is_active`、`page`、`page_size`

**DELETE /api/v1/knowledge-bases/{kb_type}/documents/{doc_id}** — 删除文档（重新索引）

**PUT /api/v1/knowledge-bases/{kb_type}/documents/{doc_id}** — 更新文档元数据

### 13.4 搜索

**GET /api/v1/knowledge-bases/search**

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索关键词 |
| `kb_types` | string[] | 否 | 限定知识库类型，逗号分隔 |
| `top_k` | int | 否 | 返回结果数，默认 5，最大 20 |

响应：
```json
{
  "code": 0,
  "data": [
    {
      "doc_id": "kb-intake-001",
      "kb_type": "intake",
      "title": "公司差旅报销制度 v3.2",
      "content_snippet": "...差旅报销需经直属上级审批，单次金额超过5000元需财务总监加签...",
      "relevance": 0.95,
      "updated_at": "2026-03-15T00:00:00Z"
    }
  ]
}
```

---

## 十四、A2A 协议规范

### 14.1 消息格式

赫尔墨斯与外部智能体（龟宝、西塞罗、波特）之间的通信采用统一 JSON 消息格式：

```json
{
  "message_id": "msg-uuid-v4",
  "protocol_version": "1.0",
  "source_agent": "hermes",
  "target_agent": "guibao",
  "command": "initiate_penalty_tracking",
  "case_ref": "SD2026051901",
  "priority": "normal",
  "payload": {
    "employee_name": "李四",
    "employee_id": "EMP-003",
    "penalty_type": "salary_deduction",
    "penalty_amount": 5000.00,
    "deduction_period_months": 3,
    "effective_date": "2026-06-01",
    "attachments": ["/a2a/penalty_order_001.pdf"]
  },
  "callback_url": "https://hermes.ecovacs.cn/api/v1/webhooks/a2a/guibao",
  "expires_at": "2026-05-26T10:30:00Z",
  "created_at": "2026-05-19T10:30:00Z"
}
```

### 14.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message_id` | UUID v4 | 是 | 消息唯一标识 |
| `protocol_version` | string | 是 | 协议版本，当前 1.0 |
| `source_agent` | string | 是 | 来源智能体名称：hermes |
| `target_agent` | string | 是 | 目标智能体：guibao / cicero / porter |
| `command` | string | 是 | 操作指令（见下方命令表） |
| `case_ref` | string | 是 | 关联的 Hermes 案件 task_id |
| `priority` | string | 否 | 优先级：low/normal/high |
| `payload` | object | 是 | 业务载荷（根据 command 不同） |
| `callback_url` | string | 是 | 结果回调地址 |
| `expires_at` | string | 否 | 消息过期时间（ISO 8601） |
| `created_at` | string | 是 | 消息创建时间 |

### 14.3 各智能体命令表

**龟宝 (guibao)** — 员工管理智能体：

| 命令 | 场景 | payload 关键字段 |
|------|------|-----------------|
| `initiate_penalty_tracking` | 发起员工处罚跟踪 | employee_name, employee_id, penalty_type, penalty_amount, deduction_period |
| `transfer_hr_case` | 转交 HR 相关案件 | case_detail, employee_list, transfer_reason |
| `query_penalty_status` | 查询处罚执行状态 | tracking_id |

**西塞罗 (cicero)** — 法务智能体：

| 命令 | 场景 | payload 关键字段 |
|------|------|-----------------|
| `push_civil_case` | 推送民事纠纷案件 | case_info, evidence_list, legal_basis |
| `submit_agreement_review` | 提交协议审核 | agreement_type, agreement_content, related_parties |
| `query_legal_opinion` | 查询法律意见 | case_context, legal_questions |

**波特 (porter)** — 财务智能体：

| 命令 | 场景 | payload 关键字段 |
|------|------|-----------------|
| `initiate_supplier_deduction` | 发起供应商扣款跟踪 | supplier_name, deduction_amount, deduction_reason, tracking_period |
| `query_deduction_status` | 查询扣款状态 | tracking_id |

### 14.4 任务生命周期

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ pending  │→  │   sent   │→  │ accepted │→  │completed │→  │  closed  │
│ (待发送)  │   │ (已发送)  │   │ (已接收)  │   │ (已完成)  │   │ (已归档)  │
└──────────┘   └────┬─────┘   └────┬─────┘   └──────────┘   └──────────┘
                    │              │
                    ↓              ↓
              ┌──────────┐  ┌──────────┐
              │  failed  │  │ rejected │
              │ (发送失败) │  │ (已拒绝)  │
              └──────────┘  └──────────┘
```

### 14.5 回调确认

外部智能体完成任务后，向 `callback_url` 发送确认消息：

```json
{
  "message_id": "msg-uuid-response",
  "original_message_id": "msg-uuid-v4",
  "target_agent": "hermes",
  "status": "completed",
  "result": {
    "tracking_id": "TRK-2026-001",
    "summary": "员工扣款已录入HR系统，首期扣款 2026-06-01 生效"
  },
  "completed_at": "2026-05-19T11:30:00Z"
}
```

### 14.6 重试与容错

- 发送失败自动重试 3 次，间隔 10s/30s/60s
- 三次重试失败后标记 `failed`，人工介入
- 消息过期（超过 `expires_at`）自动取消
- 所有 A2A 通信记录存入 `a2a_tasks` 表

---

## 十五、WebSocket 事件规范

### 15.1 连接

```
WebSocket 端点: ws://<host>/api/v1/ws
协议升级前需携带认证参数:
  ?token=<access_token>
```

### 15.2 订阅与消息格式

客户端连接后发送订阅消息指定关注的频道：

```json
{
  "action": "subscribe",
  "channels": ["case:SD2026051901", "task_center:user-zhangsan"]
}
```

服务端推送消息格式：

```json
{
  "channel": "case:SD2026051901",
  "event": "stage_changed",
  "data": {
    "case_id": "c-001",
    "task_id": "SD2026051901",
    "previous_stage": "intake",
    "current_stage": "investigation",
    "timestamp": "2026-05-19T11:46:00Z"
  }
}
```

### 15.3 工作流事件

用于风控系统按钮状态同步和前端工作流面板实时更新。

| 事件名 | 触发时机 | data 内容 |
|--------|----------|-----------|
| `workflow_started` | 工作流启动 | `{ case_id, thread_id, current_stage }` |
| `stage_changed` | 阶段切换 | `{ case_id, previous_stage, current_stage }` |
| `approval_required` | 进入守门等待 | `{ case_id, stage, pending_approval_stage }` |
| `approval_completed` | 守门完成 | `{ case_id, stage, result, next_stage }` |
| `workflow_completed` | 工作流结束 | `{ case_id, final_status }` |
| `workflow_error` | 工作流出错 | `{ case_id, stage, error_info }` |
| `stage_regenerated` | AI 输出重新生成 | `{ case_id, stage, regenerated_part }` |

### 15.4 风控按钮状态同步

风控系统通过 WebSocket 接收案件状态变更，实现按钮联动：

| Hermes 事件 | 风控按钮状态 | 说明 |
|------------|-------------|------|
| `stage_changed` → `intake` | "AI 协助" | 初筛阶段 |
| `approval_required` → `intake` | "线索初判-待确认" | 等待守门 |
| `stage_changed` → `investigation` | "调查进行中" | 调查方案阶段 |
| `workflow_completed` | 按钮不可点击 | 闭环完成 |
| 用户退出页面 | 保留状态 | 再次点击可恢复 |

### 15.5 任务中心事件

| 事件名 | 触发时机 | data 内容 |
|--------|----------|-----------|
| `task_assigned` | 新任务分配 | `{ task_id, task_type, assignee, due_date }` |
| `task_updated` | 任务状态变更 | `{ task_id, new_status, updated_by }` |
| `task_reminder` | 催办通知 | `{ task_id, message }` |
| `task_overdue` | 任务逾期 | `{ task_id, overdue_days }` |

---

## 十六、外部系统 Webhook

### 16.1 风控系统回调

**POST /api/v1/webhooks/risk-control**

风控系统在以下场景通过 Webhook 回调赫尔墨斯：

**场景一：案件创建同步**

当风控系统内的案件需要 AI 辅助时，推送案件数据到赫尔墨斯创建对应案件。

```json
{
  "event": "case_created",
  "risk_control_case_id": "RC20260519001",
  "data": {
    "fraud_source": "phone",
    "client": "ecovacs",
    "reported_staff_names": ["李四"],
    "reported_supplier_names": [],
    "reported_dealer_names": [],
    "fraud_event_detail": "...",
    "proof": "...",
    "fraud_tel": "138****1234",
    "fraud_email": "whistle@example.com",
    "attachments": ["proof_001.pdf"]
  }
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "acknowledged": true,
    "hermes_case_id": "c-001",
    "hermes_task_id": "DH2026051901"
  }
}
```

**场景二：状态同步确认**

```json
{
  "event": "status_sync",
  "hermes_case_id": "c-001",
  "risk_control_case_id": "RC20260519001",
  "status": "investigate_in_progress",
  "synced_fields": {
    "current_stage": "investigation",
    "investigation_plan_attached": true
  }
}
```

**场景三：闭环推送确认**

```json
{
  "event": "closure_confirmed",
  "hermes_case_id": "c-001",
  "risk_control_case_id": "RC20260519001",
  "closure_type": "not_handled",
  "closure_reason": "证据不足，不予调查",
  "actual_close_date": "2026-05-19",
  "attachments": ["intake_report.docx"]
}
```

### 16.2 OA 系统回调

**POST /api/v1/webhooks/oa**

OA 系统审批流程完成后回调，用于添可事业部的处罚公告 OA 审批：

```json
{
  "event": "approval_completed",
  "oa_process_id": "OA-2026-0519-001",
  "hermes_case_id": "c-001",
  "approval_result": "approved",
  "approver": "部门总监-陈总",
  "approved_at": "2026-05-19T14:00:00Z",
  "comment": "同意处罚决定"
}
```

### 16.3 MDM 系统回调

**POST /api/v1/webhooks/mdm**

MDM 黑名单库操作结果回调：

```json
{
  "event": "blacklist_sync",
  "hermes_case_id": "c-001",
  "supplier_name": "XX供应商",
  "supplier_code": "SUP-2026-001",
  "operation": "add",
  "status": "success",
  "blacklist_reason": "围串标行为",
  "synced_at": "2026-05-19T15:00:00Z"
}
```

### 16.4 A2A 回调

**POST /api/v1/webhooks/a2a/{agent}**

外部智能体（龟宝/西塞罗/波特）处理完成后回调：

```json
{
  "message_id": "resp-uuid-001",
  "original_message_id": "msg-uuid-001",
  "target_agent": "hermes",
  "status": "completed",
  "result": {
    "tracking_id": "TRK-2026-001",
    "summary": "员工处罚已落实，首期扣款 2026-06-01 生效"
  },
  "completed_at": "2026-05-19T16:00:00Z"
}
```

赫尔墨斯收到回调后：
1. 更新 `a2a_tasks` 记录状态
2. 若关联工作流阶段等待 A2A 结果，自动推进工作流
3. 记录操作日志

---

## 十七、错误码表

### 17.1 错误码格式

错误码采用 5 位数字：`{HTTP状态码前3位}{模块编号}{错误序号}`

### 17.2 通用错误码（00）

| 错误码 | HTTP 状态码 | 中文描述 | 说明 |
|--------|-----------|---------|------|
| `40000` | 400 | 请求参数错误 | 参数校验失败 |
| `40100` | 401 | 未认证 | 缺少或无效的 access_token |
| `40101` | 401 | 令牌已过期 | access_token 过期，请刷新 |
| `40102` | 401 | 账号已锁定 | 连续登录失败超限，请联系管理员 |
| `40300` | 403 | 无权限访问 | 角色无权限访问该资源 |
| `40301` | 403 | 跨事业部数据不可见 | 仅可查看所属事业部数据 |
| `40400` | 404 | 资源不存在 | 请求的资源 ID 无效或已删除 |
| `40900` | 409 | 资源冲突 | 资源状态冲突（如 task_id 重复） |
| `41300` | 413 | 文件大小超限 | 上传文件超过 50MB 限制 |
| `42900` | 429 | 请求频率超限 | 超过 100 req/min 限制 |
| `50000` | 500 | 服务器内部错误 | 未知错误 |
| `50001` | 500 | AI 服务不可用 | LLM 调用失败或超时 |
| `50002` | 500 | 外部系统不可用 | 风控/OA/MDM 外部系统调用失败 |
| `50300` | 503 | 服务维护中 | 系统维护或升级中 |

### 17.3 案件模块错误码（01）

| 错误码 | HTTP 状态码 | 中文描述 | 说明 |
|--------|-----------|---------|------|
| `40401` | 404 | 案件不存在 | case_id 不存在或已删除 |
| `40901` | 409 | 案件状态不允许操作 | 当前案件状态不支持该操作 |
| `40902` | 409 | 工作流已启动 | 工作流已启动，无法修改案件 |
| `42201` | 422 | task_id 生成失败 | 序列号生成异常 |

### 17.4 工作流错误码（02）

| 错误码 | HTTP 状态码 | 中文描述 | 说明 |
|--------|-----------|---------|------|
| `40002` | 400 | 工作流未启动 | 请先调用 start 接口 |
| `40003` | 400 | 工作流已完成 | 工作流已结束，无法恢复 |
| `40004` | 400 | 无待守门阶段 | 当前没有等待守门的阶段 |
| `40903` | 409 | 工作流已中断 | 请先恢复工作流 |
| `42202` | 422 | 工作流执行失败 | LangGraph 执行异常 |
| `42203` | 422 | 阶段重试次数超限 | 已达到最大重试次数，需人工介入 |

### 17.5 风险监控错误码（03）

| 错误码 | HTTP 状态码 | 中文描述 | 说明 |
|--------|-----------|---------|------|
| `42203` | 422 | SQL 语法校验失败 | 风险规则 SQL 无法在测试环境执行 |
| `40403` | 404 | 风险规则不存在 | rule_id 不存在或已停用 |
| `40903` | 409 | 规则已停用 | 已停用的规则不允许执行监控 |

### 17.6 行为风险错误码（05）

| 错误码 | HTTP 状态码 | 中文描述 | 说明 |
|--------|-----------|---------|------|
| `40405` | 404 | 分析报告不存在 | report_id 不存在 |
| `40005` | 400 | 分析参数不完整 | 缺少必填的分析范围或时间范围 |

### 17.7 持续改善错误码（07）

| 错误码 | HTTP 状态码 | 中文描述 | 说明 |
|--------|-----------|---------|------|
| `40007` | 400 | 必填字段缺失 | 审计发现描述/责任部门/责任人/计划完成时间不能为空 |
| `40907` | 409 | 审计发现编号重复 | 同一来源下 finding_code 必须唯一 |
| `42207` | 422 | 计划完成时间无效 | 计划完成时间不能早于录入日期 |
| `40908` | 409 | 问题已归档 | 归档后不可编辑，仅可查看 |

### 17.8 知识库错误码（08）

| 错误码 | HTTP 状态码 | 中文描述 | 说明 |
|--------|-----------|---------|------|
| `40408` | 404 | 知识库类型不存在 | kb_type 不在已注册类型列表中 |
| `40008` | 400 | 文件格式不支持 | 仅支持 docx/xlsx/pdf/txt 格式 |
| `42208` | 422 | 文档解析失败 | 文件内容无法提取文本 |

---

## 附录 A：公共接口补充

### A.1 用户管理

> 路由前缀：`/api/v1/admin/users` | 标签：`admin` | 权限：仅 `group` 角色

**GET /api/v1/admin/users** — 用户列表
**POST /api/v1/admin/users** — 创建用户
**PUT /api/v1/admin/users/{user_id}** — 更新用户
**PATCH /api/v1/admin/users/{user_id}/status** — 启用/禁用用户
**DELETE /api/v1/admin/users/{user_id}** — 删除用户（软删除）

### A.2 审计日志

> 路由前缀：`/api/v1/admin/audit-logs` | 标签：`admin` | 权限：仅 `group` 角色

**GET /api/v1/admin/audit-logs** — 审计日志查询

查询参数：`operator`、`operation`、`target_table`、`target_id`、`start_date`、`end_date`、`page`、`page_size`

> 审计日志不可删除、不可篡改，保留 >= 6 个月，满足等保二级要求。

### A.3 文档管理（公共）

> 路由前缀：`/api/v1/documents` | 标签：`documents`

**GET /api/v1/cases/{case_id}/documents** — 查询案件所有输出物列表

**GET /api/v1/documents/{doc_id}/download** — 下载文档（Word/Excel/PDF），返回 Binary stream

**POST /api/v1/cases/{case_id}/speech-to-text** — 语音转文字

请求体：`multipart/form-data { file }`（支持 wav/mp3/m4a）

响应：
```json
{
  "code": 0,
  "data": {
    "text": "完整的语音转文字内容...",
    "file_path": "/uploads/transcripts/c-001/stt-001.txt",
    "duration_seconds": 360
  }
}
```

**POST /api/v1/cases/{case_id}/sql-analyze** — SQL 数据分析

请求体：`multipart/form-data { file, query_hint }`（上传 CSV/Excel 数据文件）

### A.4 任务中心

> 路由前缀：`/api/v1/tasks` | 标签：`tasks`

**GET /api/v1/tasks** — 查询待办任务

查询参数：`assignee`、`task_type`、`status`、`page`、`page_size`

**GET /api/v1/tasks/{task_id}** — 任务详情

**PUT /api/v1/tasks/{task_id}** — 更新任务状态

**POST /api/v1/tasks/{task_id}/comment** — 添加任务评论/反馈
