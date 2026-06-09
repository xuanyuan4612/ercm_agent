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

// 工作流阶段映射
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
