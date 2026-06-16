/** 案件相关类型定义 */

export interface CaseBrief {
  id: string
  task_id: string
  case_code?: string
  client: string
  fraud_source: string
  current_stage?: string
  status: string
  created_by?: string
  created_at?: string
  updated_at?: string
}

export interface CaseDetail extends CaseBrief {
  fraud_event_detail?: string
  proof?: string
  attachments?: string[]
  fraud_tel?: string
  risk_control_case_id?: string
  workflow_state?: Record<string, unknown>
  langgraph_thread_id?: string
  generated_documents: DocumentBrief[]
}

export interface DocumentBrief {
  id: string
  type: string
  name: string
  format: string
  created_at?: string
}

export interface CaseCreateRequest {
  fraud_source: string
  client: string
  reported_staff_names?: string[]
  reported_supplier_names?: string[]
  reported_dealer_names?: string[]
  fraud_event_detail?: string
  proof?: string
  attachments?: string[]
  fraud_tel?: string
  fraud_email?: string
  fraud_other_info?: string
  risk_control_case_id?: string
}

export interface WorkflowStatus {
  current_stage: string
  stage_history: StageHistoryEntry[]
  pending_approval_stage?: string
  error_info?: unknown
  needs_human_intervention: boolean
}

export interface StageHistoryEntry {
  stage_name: string
  status: string
  ai_output_type?: string
  approval_result?: string
  started_at?: string
  completed_at?: string
}

export interface ApprovalSubmitRequest {
  action: 'approved' | 'rejected' | 'modified'
  comment?: string
  modifications?: Record<string, unknown>
}

export interface PendingApproval {
  stage: string
  ai_output: Record<string, unknown>
  original_prompt?: string
  knowledge_refs: KnowledgeRef[]
}

export interface KnowledgeRef {
  doc_id: string
  kb_type: string
  title: string
  content_snippet: string
  relevance: number
}

export interface UserInfo {
  id: string
  username: string
  display_name: string
  department: string
  email?: string
  role: string
  is_active?: boolean
  last_login?: string
  locked_until?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  expires_in: number
}

// ═══════════════════════════════════════════════════════════════
// Agent / 模块 Profile 类型
// ═══════════════════════════════════════════════════════════════

export type ModelRoutingPolicy = 'primary_only' | 'primary_with_fallback' | 'sensitive_data'

export interface QualityGate {
  require_citations: boolean
  require_evidence_chain: boolean
  require_confidence: boolean
  require_uncertainties: boolean
  require_human_review: boolean
  require_sql_review: boolean
  require_false_positive_feedback: boolean
  require_human_review_for_push: boolean
  require_control_activity_mapping: boolean
  require_deficiency_basis: boolean
  require_tenure_rule_check: boolean
  require_issue_category: boolean
  require_policy_basis: boolean
  require_legal_case_reference: boolean
  require_data_scope_confirmation: boolean
  require_privacy_minimization: boolean
  require_issue_source: boolean
  require_rectification_mapping: boolean
  require_evidence_sufficiency: boolean
  require_issue_evidence_mapping: boolean
}

export interface ModuleAgentProfile {
  profile_id: string
  module: string
  module_graph: string
  schema_version: string
  knowledge_scopes: string[]
  allowed_tools: string[]
  model_routing_policy: ModelRoutingPolicy
  primary_provider: string
  fallback_provider: string
  sensitive_fallback: string
  quality_gates: QualityGate
  description: string
}

// 分页响应
export interface PaginatedResponse<T> {
  code: number
  data: {
    items: T[]
    total: number
    page: number
    page_size: number
  }
}

export interface ApiResponse<T> {
  code: number
  data: T
  message?: string
}

// ═══════════════════════════════════════════════════════════════
// 8 大模块 Label 映射
// ═══════════════════════════════════════════════════════════════

export const MODULE_LABELS: Record<string, string> = {
  integrity_supervision: '廉洁监察',
  risk_monitoring: '风险监控',
  internal_control_evaluation: '内控评价',
  special_audit: '专项审计',
  exit_audit: '离任审计',
  trade_secrets: '商业秘密保护',
  behavioral_risk: '行为风险',
  continuous_improvement: '持续改善',
}

export const MODULE_DESCRIPTIONS: Record<string, string> = {
  integrity_supervision: '6 阶段反舞弊调查，覆盖初筛→调查→分析→处置→执行→报案全流程',
  risk_monitoring: '7×24 小时无人值守自动扫描，SQL 动态风险规则 + 误报反馈闭环',
  internal_control_evaluation: '19 个业务循环 + 13 步骤工作流，控制矩阵驱动的合规评价',
  special_audit: '5 阶段专项审计，覆盖计划→进场→测试→发现→报告全流程',
  exit_audit: '6 阶段离任审计，整合 HR 数据 + 财务凭证 + 行为风险画像',
  trade_secrets: '定密预审 + 专家评审 + 管理报告，商业秘密全生命周期保护',
  behavioral_risk: '跨系统行为数据整合 + 异常行为识别 + 隐私最小化原则',
  continuous_improvement: '全模块问题统一承接 + 闭环跟踪 + 整改效果验证',
}

export const MODULE_ICONS: Record<string, string> = {
  integrity_supervision: 'Search',
  risk_monitoring: 'WarningFilled',
  internal_control_evaluation: 'Checked',
  special_audit: 'Document',
  exit_audit: 'UserFilled',
  trade_secrets: 'Lock',
  behavioral_risk: 'View',
  continuous_improvement: 'Refresh',
}

export const MODULE_COLORS: Record<string, string> = {
  integrity_supervision: '#409EFF',
  risk_monitoring: '#E6A23C',
  internal_control_evaluation: '#67C23A',
  special_audit: '#F56C6C',
  exit_audit: '#909399',
  trade_secrets: '#9B59B6',
  behavioral_risk: '#1ABC9C',
  continuous_improvement: '#E84393',
}

// ═══════════════════════════════════════════════════════════════
// 知识库类型 Label 映射
// ═══════════════════════════════════════════════════════════════

export const KB_TYPE_LABELS: Record<string, string> = {
  // 廉洁监察
  intact: '初筛入口',
  investigation: '调查方案',
  analysis: '分析报告',
  disposition: '处置分流',
  enforcement: '处罚执行',
  // 风险监控
  risk_rules: '风险规则',
  risk_cases: '风险案例',
  database_schema: '数据库 Schema',
  disposition_feedback: '处置反馈',
  // 内控评价
  ic_policy: '内控制度',
  control_matrix: '控制矩阵',
  audit_plan: '审计计划',
  interview_template: '访谈模板',
  deficiency_rating: '缺陷评级',
  // 专项审计
  sa_plan: '专项审计计划',
  sa_history: '专项审计历史',
  audit_workpaper_template: '审计底稿模板',
  improvement_suggestion: '改善建议',
  // 离任审计
  ea_plan: '离任审计计划',
  position_duty: '岗位职责',
  personal_risk_case: '个人风险案例',
  business_audit_case: '业务审计案例',
  behavioral_risk_history: '行为风险历史',
  // 商业秘密
  trade_secret_policy: '商业秘密制度',
  ip_policy: '知识产权制度',
  trade_secret_law: '商业秘密法律',
  trade_secret_cases: '商业秘密案例',
  historical_secret_review: '历史定密评审',
  // 行为风险
  behavior_policy: '行为规范制度',
  employee_lifecycle: '员工生命周期',
  historical_behavior_analysis: '历史行为分析',
  // 持续改善
  improvement_case: '改善案例',
  rectification_template: '整改模板',
  audit_issue_history: '审计问题历史',
  policy_and_process: '制度与流程',
  // 共享
  common: '公共知识',
  law_and_regulation: '法律法规',
  kb_integrity_policy: '廉洁制度',
  kb_integrity_cases: '廉洁案例',
}

// ═══════════════════════════════════════════════════════════════
// 工具 Label 映射
// ═══════════════════════════════════════════════════════════════

export const TOOL_LABELS: Record<string, string> = {
  rag_search: '知识库检索',
  evidence_search: '证据检索',
  sql_analyze_readonly: 'SQL 只读分析',
  sql_syntax_validate: 'SQL 语法校验',
  sql_test_execute_readonly: 'SQL 测试执行',
  doc_generate: '文档生成',
  doc_parse: '文档解析',
  a2a_send: 'A2A 消息发送',
  external_sync_outbox: '外部系统同步',
  hr_profile_read: 'HR 档案读取',
  behavior_risk_summary_read: '行为风险汇总',
  behavior_log_query_readonly: '行为日志查询',
  finance_voucher_readonly: '财务凭证只读',
  control_matrix_read: '控制矩阵读取',
  interview_plan_generate: '访谈计划生成',
  audit_workpaper_analyze: '审计底稿分析',
  score_calculate: '评分计算',
  risk_scan_submit: '风险扫描提交',
  external_data_query: '外部数据查询',
  outbox_publish: '消息发布',
  policy_compare: '制度比对',
  historical_review_search: '历史评审检索',
  sensitivity_classifier: '敏感度分类器',
  issue_deduplicate: '问题去重',
  mdm_org_read: 'MDM 组织架构读取',
  image_compare: '图片比对',
  notification_draft: '通知草拟',
}

// ═══════════════════════════════════════════════════════════════
// 质量门禁 Label 映射
// ═══════════════════════════════════════════════════════════════

export const QUALITY_GATE_LABELS: Record<string, string> = {
  require_citations: '引用标注',
  require_evidence_chain: '证据链完整性',
  require_confidence: '置信度声明',
  require_uncertainties: '不确定性披露',
  require_human_review: '人工守门审核',
  require_sql_review: 'SQL 审核',
  require_false_positive_feedback: '误报反馈',
  require_human_review_for_push: '推送前人工确认',
  require_control_activity_mapping: '控制活动映射',
  require_deficiency_basis: '缺陷判定依据',
  require_tenure_rule_check: '任期规则校验',
  require_issue_category: '问题分类标注',
  require_policy_basis: '制度依据',
  require_legal_case_reference: '法律案例引用',
  require_data_scope_confirmation: '数据范围确认',
  require_privacy_minimization: '隐私最小化',
  require_issue_source: '问题来源标注',
  require_rectification_mapping: '整改方案映射',
  require_evidence_sufficiency: '证据充分性',
  require_issue_evidence_mapping: '问题证据映射',
}

// ═══════════════════════════════════════════════════════════════
// 模型路由策略 Label 映射
// ═══════════════════════════════════════════════════════════════

export const ROUTING_POLICY_LABELS: Record<string, string> = {
  primary_only: '仅主模型',
  primary_with_fallback: '主模型 + 自动降级',
  sensitive_data: '敏感数据私有模型',
}

// ═══════════════════════════════════════════════════════════════
// 工作流阶段映射
// ═══════════════════════════════════════════════════════════════

export const STAGE_LABELS: Record<string, string> = {
  intake: '材料初判与分流',
  investigation: '调查方案生成',
  analysis: '多维分析与报告撰写',
  disposition: '处置分流与处罚确定',
  enforcement: '处罚执行与跟踪',
  post_report: '报案后续协助',
}

export const STAGE_ORDER: Record<string, number> = {
  intake: 1,
  investigation: 2,
  analysis: 3,
  disposition: 4,
  enforcement: 5,
  post_report: 6,
}

export const CLIENT_LABELS: Record<string, string> = {
  ecovacs: '科沃斯',
  tineco: '添可',
  group: '集团',
}

export const SOURCE_LABELS: Record<string, string> = {
  manual: '手动录入',
  phone: '电话举报',
  email: '邮箱举报',
  wechat: '公众号',
  agent: '智能体推送',
}
