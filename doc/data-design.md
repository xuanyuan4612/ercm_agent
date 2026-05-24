# 赫尔墨斯（Hermes）数据设计文档

> 版本：v1.0 | 数据库：PostgreSQL 16 + pgvector | 编码：UTF-8 | 字符集：zh_CN.UTF-8

---

## 一、数据架构概述

### 1.1 数据库选型

| 组件 | 选型 | 用途 |
|------|------|------|
| 主数据库 | PostgreSQL 16 | 业务数据、事务处理、全文检索 |
| 向量扩展 | pgvector 0.7+ | 知识库语义检索、RAG 召回 |
| 缓存 | Redis 7 | Session、LangGraph Checkpointer、任务队列 |
| 对象存储 | MinIO | 附件、生成文档、音频/图片文件 |

### 1.2 数据分层

```
┌──────────────────────────────────────────────────────────────────┐
│                        应用层（API 读写）                          │
├──────────┬──────────┬──────────┬──────────┬──────────┬───────────┤
│ 廉洁监察  │ 风险监控  │ 内控评价  │ 专项审计  │ 离任审计  │ 商业秘密   │
├──────────┴──────────┴──────────┴──────────┴──────────┴───────────┤
│                       持续改善（统一闭环层）                        │
├──────────────────────────────────────────────────────────────────┤
│                     共享服务层（用户 / 审计 / A2A）                 │
├──────────────────────────────────────────────────────────────────┤
│                   知识库层（pgvector + 分区索引）                   │
├──────────────────────────────────────────────────────────────────┤
│              存储层（PostgreSQL 16 + MinIO 对象存储）              │
└──────────────────────────────────────────────────────────────────┘
```

### 1.3 命名规范

| 规范项 | 规则 | 示例 |
|--------|------|------|
| 表名 | 小写蛇形命名，复数形式 | `risk_alerts` |
| 主键 | 统一使用 `id UUID` | `id UUID PRIMARY KEY DEFAULT gen_random_uuid()` |
| 外键 | `{关联表单数}_id` | `case_id`, `rule_id` |
| 时间戳 | `{动作}_at TIMESTAMPTZ` | `created_at`, `reviewed_at` |
| 布尔标记 | `is_{状态}` | `is_deleted`, `is_active`, `is_confirmed` |
| JSONB | 灵活结构或列表字段 | `attachments`, `questions`, `ai_output` |
| 加密字段 | `{字段}_encrypted BYTEA` | `reported_staff_encrypted` |
| 金额字段 | `NUMERIC(18,2)` | `direct_recovery_amount` |

---

## 二、实体关系图（ER 图）

```
                                    ┌──────────────────────┐
                                    │        users          │
                                    │  (RBAC 权限体系)       │
                                    └──────────┬───────────┘
                                               │
                         ┌─────────────────────┼─────────────────────┐
                         │ 1:N                 │ 1:N                 │ 1:N
                         ▼                     ▼                     ▼
                  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
                  │  audit_log   │    │human_approvals│    │rule_iteration_log│
                  └──────────────┘    └──────┬───────┘    └──────────────────┘
                                             │
    ┌────────────────────────────────────────┼────────────────────────────────────────────┐
    │                                        │ 1:N                                        │
    │  ┌──────────────────────┐     ┌────────▼────────┐                                   │
    │  │   generated_documents │◄───┤     cases         │◄──────────────────┐               │
    │  │   (廉洁监察产出物)     │1:N └───┬───┬────┬─────┘                   │               │
    │  └──────────────────────┘         │   │    │                         │               │
    │                                   │   │    │ 1:N                     │               │
    │                          ┌────────┘   │    └──────────┐              │               │
    │                          │ 1:N        │ 1:N           │ 1:N          │ 1:N           │
    │                          ▼            ▼               ▼              │               │
    │                   ┌───────────┐ ┌───────────┐  ┌───────────┐         │               │
    │                   │case_stages│ │ a2a_tasks │  │external_  │         │               │
    │                   │(阶段流转)  │ │(智能体通信)│  │sync_logs  │         │               │
    │                   └───────────┘ └───────────┘  └───────────┘         │               │
    └─────────────────────────────────────────────────────────────────────┼───────────────┘
                                                                          │
    ┌─────────────────────────────────────────────────────────────────────┤
    │                                                                     │ 来源: risk_alerts → cases
    │  ┌─────────────────────┐     ┌────────────────────┐                 │
    │  │    risk_rules        │     │  rule_iteration_log │                 │
    │  │   (风险规则库)        │1:N  │  (规则迭代记录)      │                 │
    │  └──────────┬──────────┘     └────────────────────┘                 │
    │             │ 1:N                                                   │
    │             ▼                                                       │
    │  ┌─────────────────────┐     ┌──────────────────────┐               │
    │  │    risk_alerts       │1:N  │ risk_analysis_subjects│              │
    │  │   (风险预警明细)      ├────►│  (分析主体合并)        │              │
    │  └──────────┬──────────┘     └──────────────────────┘               │
    │             │ 1:N                                                   │
    │             ▼                                                       │
    │  ┌─────────────────────┐                                            │
    │  │  risk_push_records   │──► 推送至 廉洁监察 / 内控评价 / 商业秘密     │
    │  └─────────────────────┘                                            │
    └─────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                                                                             │
    │  ┌──────────────────────┐    1:N    ┌──────────────────────┐                │
    │  │ ic_evaluation_projects│─────────►│  ic_control_matrices  │                │
    │  │   (内控评价项目)       │          │   (风控矩阵)           │                │
    │  └──────────┬───────────┘          └──────────┬───────────┘                │
    │             │ 1:N                   ┌─────────┴─────────┐                   │
    │             ├──────────────────────►│                    │                   │
    │             │ 1:N              ┌────▼─────┐      ┌──────▼──────┐            │
    │             ├─────────────────►│ic_design │      │ic_execution │            │
    │             │ 1:N              │_defects  │      │_defects     │            │
    │             ├─────────────────►│(设计缺陷) │      │(执行缺陷)    │            │
    │             │ 1:N              └──────────┘      └─────────────┘            │
    │             ├────────────────►  ic_score_records (打分记录)                   │
    │             └────────────────►  ic_evaluation_reports (评价报告)              │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                                                                             │
    │  ┌─────────────────┐   1:N   ┌───────────┐  1:N  ┌──────────────┐           │
    │  │ audit_projects   │────────►│audit_plans│──────►│audit_checklists│          │
    │  │  (专项审计项目)   │        │(审计方案)  │       │(检查清单)      │           │
    │  └────────┬────────┘        └───────────┘       └──────────────┘           │
    │           │ 1:N                                                             │
    │           ├──────────────►  audit_interviews (访谈记录)                      │
    │           ├──────────────►  audit_findings (审计发现)                        │
    │           └──────────────►  audit_reports (审计报告)                         │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                                                                             │
    │  ┌───────────────────┐ 1:N  ┌────────────────────┐                          │
    │  │ exit_audit_projects│────►│exit_audit_plans      │                          │
    │  │  (离任审计项目)     │     │(离任审计方案)         │                          │
    │  └─────────┬─────────┘     └────────────────────┘                          │
    │            │ 1:N                                                            │
    │            ├──────────────► exit_audit_questionnaires (访谈问卷)              │
    │            ├──────────────► exit_audit_data_requests (资料需求)               │
    │            ├──────────────► exit_audit_findings (审计发现)                    │
    │            └──────────────► exit_audit_reports (审计报告)                     │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                                                                             │
    │  ┌────────────────────┐  1:N  ┌──────────────────────┐                      │
    │  │ trade_secret_items  │──────►│trade_secret_reviews   │                      │
    │  │  (商业秘密事项)      │      │(定密评审记录)          │                      │
    │  └──────────┬─────────┘      └──────────────────────┘                      │
    │             │ 1:N                                                           │
    │             ├──────────────► trade_secret_suggestions (定密建议)              │
    │             └──────────────► trade_secret_management_reports (管理报告)       │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                                                                             │
    │  ┌────────────────────┐                                                     │
    │  │ improvement_issues  │── 统一承接所有模块发现的问题                          │
    │  │  (持续改善问题)      │                                                     │
    │  └─────────┬──────────┘                                                     │
    │            │ 1:N                                                            │
    │            ├──────────────► improvement_plans (整改计划)                      │
    │            ├──────────────► improvement_tasks (整改任务)                      │
    │            ├──────────────► improvement_evidence (整改证据)                   │
    │            └──────────────► improvement_reviews (整改复核)                    │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                         知识库（独立知识域）                                   │
    │                                                                             │
    │  ┌──────────────────────────────────────────────────────────────┐           │
    │  │  knowledge_documents (pgvector 向量存储, 按 kb_type 分区索引)   │           │
    │  │  kb_type: intake | investigation | analysis | disposition     │           │
    │  │          | enforcement | risk_monitor | ic_evaluation         │           │
    │  │          | special_audit | exit_audit | trade_secret           │           │
    │  │          | improvement | common                                │           │
    │  └──────────────────────────────────────────────────────────────┘           │
    └─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、共享基础表

### 3.1 用户表（users）

```sql
-- 用户与权限表（RBAC 三层角色：group / ecovacs / tineco）
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    department VARCHAR(100),
    email VARCHAR(200),
    role VARCHAR(20) NOT NULL CHECK (role IN ('group', 'ecovacs', 'tineco')),
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE users IS '用户表（RBAC 三层角色权限体系）';
COMMENT ON COLUMN users.role IS '角色：group=集团(全量), ecovacs=科沃斯, tineco=添可';
```

### 3.2 审计日志表（audit_log）

```sql
-- 审计日志表（等保二级要求：仅追加，不可删除，保留 >= 6 个月）
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id VARCHAR(50),
    operator_role VARCHAR(20),
    operation VARCHAR(20) NOT NULL,
    target_table VARCHAR(50),
    target_id UUID,
    ip_address INET,
    user_agent TEXT,
    changes JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE audit_log IS '审计日志表（等保二级：仅追加、不可删除、不可篡改）';
COMMENT ON COLUMN audit_log.operation IS '操作类型：CREATE/UPDATE/DELETE/EXPORT/APPROVE/REJECT/LOGIN';
COMMENT ON COLUMN audit_log.changes IS '变更内容摘要（JSON格式，敏感字段脱敏后记录）';
```

### 3.3 外部系统同步记录（external_sync_logs）

```sql
-- 外部系统同步日志（风控/OA/MDM/BPM 等系统交互记录）
CREATE TABLE external_sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_module VARCHAR(30) NOT NULL,
    source_record_id UUID,
    system_name VARCHAR(50) NOT NULL,
    sync_type VARCHAR(30) NOT NULL,
    request_payload JSONB,
    response_payload JSONB,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'syncing', 'success', 'failed', 'retrying')),
    retry_count SMALLINT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

COMMENT ON TABLE external_sync_logs IS '外部系统同步记录表';
COMMENT ON COLUMN external_sync_logs.source_module IS '来源模块：integrity/risk_monitor/ic_evaluation/special_audit/exit_audit/trade_secret/improvement';
COMMENT ON COLUMN external_sync_logs.system_name IS '目标系统：risk_control/OA/MDM/BPM/企查查/天眼查';
```

### 3.4 A2A 智能体通信任务表（a2a_tasks）

```sql
-- A2A 智能体间通信任务表
CREATE TABLE a2a_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_module VARCHAR(30) NOT NULL,
    source_record_id UUID,
    target_agent VARCHAR(50) NOT NULL,
    command VARCHAR(50) NOT NULL,
    request_payload JSONB,
    response_payload JSONB,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'accepted', 'processing', 'completed', 'failed')),
    callback_received BOOLEAN DEFAULT false,
    retry_count SMALLINT DEFAULT 0,
    max_retries SMALLINT DEFAULT 3,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

COMMENT ON TABLE a2a_tasks IS 'A2A 智能体间通信任务表';
COMMENT ON COLUMN a2a_tasks.target_agent IS '目标智能体：guibao(龟宝)/cicero(西塞罗)/porter(波特)';
COMMENT ON COLUMN a2a_tasks.command IS '操作指令：initiate_penalty_tracking/push_legal_review/push_supplier_deduction 等';
```

---

## 四、廉洁监察模块数据表

### 4.1 案件主表（cases）— 复用现有表结构

```sql
-- 案件主表（双轨来源：系统抓取 + 人工录入）
CREATE TABLE cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id VARCHAR(30) UNIQUE NOT NULL,
    case_code VARCHAR(50),
    fraud_source VARCHAR(30) NOT NULL,
    client VARCHAR(20) NOT NULL CHECK (client IN ('ecovacs', 'tineco', 'group')),

    -- 敏感字段（AES-256-GCM 加密存储）
    reported_staff_encrypted BYTEA,
    reported_suppliers_encrypted BYTEA,
    reported_dealers_encrypted BYTEA,
    fraud_tel_encrypted BYTEA,
    fraud_email_encrypted BYTEA,

    fraud_detail TEXT,
    proof TEXT,
    attachments JSONB,
    risk_control_case_id VARCHAR(50),

    current_stage VARCHAR(50),
    workflow_state JSONB,
    langgraph_thread_id VARCHAR(64),
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'investigating', 'disposing', 'enforcing', 'closed', 'transferred')),

    is_deleted BOOLEAN DEFAULT false,
    created_by VARCHAR(50),
    updated_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE cases IS '廉洁监察案件主表';
COMMENT ON COLUMN cases.task_id IS '任务ID，规则：来源缩写(GZ/SD/YX/ZN)+年月日+序号，如 GZ2025121102';
COMMENT ON COLUMN cases.fraud_source IS '舞弊来源：phone/email/wechat/agent/manual';
COMMENT ON COLUMN cases.client IS '事业部：ecovacs(科沃斯)/tineco(添可)/group(集团)';
COMMENT ON COLUMN cases.reported_staff_encrypted IS '被举报人员姓名（AES-256-GCM 加密）';
COMMENT ON COLUMN cases.reported_suppliers_encrypted IS '被举报供应商（AES-256-GCM 加密）';
COMMENT ON COLUMN cases.fraud_tel_encrypted IS '举报人电话（AES-256-GCM 加密）';
COMMENT ON COLUMN cases.fraud_email_encrypted IS '举报人邮箱（AES-256-GCM 加密）';
```

### 4.2 案件阶段流转表（case_stages）— 复用现有表结构

```sql
CREATE TABLE case_stages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    stage_name VARCHAR(50) NOT NULL,
    stage_order SMALLINT NOT NULL,
    ai_input JSONB,
    ai_output JSONB,
    knowledge_refs JSONB,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'pending_approval', 'approved', 'rejected', 'error')),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_info JSONB,
    retry_count SMALLINT DEFAULT 0
);

COMMENT ON TABLE case_stages IS '案件阶段流转记录表';
COMMENT ON COLUMN case_stages.stage_name IS '阶段名称：intake/investigation/analysis/disposition/enforcement/post_report';
COMMENT ON COLUMN case_stages.ai_output IS 'AI 输出内容（JSON格式：报告路径、决策结果、分流建议等）';
```

### 4.3 碳基守门记录表（human_approvals）— 复用现有表结构

```sql
CREATE TABLE human_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    stage_name VARCHAR(50) NOT NULL,
    reviewer_id VARCHAR(50) NOT NULL,
    action VARCHAR(20) NOT NULL CHECK (action IN ('approved', 'rejected', 'modified')),
    original_output JSONB,
    modified_output JSONB,
    modifications_summary TEXT,
    comment TEXT,
    signature VARCHAR(512),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE human_approvals IS '碳基守门记录表（不可篡改，审计追溯）';
COMMENT ON COLUMN human_approvals.signature IS '数字签名（HmacSHA256 防篡改）';
```

### 4.4 生成文档表（generated_documents）— 复用现有表结构

```sql
CREATE TABLE generated_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    doc_type VARCHAR(50) NOT NULL,
    stage_name VARCHAR(50),
    file_path VARCHAR(500),
    file_format VARCHAR(10) NOT NULL,
    version INT DEFAULT 1,
    is_confirmed BOOLEAN DEFAULT false,
    storage_bucket VARCHAR(100),
    storage_key VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE generated_documents IS '廉洁监察生成文档表（MinIO 对象存储）';
COMMENT ON COLUMN generated_documents.doc_type IS '文档类型：intake_report/investigation_plan/interview_outline/case_conclusion/monitoring_report/penalty_opinion/penalty_announcement/prosecution_letter/compensation_agreement/guidance_report';
```

---

## 五、风险监控模块数据表

### 5.1 风险规则表（risk_rules）

```sql
-- 风险规则库（AI 生成 + 人工审核）
CREATE TABLE risk_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_code VARCHAR(50) UNIQUE NOT NULL,
    business_unit VARCHAR(50),
    channel VARCHAR(50),
    format VARCHAR(50),
    department VARCHAR(100),
    position VARCHAR(100),
    personnel_info TEXT,
    business_cycle VARCHAR(100),
    level1_scene VARCHAR(100),
    level2_scene VARCHAR(100),
    level3_scene VARCHAR(100) NOT NULL,
    sql_statement TEXT NOT NULL,
    risk_level VARCHAR(10) NOT NULL CHECK (risk_level IN ('高', '中', '低')),
    threshold NUMERIC(12,4),
    monitor_frequency VARCHAR(20) NOT NULL CHECK (monitor_frequency IN ('hourly', 'daily', 'weekly', 'monthly')),
    monitor_business_unit VARCHAR(50),
    use_external_data BOOLEAN DEFAULT false,
    status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'testing', 'active', 'inactive', 'deprecated')),
    version INT DEFAULT 1,
    reviewed_by VARCHAR(50),
    reviewed_at TIMESTAMPTZ,
    created_by VARCHAR(50),
    updated_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE risk_rules IS '风险规则库表';
COMMENT ON COLUMN risk_rules.sql_statement IS 'AI 生成的风险扫描 SQL 语句（经测试环境验证可执行）';
COMMENT ON COLUMN risk_rules.monitor_frequency IS '监控频率：hourly/daily/weekly/monthly';
COMMENT ON COLUMN risk_rules.risk_level IS '风险等级：高/中/低';
```

### 5.2 风险分析主体表（risk_analysis_subjects）

```sql
-- 风险分析主体表（按主体合并重复预警）
CREATE TABLE risk_analysis_subjects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_code VARCHAR(50) UNIQUE NOT NULL,
    subject_name VARCHAR(200) NOT NULL,
    subject_type VARCHAR(30) NOT NULL CHECK (subject_type IN ('员工', '供应商', '经销商', '客户', '部门', '其他')),
    contact_info JSONB,
    merge_source_ids JSONB,
    risk_behavior TEXT,
    risk_business TEXT,
    impact_scope TEXT,
    involved_amount NUMERIC(18,2),
    analysis_report_path VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE risk_analysis_subjects IS '风险分析主体表（按联系方式/联系人/地址合并重复预警）';
COMMENT ON COLUMN risk_analysis_subjects.merge_source_ids IS '合并来源预警ID列表（JSON数组）';
```

### 5.3 风险预警表（risk_alerts）

```sql
-- 风险预警明细表
CREATE TABLE risk_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_code VARCHAR(50) UNIQUE NOT NULL,
    rule_id UUID NOT NULL REFERENCES risk_rules(id),
    analysis_subject_id UUID REFERENCES risk_analysis_subjects(id),
    business_unit VARCHAR(50),
    alert_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alert_data JSONB,
    risk_type VARCHAR(50) NOT NULL CHECK (risk_type IN ('合规风险', '舞弊风险', '商业秘密风险', '操作风险', '财务风险', '其他')),
    risk_level VARCHAR(10) NOT NULL CHECK (risk_level IN ('高', '中', '低')),
    severity VARCHAR(10) CHECK (severity IN ('严重', '一般', '轻微')),
    widespread VARCHAR(10) CHECK (widespread IN ('广泛', '局部', '孤立')),
    impact_degree TEXT,
    impact_amount NUMERIC(18,2),
    handling_suggestion TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'reviewing', 'confirmed', 'dismissed', 'pushed', 'closed')),
    reviewed_by VARCHAR(50),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE risk_alerts IS '风险预警明细表';
COMMENT ON COLUMN risk_alerts.alert_data IS '预警原始数据（JSON格式：异常明细、透视数据）';
COMMENT ON COLUMN risk_alerts.risk_type IS '风险类型：合规风险/舞弊风险/商业秘密风险/操作风险/财务风险/其他';
```

### 5.4 风险推送记录表（risk_push_records）

```sql
-- 风险推送记录表（推送至各处置模块）
CREATE TABLE risk_push_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id UUID NOT NULL REFERENCES risk_alerts(id),
    target_module VARCHAR(30) NOT NULL,
    target_record_id UUID,
    push_payload JSONB,
    push_status VARCHAR(20) DEFAULT 'pending'
        CHECK (push_status IN ('pending', 'pushed', 'received', 'processing', 'completed', 'failed', 'rejected')),
    callback_status VARCHAR(20) DEFAULT 'pending'
        CHECK (callback_status IN ('pending', 'disposed', 'rectifying', 'no_action', 'false_positive', 'completed')),
    callback_detail JSONB,
    push_at TIMESTAMPTZ,
    callback_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE risk_push_records IS '风险推送记录表';
COMMENT ON COLUMN risk_push_records.target_module IS '目标模块：integrity(廉洁监察)/ic_evaluation(内控评价)/trade_secret(商业秘密)/business_dept(业务部门)';
```

### 5.5 规则迭代记录表（rule_iteration_log）

```sql
-- 规则迭代优化记录表
CREATE TABLE rule_iteration_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES risk_rules(id),
    iteration_type VARCHAR(20) NOT NULL CHECK (iteration_type IN ('sql_update', 'threshold_update', 'frequency_update', 'deprecate', 'activate')),
    old_sql TEXT,
    new_sql TEXT,
    old_threshold NUMERIC(12,4),
    new_threshold NUMERIC(12,4),
    reason TEXT NOT NULL,
    operator_id VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE rule_iteration_log IS '风险规则迭代优化记录表';
COMMENT ON COLUMN rule_iteration_log.reason IS '迭代原因：误报优化/失效指标/阈值调整/SQL优化';
```

---

## 六、内控评价模块数据表

### 6.1 内控评价项目表（ic_evaluation_projects）

```sql
CREATE TABLE ic_evaluation_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code VARCHAR(50) UNIQUE NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    evaluation_purpose TEXT,
    audited_unit VARCHAR(200) NOT NULL,
    evaluation_period_start DATE NOT NULL,
    evaluation_period_end DATE NOT NULL,
    project_leader VARCHAR(100) NOT NULL,
    project_members JSONB,
    business_cycles JSONB,
    status VARCHAR(20) DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'in_progress', 'defects_confirmed', 'scored', 'reported', 'closed')),
    risk_control_project_id VARCHAR(50),
    created_by VARCHAR(50),
    updated_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ic_evaluation_projects IS '内控评价项目表（覆盖19个业务循环）';
COMMENT ON COLUMN ic_evaluation_projects.business_cycles IS '涉及业务循环列表（JSON数组，最多19个循环）';
```

### 6.2 风控矩阵表（ic_control_matrices）

```sql
CREATE TABLE ic_control_matrices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES ic_evaluation_projects(id) ON DELETE CASCADE,
    business_cycle VARCHAR(100) NOT NULL,
    level1_process VARCHAR(200),
    control_activity_id VARCHAR(50),
    control_target TEXT,
    key_control_point TEXT,
    test_procedure TEXT,
    schedule VARCHAR(100),
    assignee VARCHAR(100),
    design_test_basis_id UUID,
    execution_test_basis_id UUID,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'design_testing', 'execution_testing', 'completed')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ic_control_matrices IS '内控评价风控矩阵表';
COMMENT ON COLUMN ic_control_matrices.business_cycle IS '业务循环（共19个：采购付款/销售收款/存货管理/固定资产/资金管理/预算管理/合同管理/人力资源/信息系统/研发管理/生产管理/质量管理/资产管理/税务管理/投融资管理/关联交易/信息披露/社会责任/战略管理）';
```

### 6.3 内控设计缺陷表（ic_design_defects）

```sql
CREATE TABLE ic_design_defects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES ic_evaluation_projects(id) ON DELETE CASCADE,
    matrix_id UUID REFERENCES ic_control_matrices(id),
    business_cycle VARCHAR(100) NOT NULL,
    regulation_code VARCHAR(100),
    regulation_name VARCHAR(500),
    defect_type VARCHAR(50) NOT NULL,
    defect_description TEXT NOT NULL,
    score NUMERIC(5,2),
    identified_by VARCHAR(50),
    identified_at TIMESTAMPTZ DEFAULT NOW(),
    confirmed_by VARCHAR(50),
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ic_design_defects IS '内控设计缺陷表（制度设计有效性评价）';
COMMENT ON COLUMN ic_design_defects.defect_type IS '缺陷类型：制度缺失/制度冲突/制度滞后/职责不清/授权不当/控制缺失';
```

### 6.4 内控执行缺陷表（ic_execution_defects）

```sql
CREATE TABLE ic_execution_defects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES ic_evaluation_projects(id) ON DELETE CASCADE,
    matrix_id UUID REFERENCES ic_control_matrices(id),
    business_cycle VARCHAR(100) NOT NULL,
    defect_type VARCHAR(50) NOT NULL,
    defect_description TEXT NOT NULL,
    data_source TEXT,
    score NUMERIC(5,2),
    identified_by VARCHAR(50),
    identified_at TIMESTAMPTZ DEFAULT NOW(),
    confirmed_by VARCHAR(50),
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ic_execution_defects IS '内控执行缺陷表（流程执行有效性评价）';
COMMENT ON COLUMN ic_execution_defects.defect_type IS '缺陷类型：未按制度执行/执行不完整/执行偏差/记录缺失/审批缺失/超权限操作';
```

### 6.5 内控打分记录表（ic_score_records）

```sql
CREATE TABLE ic_score_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES ic_evaluation_projects(id) ON DELETE CASCADE,
    dimension VARCHAR(30) NOT NULL CHECK (dimension IN ('business_unit', 'business_cycle', 'position')),
    dimension_value VARCHAR(200) NOT NULL,
    design_score NUMERIC(5,2),
    execution_score NUMERIC(5,2),
    total_score NUMERIC(5,2),
    score_detail JSONB,
    scored_by VARCHAR(50),
    scored_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ic_score_records IS '内控评价打分记录表';
COMMENT ON COLUMN ic_score_records.dimension IS '评分维度：business_unit(事业部)/business_cycle(业务循环)/position(岗位)';
COMMENT ON COLUMN ic_score_records.score_detail IS '评分详情（JSON：各项得分明细、扣分原因）';
```

### 6.6 内控评价报告表（ic_evaluation_reports）

```sql
CREATE TABLE ic_evaluation_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES ic_evaluation_projects(id) ON DELETE CASCADE,
    report_type VARCHAR(30) NOT NULL CHECK (report_type IN ('draft', 'final', 'supplement')),
    report_path VARCHAR(500),
    storage_bucket VARCHAR(100),
    storage_key VARCHAR(500),
    version INT DEFAULT 1,
    is_final BOOLEAN DEFAULT false,
    report_summary TEXT,
    created_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ic_evaluation_reports IS '内控评价报告表';
COMMENT ON COLUMN ic_evaluation_reports.report_summary IS '报告摘要（包含整体结论、得分汇总、重要缺陷）';
```

---

## 七、专项审计模块数据表

### 7.1 专项审计项目表（audit_projects）

```sql
CREATE TABLE audit_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code VARCHAR(50) UNIQUE NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    audit_purpose TEXT NOT NULL,
    audit_focus TEXT,
    audit_period_start DATE NOT NULL,
    audit_period_end DATE NOT NULL,
    audited_unit VARCHAR(200) NOT NULL,
    project_leader VARCHAR(100) NOT NULL,
    project_members JSONB,
    risk_control_project_id VARCHAR(50),
    status VARCHAR(20) DEFAULT 'draft'
        CHECK (status IN ('draft', 'plan_approved', 'interviewing', 'checking', 'findings_confirmed', 'reported', 'closed')),
    created_by VARCHAR(50),
    updated_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE audit_projects IS '专项审计项目表';
COMMENT ON COLUMN audit_projects.audit_purpose IS '审计目的';
COMMENT ON COLUMN audit_projects.audit_focus IS '审计重点';
```

### 7.2 审计方案表（audit_plans）

```sql
CREATE TABLE audit_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES audit_projects(id) ON DELETE CASCADE,
    plan_type VARCHAR(30) NOT NULL CHECK (plan_type IN ('draft', 'interview', 'checklist', 'comprehensive')),
    audit_scope TEXT,
    audit_method TEXT,
    sample_strategy VARCHAR(200),
    sample_size INT,
    schedule TEXT,
    assignee VARCHAR(100),
    plan_content JSONB,
    version INT DEFAULT 1,
    is_approved BOOLEAN DEFAULT false,
    approved_by VARCHAR(50),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE audit_plans IS '专项审计方案表（包含审计范围、方法、抽样策略）';
```

### 7.3 审计访谈记录表（audit_interviews）

```sql
CREATE TABLE audit_interviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES audit_projects(id) ON DELETE CASCADE,
    interviewee_name VARCHAR(100),
    interviewee_department VARCHAR(100),
    interviewee_position VARCHAR(100),
    questionnaire JSONB,
    interview_result TEXT,
    interview_conclusion TEXT,
    interviewer VARCHAR(100),
    interview_date DATE,
    status VARCHAR(20) DEFAULT 'planned'
        CHECK (status IN ('planned', 'conducted', 'analyzing', 'completed')),
    attachment_paths JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE audit_interviews IS '专项审计访谈记录表';
COMMENT ON COLUMN audit_interviews.questionnaire IS '访谈问卷（JSON格式：问题列表、结构化提纲）';
COMMENT ON COLUMN audit_interviews.interview_result IS '访谈结果（语音转文字记录或文字记录）';
```

### 7.4 审计检查清单表（audit_checklists）

```sql
CREATE TABLE audit_checklists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES audit_projects(id) ON DELETE CASCADE,
    plan_id UUID REFERENCES audit_plans(id),
    category VARCHAR(100),
    check_item TEXT NOT NULL,
    data_source VARCHAR(200),
    check_method VARCHAR(100),
    expected_result TEXT,
    actual_result TEXT,
    is_issue_found BOOLEAN DEFAULT false,
    issue_ref_id UUID,
    checked_by VARCHAR(50),
    checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE audit_checklists IS '专项审计检查清单表（逐项检查记录）';
```

### 7.5 审计发现表（audit_findings）

```sql
CREATE TABLE audit_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES audit_projects(id) ON DELETE CASCADE,
    finding_code VARCHAR(50) UNIQUE NOT NULL,
    finding_description TEXT NOT NULL,
    business_cycle VARCHAR(100),
    risk_level VARCHAR(10) CHECK (risk_level IN ('高', '中', '低')),
    related_evidence JSONB,
    improvement_suggestion TEXT,
    status VARCHAR(20) DEFAULT 'draft'
        CHECK (status IN ('draft', 'pending_confirm', 'confirmed', 'disputed', 'closed')),
    confirmed_by VARCHAR(50),
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE audit_findings IS '专项审计发现表（问题清单）';
COMMENT ON COLUMN audit_findings.finding_code IS '审计发现编号（唯一，如 SA-2025-001）';
```

### 7.6 审计报告表（audit_reports）

```sql
CREATE TABLE audit_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES audit_projects(id) ON DELETE CASCADE,
    report_type VARCHAR(30) NOT NULL CHECK (report_type IN ('draft', 'final', 'supplement')),
    report_path VARCHAR(500),
    storage_bucket VARCHAR(100),
    storage_key VARCHAR(500),
    version INT DEFAULT 1,
    is_final BOOLEAN DEFAULT false,
    created_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE audit_reports IS '专项审计报告表';
```

---

## 八、离任审计模块数据表

### 8.1 离任审计项目表（exit_audit_projects）

```sql
CREATE TABLE exit_audit_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code VARCHAR(50) UNIQUE NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    business_unit VARCHAR(50) NOT NULL,
    exit_person_name_encrypted BYTEA,
    exit_person_id VARCHAR(50),
    exit_person_department VARCHAR(100),
    exit_person_position VARCHAR(100),
    entry_date DATE,
    last_working_day DATE NOT NULL,
    audit_period_start DATE NOT NULL,
    audit_period_end DATE NOT NULL,
    project_leader VARCHAR(100) NOT NULL,
    project_members JSONB,
    responsibility_config JSONB,
    risk_control_project_id VARCHAR(50),
    status VARCHAR(20) DEFAULT 'draft'
        CHECK (status IN ('draft', 'plan_approved', 'interviewing', 'data_collecting', 'findings_confirmed', 'reported', 'closed')),
    created_by VARCHAR(50),
    updated_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE exit_audit_projects IS '离任审计项目表';
COMMENT ON COLUMN exit_audit_projects.exit_person_name_encrypted IS '离任人员姓名（AES-256-GCM 加密）';
COMMENT ON COLUMN exit_audit_projects.responsibility_config IS '职责配置（JSON：来自MCP数据调用的岗位职责列表）';
COMMENT ON COLUMN exit_audit_projects.audit_period_start IS '审计期间起始：1年<本岗位时间≤5年→离职日期前3年；>5年→前1年';
```

### 8.2 离任审计方案表（exit_audit_plans）

```sql
CREATE TABLE exit_audit_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES exit_audit_projects(id) ON DELETE CASCADE,
    plan_type VARCHAR(30) NOT NULL CHECK (plan_type IN ('personal', 'business', 'comprehensive')),
    responsibility_scope JSONB,
    business_scope JSONB,
    audit_method TEXT,
    sample_strategy VARCHAR(200),
    sample_size INT,
    version INT DEFAULT 1,
    is_approved BOOLEAN DEFAULT false,
    approved_by VARCHAR(50),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE exit_audit_plans IS '离任审计方案表（个人审计方案 + 业务审计方案）';
COMMENT ON COLUMN exit_audit_plans.responsibility_scope IS '职责范围（JSON：匹配的岗位职责及检查项列表）';
COMMENT ON COLUMN exit_audit_plans.business_scope IS '业务范围（JSON：关联的业务内容及标准审计程序列表）';
```

### 8.3 离任审计访谈问卷表（exit_audit_questionnaires）

```sql
CREATE TABLE exit_audit_questionnaires (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES exit_audit_projects(id) ON DELETE CASCADE,
    questionnaire_type VARCHAR(30) CHECK (questionnaire_type IN ('exit_person', 'colleague', 'supervisor', 'subordinate')),
    questions JSONB NOT NULL,
    is_exit_person_confirmable BOOLEAN DEFAULT false,
    confirmed_by VARCHAR(50),
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE exit_audit_questionnaires IS '离任审计访谈问卷表';
COMMENT ON COLUMN exit_audit_questionnaires.is_exit_person_confirmable IS '离职人是否可确认该问卷';
```

### 8.4 资料需求清单表（exit_audit_data_requests）

```sql
CREATE TABLE exit_audit_data_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES exit_audit_projects(id) ON DELETE CASCADE,
    data_item TEXT NOT NULL,
    provider_name VARCHAR(100),
    provider_department VARCHAR(100),
    data_source VARCHAR(200),
    request_status VARCHAR(20) DEFAULT 'pending'
        CHECK (request_status IN ('pending', 'sent', 'provided', 'partial', 'overdue')),
    task_id UUID,
    provided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE exit_audit_data_requests IS '离任审计资料需求清单表';
COMMENT ON COLUMN exit_audit_data_requests.task_id IS '推送至任务中心的 A2A 任务ID（同一人员多条资料合并发送）';
```

### 8.5 离任审计发现表（exit_audit_findings）

```sql
CREATE TABLE exit_audit_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES exit_audit_projects(id) ON DELETE CASCADE,
    finding_category VARCHAR(20) NOT NULL CHECK (finding_category IN ('personal', 'business')),
    finding_code VARCHAR(50) UNIQUE NOT NULL,
    finding_description TEXT NOT NULL,
    risk_level VARCHAR(10) CHECK (risk_level IN ('高', '中', '低')),
    related_evidence JSONB,
    improvement_suggestion TEXT,
    status VARCHAR(20) DEFAULT 'draft'
        CHECK (status IN ('draft', 'pending_confirm', 'confirmed', 'disputed', 'closed')),
    confirmed_by VARCHAR(50),
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE exit_audit_findings IS '离任审计发现表';
COMMENT ON COLUMN exit_audit_findings.finding_category IS '发现类别：personal(个人层面：商业秘密泄露/个人报销/样机使用/关联公司/资产使用）; business(业务层面：流程漏洞/制度缺陷/经济损失)';
```

### 8.6 离任审计报告表（exit_audit_reports）

```sql
CREATE TABLE exit_audit_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES exit_audit_projects(id) ON DELETE CASCADE,
    report_type VARCHAR(30) NOT NULL CHECK (report_type IN ('personal', 'business', 'comprehensive')),
    report_path VARCHAR(500),
    storage_bucket VARCHAR(100),
    storage_key VARCHAR(500),
    version INT DEFAULT 1,
    is_final BOOLEAN DEFAULT false,
    created_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE exit_audit_reports IS '离任审计报告表（个人报告 + 业务报告 + 总报告）';
```

---

## 九、行为风险模块数据表

### 9.1 行为风险分析报告表（behavior_risk_analysis_reports）

```sql
-- 行为风险分析报告表
CREATE TABLE behavior_risk_analysis_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_code VARCHAR(50) UNIQUE NOT NULL,
    business_unit VARCHAR(50),
    department VARCHAR(100),
    position VARCHAR(100),
    personnel_name VARCHAR(100),
    role_type VARCHAR(50),
    analysis_period_start DATE NOT NULL,
    analysis_period_end DATE NOT NULL,
    behavior_data_sources JSONB,
    abnormal_behaviors JSONB,
    risk_level VARCHAR(10) CHECK (risk_level IN ('高', '中', '低')),
    correlation_analysis TEXT,
    report_path VARCHAR(500),
    storage_bucket VARCHAR(100),
    storage_key VARCHAR(500),
    status VARCHAR(20) DEFAULT 'draft'
        CHECK (status IN ('draft', 'analyzing', 'completed', 'reviewed')),
    created_by VARCHAR(50),
    reviewed_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);

COMMENT ON TABLE behavior_risk_analysis_reports IS '行为风险分析报告表';
COMMENT ON COLUMN behavior_risk_analysis_reports.behavior_data_sources IS '行为数据来源（JSON数组：各监管系统名称及数据范围）';
COMMENT ON COLUMN behavior_risk_analysis_reports.abnormal_behaviors IS '异常行为列表（JSON数组：行为类型/描述/涉及数据/风险等级）';
```

### 9.2 行为风险管理报告表（behavior_risk_management_reports）

```sql
-- 行为风险管理情况报告表（月度生成）
CREATE TABLE behavior_risk_management_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_period VARCHAR(20) NOT NULL,
    report_scope VARCHAR(100) NOT NULL,
    report_type VARCHAR(30) NOT NULL DEFAULT 'monthly',
    monitoring_systems_coverage JSONB,
    missing_coverage JSONB,
    data_quality_assessment JSONB,
    high_risk_behaviors JSONB,
    high_frequency_behaviors JSONB,
    optimization_suggestions TEXT,
    report_path VARCHAR(500),
    storage_bucket VARCHAR(100),
    storage_key VARCHAR(500),
    created_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE behavior_risk_management_reports IS '行为风险管理情况报告表（月度生成）';
COMMENT ON COLUMN behavior_risk_management_reports.monitoring_systems_coverage IS '监管系统覆盖范围（JSON：已接入系统清单及覆盖情况）';
COMMENT ON COLUMN behavior_risk_management_reports.missing_coverage IS '缺失范围（JSON：尚未覆盖的监管盲区）';
COMMENT ON COLUMN behavior_risk_management_reports.data_quality_assessment IS '数据质量评估（JSON：完整性/及时性/准确性）';
COMMENT ON COLUMN behavior_risk_management_reports.high_risk_behaviors IS '高风险行为展示（JSON：高风险行为事件汇总与详情）';
COMMENT ON COLUMN behavior_risk_management_reports.high_frequency_behaviors IS '高频行为问题展示（JSON：分类统计与趋势分析）';
```

### 9.3 行为风险索引

```sql
CREATE INDEX idx_brar_bu ON behavior_risk_analysis_reports(business_unit, created_at DESC);
CREATE INDEX idx_brar_person ON behavior_risk_analysis_reports(personnel_name, created_at DESC);
CREATE INDEX idx_brar_status ON behavior_risk_analysis_reports(status, created_at DESC);
CREATE INDEX idx_brmr_period ON behavior_risk_management_reports(report_period, report_scope);
```

---

## 十、商业秘密模块数据表

### 10.1 商业秘密事项表（trade_secret_items）

```sql
CREATE TABLE trade_secret_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_code VARCHAR(50) UNIQUE NOT NULL,
    item_name VARCHAR(200) NOT NULL,
    secret_type VARCHAR(50) NOT NULL,
    secret_level VARCHAR(20) NOT NULL CHECK (secret_level IN ('核心商密', '普通商密', '内部信息')),
    business_unit VARCHAR(50) NOT NULL,
    department VARCHAR(100),
    project_name VARCHAR(200),
    file_list JSONB NOT NULL,
    secret_personnel_scope JSONB,
    storage_certificate_no VARCHAR(100),
    keeper_id VARCHAR(50),
    keeper_name VARCHAR(100),
    risk_control_item_id VARCHAR(50),
    status VARCHAR(20) DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'reviewing', 'approved', 'rejected')),
    pre_review_count INT DEFAULT 0,
    created_by VARCHAR(50),
    updated_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE trade_secret_items IS '商业秘密事项表（对应《商业秘密信息表》+《涉密文件清单》）';
COMMENT ON COLUMN trade_secret_items.file_list IS '涉密文件清单（JSON数组：文件名、文件类型、存储位置）';
COMMENT ON COLUMN trade_secret_items.secret_personnel_scope IS '涉密人员范围（JSON数组：人员ID、姓名、部门）';
```

### 10.2 定密评审记录表（trade_secret_reviews）

```sql
CREATE TABLE trade_secret_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_code VARCHAR(50) UNIQUE NOT NULL,
    item_id UUID NOT NULL REFERENCES trade_secret_items(id),
    review_organization VARCHAR(100),
    review_period VARCHAR(50),
    review_workflow_id VARCHAR(50),
    review_result JSONB,
    reviewer_id VARCHAR(50),
    review_status VARCHAR(20) DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'in_progress', 'completed', 'returned')),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE trade_secret_reviews IS '定密评审记录表';
COMMENT ON COLUMN trade_secret_reviews.review_result IS '评审结果（JSON：涉密信息类型/密级/文件清单/涉密人员范围/存证编号 的完整性/合理性/准确性评价）';
```

### 10.3 定密建议（预审）表（trade_secret_suggestions）

```sql
CREATE TABLE trade_secret_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id UUID NOT NULL REFERENCES trade_secret_items(id),
    suggestion_type VARCHAR(30) NOT NULL CHECK (suggestion_type IN ('pre_review', 'keeper_suggestion')),
    pre_review_report_path VARCHAR(500),
    suggestion_content JSONB,
    keeper_feedback VARCHAR(20) CHECK (keeper_feedback IN ('accepted', 'partial', 'rejected')),
    keeper_feedback_detail TEXT,
    feedback_status VARCHAR(20) DEFAULT 'pending'
        CHECK (feedback_status IN ('pending', 'submitted', 'none')),
    storage_bucket VARCHAR(100),
    storage_key VARCHAR(500),
    created_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE trade_secret_suggestions IS '定密建议/预审表（保密员定密预审）';
COMMENT ON COLUMN trade_secret_suggestions.suggestion_content IS '建议内容（JSON：前期已定密信息评审结果 + 建议定密内容，格式对齐《商业秘密信息表》模板）';
COMMENT ON COLUMN trade_secret_suggestions.keeper_feedback IS '保密员反馈：accepted(全部接受)/partial(部分接受)/rejected(不接受)';
```

### 10.4 商业秘密管理报告表（trade_secret_management_reports）

```sql
CREATE TABLE trade_secret_management_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_period VARCHAR(20) NOT NULL,
    report_scope VARCHAR(100) NOT NULL,
    report_type VARCHAR(30) NOT NULL DEFAULT 'monthly',
    report_path VARCHAR(500),
    storage_bucket VARCHAR(100),
    storage_key VARCHAR(500),
    statistics_data JSONB,
    created_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE trade_secret_management_reports IS '商业秘密管理情况报告表（月度生成）';
COMMENT ON COLUMN trade_secret_management_reports.statistics_data IS '统计数据（JSON：总定密组织数量/已定密组织数量/占比/总流程数/总信息条数/期间进度等）';
COMMENT ON COLUMN trade_secret_management_reports.report_scope IS '总结范围：全集团/某事业部/某部门/某项目';
```

---

## 十一、持续改善模块数据表

### 11.1 持续改善问题主表（improvement_issues）

```sql
-- 持续改善问题主表（统一承接所有模块发现的问题，30+字段固定表头）
CREATE TABLE improvement_issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_code VARCHAR(50) UNIQUE NOT NULL,
    project_year VARCHAR(10),
    business_unit VARCHAR(50),
    source_module VARCHAR(30) NOT NULL
        CHECK (source_module IN ('ic_evaluation', 'integrity', 'trade_secret', 'behavior_risk', 'special_audit', 'exit_audit', 'business_assigned')),
    source_project_code VARCHAR(50),
    source_project_name VARCHAR(200),
    source_finding_code VARCHAR(50),
    finding_description TEXT NOT NULL,
    business_cycle VARCHAR(100),
    improvement_suggestion TEXT,
    project_leader VARCHAR(100),
    risk_control_follower VARCHAR(100),
    responsible_department VARCHAR(100) NOT NULL,
    responsible_person VARCHAR(100) NOT NULL,
    improvement_plan_requirement TEXT,
    planned_completion_date DATE NOT NULL,
    ai_review_plan_date DATE,
    ai_review_plan_opinion TEXT,
    audit_review_plan_opinion TEXT,
    audit_review_plan_date DATE,
    actual_completion_date DATE,
    is_overdue BOOLEAN DEFAULT false,
    overdue_days INT DEFAULT 0,
    ai_review_opinion TEXT,
    ai_review_date DATE,
    audit_review_opinion TEXT,
    reviewer VARCHAR(100),
    ai_review_evidence_date DATE,
    ai_review_evidence_opinion TEXT,
    audit_review_evidence_date DATE,
    response_count INT DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'pending_push'
        CHECK (status IN (
            'pending_push', 'pending_plan', 'plan_pending_approval',
            'pending_evidence', 'pending_review', 'completed',
            'returned_for_rework', 'voided'
        )),
    direct_recovery_amount NUMERIC(18,2) DEFAULT 0,
    indirect_recovery_amount NUMERIC(18,2) DEFAULT 0,
    personnel_handling TEXT,
    is_voided BOOLEAN DEFAULT false,
    void_reason TEXT,
    created_by VARCHAR(50),
    updated_by VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE improvement_issues IS '持续改善问题主表（30+字段固定表头，统一承接所有审计发现问题）';
COMMENT ON COLUMN improvement_issues.source_module IS '来源模块：ic_evaluation(内控评价)/integrity(廉洁监察)/trade_secret(商业秘密)/behavior_risk(行为风险)/special_audit(专项审计)/exit_audit(离任审计)/business_assigned(业务交办)';
COMMENT ON COLUMN improvement_issues.status IS '状态：pending_push(问题待推送)/pending_plan(计划待提交)/plan_pending_approval(计划待审批)/pending_evidence(整改答复待提交)/pending_review(已整改待复核)/completed(整改完成)/returned_for_rework(退回重改)/voided(已作废)';
```

### 11.2 整改计划表（improvement_plans）

```sql
CREATE TABLE improvement_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES improvement_issues(id) ON DELETE CASCADE,
    plan_description TEXT NOT NULL,
    attachment_paths JSONB,
    submitted_by VARCHAR(100),
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    ai_first_review_opinion TEXT,
    audit_review_opinion TEXT,
    review_status VARCHAR(20) DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'ai_reviewed', 'approved', 'rejected')),
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE improvement_plans IS '整改计划/方案表';
COMMENT ON COLUMN improvement_plans.review_status IS '审核状态：pending(待审核)/ai_reviewed(AI初审完成)/approved(审核通过)/rejected(审核不通过)';
```

### 11.3 整改任务表（improvement_tasks）

```sql
CREATE TABLE improvement_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES improvement_issues(id) ON DELETE CASCADE,
    task_name VARCHAR(200) NOT NULL,
    task_description TEXT,
    assignee_id VARCHAR(50),
    assignee_name VARCHAR(100),
    assignee_department VARCHAR(100),
    due_date DATE,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'submitted', 'completed', 'overdue')),
    push_record_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE improvement_tasks IS '整改任务表（下发至任务中心）';
COMMENT ON COLUMN improvement_tasks.push_record_id IS '任务推送记录ID（A2A 关联）';
```

### 11.4 整改证据表（improvement_evidence）

```sql
CREATE TABLE improvement_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES improvement_issues(id) ON DELETE CASCADE,
    evidence_type VARCHAR(50),
    evidence_description TEXT,
    attachment_paths JSONB,
    storage_bucket VARCHAR(100),
    storage_keys JSONB,
    submitted_by VARCHAR(100),
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE improvement_evidence IS '整改证据/材料表';
COMMENT ON COLUMN improvement_evidence.evidence_type IS '证据类型：文档/截图/数据报表/审批记录/培训记录/制度文件';
```

### 11.5 整改复核记录表（improvement_reviews）

```sql
CREATE TABLE improvement_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES improvement_issues(id) ON DELETE CASCADE,
    review_type VARCHAR(20) NOT NULL CHECK (review_type IN ('ai_plan_review', 'human_plan_review', 'ai_evidence_review', 'human_evidence_review')),
    review_result VARCHAR(20) NOT NULL CHECK (review_result IN ('pass', 'fail', 'conditionally_pass')),
    review_comment TEXT,
    return_reason TEXT,
    reviewer_id VARCHAR(100),
    reviewed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE improvement_reviews IS '整改复核记录表（AI初审 + 人工复审，全流程留痕）';
COMMENT ON COLUMN improvement_reviews.return_reason IS '退回原因（复核不通过时必填）';
COMMENT ON COLUMN improvement_reviews.review_type IS '复核类型：ai_plan_review(AI计划复核)/human_plan_review(人工计划复核)/ai_evidence_review(AI证据复核)/human_evidence_review(人工证据复核)';
```

---

## 十二、知识库数据模型

### 12.1 知识库文档表（knowledge_documents）

```sql
-- 知识库文档主表（pgvector 向量存储）
-- 前置条件：CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_type VARCHAR(30) NOT NULL
        CHECK (kb_type IN (
            'intake', 'investigation', 'analysis', 'disposition', 'enforcement',
            'risk_monitor', 'ic_evaluation', 'special_audit', 'exit_audit',
            'trade_secret', 'improvement', 'behavior_risk', 'common'
        )),
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64),
    embedding VECTOR(1536),
    metadata_ JSONB,
    source_path VARCHAR(500),
    chunk_index INT DEFAULT 1,
    total_chunks INT DEFAULT 1,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE knowledge_documents IS '知识库文档主表（pgvector 向量存储，按 kb_type 分区索引）';
COMMENT ON COLUMN knowledge_documents.kb_type IS '知识库类型：intake(初筛)/investigation(调查方案)/analysis(分析报告)/disposition(处置分流)/enforcement(处罚执行)/risk_monitor(风险监控)/ic_evaluation(内控评价)/special_audit(专项审计)/exit_audit(离任审计)/trade_secret(商业秘密)/improvement(持续改善)/behavior_risk(行为风险)/common(公共)';
COMMENT ON COLUMN knowledge_documents.embedding IS '文本向量（维度1536，text-embedding-3-large 模型）';
COMMENT ON COLUMN knowledge_documents.metadata_ IS '元数据（JSON：作者/来源/标签/生效日期/失效日期/适用模块）';
COMMENT ON COLUMN knowledge_documents.chunk_index IS '分块序号（chunk_size=1000, overlap=200）';

-- 向量索引：按知识库类型分区建立 IVFFlat 索引
-- 前置：每个 kb_type 分区数据量 > 1000 时 IVFFlat 效果最佳
CREATE INDEX idx_kb_embedding_intake
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'intake' AND is_active;

CREATE INDEX idx_kb_embedding_investigation
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'investigation' AND is_active;

CREATE INDEX idx_kb_embedding_analysis
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'analysis' AND is_active;

CREATE INDEX idx_kb_embedding_disposition
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'disposition' AND is_active;

CREATE INDEX idx_kb_embedding_enforcement
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'enforcement' AND is_active;

CREATE INDEX idx_kb_embedding_risk_monitor
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'risk_monitor' AND is_active;

CREATE INDEX idx_kb_embedding_ic_evaluation
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'ic_evaluation' AND is_active;

CREATE INDEX idx_kb_embedding_special_audit
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'special_audit' AND is_active;

CREATE INDEX idx_kb_embedding_exit_audit
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'exit_audit' AND is_active;

CREATE INDEX idx_kb_embedding_trade_secret
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'trade_secret' AND is_active;

CREATE INDEX idx_kb_embedding_improvement
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'improvement' AND is_active;

CREATE INDEX idx_kb_embedding_behavior_risk
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'behavior_risk' AND is_active;

CREATE INDEX idx_kb_embedding_common
    ON knowledge_documents USING ivfflat (embedding vector_cosine_ops)
    WHERE kb_type = 'common' AND is_active;
```

### 12.2 知识库各阶段内容配置

| kb_type | 知识库内容 | 向量维度 | 预估文档量 |
|---------|-----------|---------|-----------|
| `intake` | 组织架构、人员名单、岗位职责、客户/供应商清单、内部管理制度、外部法律法规 | 1536 | 500-2000 |
| `investigation` | 类似案件法条、业务系统信息、过往舞弊案件及处理方案 | 1536 | 200-1000 |
| `analysis` | 过往调查报告、报告模板及格式要求 | 1536 | 100-500 |
| `disposition` | 制度文件、追责审批流程、组织架构及分权 | 1536 | 300-1500 |
| `enforcement` | 黑名单制度、赔偿协议模板、处罚公告模板、人员架构 | 1536 | 100-500 |
| `risk_monitor` | 风险清单知识库、历史风险案例、处置结果、工商/舆情数据 | 1536 | 500-3000 |
| `ic_evaluation` | 制度库、内控评价标准矩阵、内控法规、历史缺陷清单、历史改善建议 | 1536 | 500-3000 |
| `special_audit` | 历史审计方案、审计发现清单、访谈模板、业务系统数据字典 | 1536 | 300-2000 |
| `exit_audit` | 历史审计方案、审计发现清单、业务循环数据字典、报告模板 | 1536 | 200-1500 |
| `trade_secret` | 保密员/保密项目清单、制度文件、外部法律法规、侵权案例、前期评审结果 | 1536 | 300-2000 |
| `improvement` | 历史整改记录、整改方案模板、复核标准、报表模板 | 1536 | 200-1000 |
| `behavior_risk` | 行为数据字典、员工档案模板、法律法规、历史分析结果 | 1536 | 100-500 |
| `common` | 公共制度、岗位职责模板、通用法规、数据字典 | 1536 | 100-500 |

### 12.3 知识库文档同步流程

```
本地/远程文档(docx/xlsx/pdf/txt/csv)
    │
    ├─→ 解析提取纯文本（去除格式/表格/图片OCR）
    │
    ├─→ 分块处理（chunk_size=1000字符, overlap=200字符）
    │
    ├─→ 计算 content_hash（SHA-256）→ 与已有 hash 比对 → 增量更新
    │
    ├─→ 调用 Embedding API（text-embedding-3-large / bge-large-zh-v1.5）
    │
    └─→ 存入 knowledge_documents 表（按 kb_type 分区索引）
```

---

## 十三、数据安全设计

### 13.1 加密方案（AES-256-GCM）

| 加密字段 | 所属表 | 加密算法 | 密钥管理 |
|---------|--------|---------|---------|
| reported_staff_encrypted | cases | AES-256-GCM | 环境变量 `ENCRYPTION_KEY`（32字节Base64） |
| reported_suppliers_encrypted | cases | AES-256-GCM | 同上 |
| reported_dealers_encrypted | cases | AES-256-GCM | 同上 |
| fraud_tel_encrypted | cases | AES-256-GCM | 同上 |
| fraud_email_encrypted | cases | AES-256-GCM | 同上 |
| exit_person_name_encrypted | exit_audit_projects | AES-256-GCM | 同上 |

```sql
-- 加密存储示例说明（应用层处理，非数据库层）
-- 存储类型：BYTEA（二进制）
-- 加密流程：明文 → AES-256-GCM(Nonce+密文+Tag) → Base64编码 → BYTEA
-- 解密流程：BYTEA → Base64解码 → AES-256-GCM解密 → 明文
-- 密钥轮换：支持多版本密钥，新增字段 key_version 标记加密密钥版本
```

### 13.2 敏感字段脱敏规则（查询层）

| 字段 | 脱敏规则 | 示例 |
|------|---------|------|
| 手机号 | 保留前3后4，中间4位替换为 `****` | 138****1234 |
| 邮箱 | 保留首字符和@后域名，中间替换为 `***` | z***@ecovacs.com |
| 姓名 | 保留姓，名替换为 `*` | 张* |
| AD账号 | 保留前3位，其余替换为 `***` | jia*** |
| 身份证号 | 保留前6后4，中间替换为 `********` | 320500********1234 |

### 13.3 审计安全要求（等保二级）

| 要求项 | 实现方案 |
|--------|---------|
| **身份鉴别** | JWT 令牌（8h过期），登录失败 5 次锁定 30 分钟，刷新令牌 7 天 |
| **访问控制** | RBAC 三层角色（group/ecovacs/tineco）+ 应用层行级数据过滤 |
| **安全审计** | 全量操作记录至 audit_log，保留 >= 6 个月，仅追加不可删除 |
| **通信保密性** | HTTPS + 内网 mTLS（服务间通信） |
| **数据保密性** | 个人信息列级 AES-256-GCM 加密，日志中敏感字段脱敏 |
| **软件容错** | 关键节点失败自动重试 3 次，降级策略：告警 + 人工接管 |
| **资源控制** | API 速率限制 100 req/min/用户，文件上传限 50MB |
| **数据备份** | PG 每日全量备份 + WAL 连续归档，保留 30 天 |
| **剩余信息保护** | 用户登出清除 Session，敏感字段不写入应用日志 |
| **数字签名** | human_approvals 表 signature 字段采用 HmacSHA256 防篡改签名 |

### 13.4 软删除策略

以下表采用软删除（`is_deleted = true`），禁止物理删除：

| 表名 | 软删除字段 | 说明 |
|------|-----------|------|
| cases | `is_deleted` | 案件不可物理删除 |
| improvement_issues | `is_voided` | 问题作废需填写 void_reason |
| risk_rules | `status = 'deprecated'` | 规则作废保留历史 |
| knowledge_documents | `is_active` | 文档逻辑删除后可恢复 |

---

## 十四、索引策略

### 14.1 索引设计总原则

1. **主键索引**：所有表 UUID 主键自动建立 B-Tree 唯一索引
2. **外键索引**：所有外键列建立 B-Tree 索引（加速 JOIN）
3. **查询条件索引**：高频 WHERE/ORDER BY 列的复合索引
4. **部分索引**：软删除表使用 `WHERE NOT is_deleted` 或 `WHERE is_active` 缩小索引体积
5. **向量索引**：pgvector 使用 IVFFlat 索引，按 kb_type 分区
6. **全文检索**：`finding_description`、`fraud_detail` 等长文本字段使用 GIN 索引 + `tsvector`

### 14.2 各模块索引清单

#### 共享基础表索引

```sql
-- users
CREATE INDEX idx_users_role ON users(role) WHERE is_active;
CREATE INDEX idx_users_username ON users(username);

-- audit_log
CREATE INDEX idx_audit_operator ON audit_log(operator_id, created_at DESC);
CREATE INDEX idx_audit_target ON audit_log(target_table, target_id);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);
CREATE INDEX idx_audit_operation ON audit_log(operation, created_at DESC);

-- external_sync_logs
CREATE INDEX idx_sync_source ON external_sync_logs(source_module, source_record_id);
CREATE INDEX idx_sync_system ON external_sync_logs(system_name, status);
CREATE INDEX idx_sync_created ON external_sync_logs(created_at DESC);

-- a2a_tasks
CREATE INDEX idx_a2a_source ON a2a_tasks(source_module, source_record_id);
CREATE INDEX idx_a2a_target ON a2a_tasks(target_agent, status);
CREATE INDEX idx_a2a_created ON a2a_tasks(created_at DESC);
```

#### 廉洁监察索引

```sql
-- cases
CREATE INDEX idx_cases_client ON cases(client) WHERE NOT is_deleted;
CREATE INDEX idx_cases_status ON cases(status) WHERE NOT is_deleted;
CREATE INDEX idx_cases_stage ON cases(current_stage) WHERE NOT is_deleted;
CREATE INDEX idx_cases_task_id ON cases(task_id);
CREATE INDEX idx_cases_risk_ctrl ON cases(risk_control_case_id);
CREATE INDEX idx_cases_created ON cases(created_at DESC) WHERE NOT is_deleted;

-- case_stages
CREATE INDEX idx_stages_case ON case_stages(case_id, stage_order);
CREATE INDEX idx_stages_status ON case_stages(status, started_at);

-- human_approvals
CREATE INDEX idx_approvals_case ON human_approvals(case_id, stage_name);
CREATE INDEX idx_approvals_reviewer ON human_approvals(reviewer_id, created_at DESC);

-- generated_documents
CREATE INDEX idx_docs_case ON generated_documents(case_id, doc_type);
CREATE INDEX idx_docs_stage ON generated_documents(stage_name, doc_type);
```

#### 风险监控索引

```sql
-- risk_rules
CREATE INDEX idx_rules_bu ON risk_rules(monitor_business_unit, status);
CREATE INDEX idx_rules_level ON risk_rules(risk_level, status);
CREATE INDEX idx_rules_freq ON risk_rules(monitor_frequency, status);
CREATE INDEX idx_rules_code ON risk_rules(rule_code);
CREATE INDEX idx_rules_active ON risk_rules(status, created_at DESC) WHERE status = 'active';

-- risk_alerts
CREATE INDEX idx_alerts_rule ON risk_alerts(rule_id, alert_time DESC);
CREATE INDEX idx_alerts_subject ON risk_alerts(analysis_subject_id);
CREATE INDEX idx_alerts_status ON risk_alerts(status, alert_time DESC);
CREATE INDEX idx_alerts_type_level ON risk_alerts(risk_type, risk_level, alert_time DESC);
CREATE INDEX idx_alerts_bu_time ON risk_alerts(business_unit, alert_time DESC);

-- risk_analysis_subjects
CREATE INDEX idx_subjects_code ON risk_analysis_subjects(subject_code);
CREATE INDEX idx_subjects_type ON risk_analysis_subjects(subject_type);

-- risk_push_records
CREATE INDEX idx_push_alert ON risk_push_records(alert_id);
CREATE INDEX idx_push_module ON risk_push_records(target_module, push_status);
CREATE INDEX idx_push_callback ON risk_push_records(callback_status);

-- rule_iteration_log
CREATE INDEX idx_rule_iter ON rule_iteration_log(rule_id, created_at DESC);
CREATE INDEX idx_rule_iter_type ON rule_iteration_log(iteration_type, created_at DESC);
```

#### 内控评价索引

```sql
-- ic_evaluation_projects
CREATE INDEX idx_ic_proj_status ON ic_evaluation_projects(status, created_at DESC);
CREATE INDEX idx_ic_proj_unit ON ic_evaluation_projects(audited_unit, created_at DESC);
CREATE INDEX idx_ic_proj_code ON ic_evaluation_projects(project_code);

-- ic_control_matrices
CREATE INDEX idx_ic_matrix_proj ON ic_control_matrices(project_id, business_cycle);
CREATE INDEX idx_ic_matrix_cycle ON ic_control_matrices(business_cycle, status);

-- ic_design_defects / ic_execution_defects
CREATE INDEX idx_ic_dd_proj ON ic_design_defects(project_id, business_cycle);
CREATE INDEX idx_ic_ed_proj ON ic_execution_defects(project_id, business_cycle);

-- ic_score_records
CREATE INDEX idx_ic_score_proj ON ic_score_records(project_id, dimension);
CREATE INDEX idx_ic_score_dim ON ic_score_records(dimension, dimension_value);

-- ic_evaluation_reports
CREATE INDEX idx_ic_rpt_proj ON ic_evaluation_reports(project_id, version DESC);
```

#### 专项审计索引

```sql
CREATE INDEX idx_ap_status ON audit_projects(status, created_at DESC);
CREATE INDEX idx_ap_unit ON audit_projects(audited_unit);
CREATE INDEX idx_aplan_proj ON audit_plans(project_id, plan_type);
CREATE INDEX idx_ainterview_proj ON audit_interviews(project_id, interview_date);
CREATE INDEX idx_achecklist_proj ON audit_checklists(project_id, is_issue_found);
CREATE INDEX idx_afinding_proj ON audit_findings(project_id, risk_level);
CREATE INDEX idx_afinding_code ON audit_findings(finding_code);
CREATE INDEX idx_arpt_proj ON audit_reports(project_id, is_final);
```

#### 离任审计索引

```sql
CREATE INDEX idx_eap_status ON exit_audit_projects(status, created_at DESC);
CREATE INDEX idx_eap_person ON exit_audit_projects(exit_person_id);
CREATE INDEX idx_eap_bu ON exit_audit_projects(business_unit);
CREATE INDEX idx_eaplan_proj ON exit_audit_plans(project_id, plan_type);
CREATE INDEX idx_eaq_proj ON exit_audit_questionnaires(project_id, questionnaire_type);
CREATE INDEX idx_eadr_proj ON exit_audit_data_requests(project_id, request_status);
CREATE INDEX idx_eaf_proj ON exit_audit_findings(project_id, finding_category);
CREATE INDEX idx_eaf_code ON exit_audit_findings(finding_code);
CREATE INDEX idx_earpt_proj ON exit_audit_reports(project_id, is_final);
```

#### 商业秘密索引

```sql
CREATE INDEX idx_tsi_bu ON trade_secret_items(business_unit, status);
CREATE INDEX idx_tsi_level ON trade_secret_items(secret_level, status);
CREATE INDEX idx_tsi_keeper ON trade_secret_items(keeper_id);
CREATE INDEX idx_tsr_item ON trade_secret_reviews(item_id, review_status);
CREATE INDEX idx_tsr_status ON trade_secret_reviews(review_status, created_at DESC);
CREATE INDEX idx_tss_item ON trade_secret_suggestions(item_id, created_at DESC);
CREATE INDEX idx_tsmr_period ON trade_secret_management_reports(report_period, report_scope);
```

#### 持续改善索引

```sql
CREATE INDEX idx_ii_source ON improvement_issues(source_module, source_project_code);
CREATE INDEX idx_ii_status ON improvement_issues(status, planned_completion_date);
CREATE INDEX idx_ii_dept ON improvement_issues(responsible_department, status);
CREATE INDEX idx_ii_person ON improvement_issues(responsible_person, status);
CREATE INDEX idx_ii_overdue ON improvement_issues(is_overdue, overdue_days) WHERE is_overdue = true;
CREATE INDEX idx_ii_code ON improvement_issues(issue_code);
CREATE INDEX idx_ii_year_bu ON improvement_issues(project_year, business_unit);
CREATE INDEX idx_ip_issue ON improvement_plans(issue_id, review_status);
CREATE INDEX idx_it_issue ON improvement_tasks(issue_id, status);
CREATE INDEX idx_it_assignee ON improvement_tasks(assignee_id, status);
CREATE INDEX idx_ie_issue ON improvement_evidence(issue_id, submitted_at DESC);
CREATE INDEX idx_ir_issue ON improvement_reviews(issue_id, review_type, reviewed_at DESC);
```

#### 知识库索引

```sql
-- 非向量索引
CREATE INDEX idx_kb_type ON knowledge_documents(kb_type) WHERE is_active;
CREATE INDEX idx_kb_hash ON knowledge_documents(kb_type, content_hash);
CREATE INDEX idx_kb_title ON knowledge_documents USING gin (to_tsvector('simple', title)) WHERE is_active;
CREATE INDEX idx_kb_content ON knowledge_documents USING gin (to_tsvector('simple', content)) WHERE is_active;
CREATE INDEX idx_kb_updated ON knowledge_documents(kb_type, updated_at DESC) WHERE is_active;
```

---

## 十五、数据流转设计

### 15.1 模块间数据流转总览

```
                         风险监控（risk_rules → risk_alerts）
                               │
            ┌──────────────────┼──────────────────┬──────────────┐
            ▼                  ▼                  ▼              ▼
      廉洁监察            内控评价            商业秘密       行为风险
      (cases)         (ic_evaluation     (trade_secret   (behavior_risk
                        _projects)         _items)      _analysis_reports)
            │                  │                  │              │
            └──────┬───────────┘                  │              │
                   │                              │              │
             ┌─────▼─────┐                        │              │
             │  持续改善   │◄───────────────────────┘              │
             │(improvement│                                       │
             │  _issues)  │                                       │
             └─────▲─────┘                                       │
                   │                                              │
        ┌──────────┴──────────┐                                   │
        │                     │                                   │
    专项审计               离任审计 ◄──────────────────────────────┘
(audit_projects)    (exit_audit_projects)
```

### 15.2 跨模块数据流明细

| 序号 | 上游模块 | 下游模块 | 数据流 | 关联字段 | 触发条件 |
|------|---------|---------|--------|---------|---------|
| 1 | 风险监控 | 廉洁监察 | `risk_alerts` → `cases` | `risk_push_records.target_module='integrity'` | 风险类型=舞弊风险，风险等级=高/中 |
| 2 | 风险监控 | 内控评价 | `risk_alerts` → `ic_evaluation_projects` | `risk_push_records.target_module='ic_evaluation'` | 风险类型=合规风险 |
| 3 | 风险监控 | 商业秘密 | `risk_alerts` → `trade_secret_items` | `risk_push_records.target_module='trade_secret'` | 风险类型=商业秘密风险 |
| 4 | 廉洁监察 | 持续改善 | `cases` → `improvement_issues` | `improvement_issues.source_module='integrity'` | 案件涉及追责处罚，生成问题清单 |
| 5 | 内控评价 | 持续改善 | `ic_design_defects/ic_execution_defects` → `improvement_issues` | `improvement_issues.source_module='ic_evaluation'` | 缺陷确认后汇入整改 |
| 6 | 内控评价 | 商业秘密 | `ic_evaluation_projects` → 制度库共享 | `knowledge_documents(kb_type='ic_evaluation')` 提供制度比对 | 定密评审时调用制度库 |
| 7 | 专项审计 | 持续改善 | `audit_findings` → `improvement_issues` | `improvement_issues.source_module='special_audit'` | 审计问题确认后汇入整改 |
| 8 | 离任审计 | 持续改善 | `exit_audit_findings` → `improvement_issues` | `improvement_issues.source_module='exit_audit'` | 个人/业务问题确认后汇入整改 |
| 9 | 风险监控 | 行为风险 | `risk_alerts` → `behavior_risk_analysis_reports` | 风险预警推送至行为风险分析 | 异常行为监测触发行为风险分析 |
| 10 | 行为风险 | 离任审计 | `behavior_risk_analysis_reports` → `exit_audit_projects` findings | 行为风险分析结果供离任审计参考 | 离任审计立项时调取行为风险记录 |
| 11 | 离任审计 | 风险监控 | 行为风险预警结果 ← `risk_alerts` | 离任审计接收风险监控传回的行为风险预警 | 问题清单生成阶段 |
| 12 | 持续改善 | 归档 | `improvement_issues(status='completed')` → 只读归档 | 状态变更为 `completed` | 整改复核通过 |
| 13 | 风险监控 | 风险监控 | `risk_alerts(callback_status)` → `rule_iteration_log` | 处置结果回流优化规则 | 误报/失效指标触发 |

### 15.3 A2A 外部智能体数据流

| 序号 | 来源模块 | 目标智能体 | 数据载体 | 关键字段 | 回调机制 |
|------|---------|-----------|---------|---------|---------|
| 1 | 廉洁监察 | 龟宝(guibao) | `a2a_tasks` | `target_agent='guibao'`, `command='initiate_penalty_tracking'` | `callback_url` → 更新 `a2a_tasks.callback_received` |
| 2 | 廉洁监察 | 西塞罗(cicero) | `a2a_tasks` | `target_agent='cicero'`, `command='push_legal_review'` | `callback_url` → 推进工作流 |
| 3 | 廉洁监察 | 波特(porter) | `a2a_tasks` | `target_agent='porter'`, `command='push_supplier_deduction'` | `callback_url` → 更新扣款状态 |
| 4 | 所有模块 | 外部系统 | `external_sync_logs` | `system_name='risk_control/OA/MDM/BPM'` | Webhook 回调 |

### 15.4 端到端数据流示例

#### 示例一：风险发现 → 立案调查 → 处罚整改

```
1. risk_rules(定时执行SQL) → risk_alerts(生成预警明细)
2. risk_alerts → risk_analysis_subjects(按主体合并) → 风险定性
3. risk_alerts(risk_type='舞弊风险') → risk_push_records → cases(自动创建案件)
4. cases → case_stages(intake→investigation→analysis→disposition→enforcement→post_report)
5. cases(涉及追责) → improvement_issues(source_module='integrity')
6. improvement_issues → improvement_plans → improvement_tasks → improvement_evidence → improvement_reviews
7. improvement_reviews(review_result='pass') → improvement_issues(status='completed') → 归档
```

#### 示例二：内控评价 → 缺陷发现 → 整改闭环

```
1. ic_evaluation_projects(立项) → ic_control_matrices(风控矩阵)
2. ic_control_matrices → ic_design_defects(设计缺陷) + ic_execution_defects(执行缺陷)
3. ic_score_records(打分) → ic_evaluation_reports(报告)
4. ic_design_defects + ic_execution_defects → improvement_issues(source_module='ic_evaluation')
5. improvement_issues → 整改任务下发 → 责任人提交证据 → AI初审 + 人工复审 → 闭环
```

---

## 附录

### A. 字段类型速查

| 类型 | 适用场景 |
|------|---------|
| `UUID` | 所有主键 |
| `VARCHAR(N)` | 编码、名称、短文本 |
| `TEXT` | 描述、意见、长文本 |
| `JSONB` | 灵活结构（附件列表、问答、AI输出、配置） |
| `BYTEA` | AES-256-GCM 加密字段 |
| `BOOLEAN` | 状态标记 |
| `SMALLINT` / `INT` | 序号、计数、版本号 |
| `NUMERIC(18,2)` | 金额 |
| `NUMERIC(5,2)` | 评分 |
| `NUMERIC(12,4)` | 阈值、指标 |
| `DATE` | 日期（无时间） |
| `TIMESTAMPTZ` | 时间戳（带时区） |
| `INET` | IP 地址 |
| `VECTOR(1536)` | 文本嵌入向量 |

### B. CHECK 约束汇总

| 表 | 字段 | 约束值 |
|----|------|--------|
| users | role | `group`, `ecovacs`, `tineco` |
| cases | client | `ecovacs`, `tineco`, `group` |
| cases | status | `pending`, `investigating`, `disposing`, `enforcing`, `closed`, `transferred` |
| risk_rules | risk_level | `高`, `中`, `低` |
| risk_rules | monitor_frequency | `hourly`, `daily`, `weekly`, `monthly` |
| risk_alerts | risk_type | `合规风险`, `舞弊风险`, `商业秘密风险`, `操作风险`, `财务风险`, `其他` |
| ic_score_records | dimension | `business_unit`, `business_cycle`, `position` |
| exit_audit_findings | finding_category | `personal`, `business` |
| trade_secret_items | secret_level | `核心商密`, `普通商密`, `内部信息` |
| improvement_issues | source_module | `ic_evaluation`, `integrity`, `trade_secret`, `behavior_risk`, `special_audit`, `exit_audit`, `business_assigned` |
| knowledge_documents | kb_type | 13 种知识库类型 |

### C. 预估数据量级

| 表 | 日增量 | 年总量 | 存储策略 |
|----|--------|--------|---------|
| users | - | ~100 | 永久保留 |
| cases | 3-10 | ~2000 | 软删除，归档 3 年 |
| risk_alerts | 50-500 | ~10万 | 热数据 90 天，归档 1 年 |
| audit_findings | 2-10 | ~2000 | 永久保留 |
| improvement_issues | 5-20 | ~5000 | 热数据 1 年，归档 3 年 |
| knowledge_documents | 5-50 | ~1万 | 永久保留，增量更新 |
| audit_log | 100-500 | ~10万 | 保留 >= 6 个月，归档 1 年 |
| a2a_tasks | 10-50 | ~1万 | 热数据 90 天，归档 1 年 |

---

> **文档版本**：v1.0 | **最后更新**：2026-05-19 | **数据库版本**：PostgreSQL 16 + pgvector 0.7+
