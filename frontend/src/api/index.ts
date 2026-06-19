import axios from 'axios'
import type {
  ApiResponse,
  CaseBrief,
  CaseCreateRequest,
  CaseDetail,
  LoginRequest,
  LoginResponse,
  PaginatedResponse,
  PendingApproval,
  UserInfo,
  WorkflowStatus,
} from '@/types'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// 请求拦截器：注入 token
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：统一错误处理
http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

function get<T>(url: string, params?: Record<string, unknown>) {
  return http.get<ApiResponse<T>>(url, { params }).then((r) => r.data)
}

function post<T>(url: string, data?: Record<string, unknown>) {
  return http.post<ApiResponse<T>>(url, data).then((r) => r.data)
}

function put<T>(url: string, data?: Record<string, unknown>) {
  return http.put<ApiResponse<T>>(url, data).then((r) => r.data)
}

function del<T>(url: string) {
  return http.delete<ApiResponse<T>>(url).then((r) => r.data)
}

// ═══ 认证 ═══
export const authApi = {
  login: (data: LoginRequest) => post<LoginResponse>('/auth/login', data as never),
  logout: () => post<Record<string, never>>('/auth/logout'),
  me: () => get<UserInfo>('/auth/me'),
}

// ═══ 案件管理 ═══
export const casesApi = {
  list: (params?: Record<string, unknown>) =>
    get<PaginatedResponse<CaseBrief>['data']>('/cases', params),
  get: (id: string) => get<CaseDetail>(`/cases/${id}`),
  create: (data: CaseCreateRequest) => post<CaseBrief>(`/cases`, data as never),
  update: (id: string, data: Partial<CaseCreateRequest>) =>
    put<CaseDetail>(`/cases/${id}`, data as never),
  delete: (id: string) => del<{ message: string }>(`/cases/${id}`),
}

// ═══ 工作流 ═══
export const workflowApi = {
  start: (caseId: string) => post<{ thread_id: string; current_stage: string; status: string }>(
    `/cases/${caseId}/workflow/start`
  ),
  resume: (caseId: string, comment?: string) =>
    post<{ thread_id: string; current_stage: string; status: string }>(
      `/cases/${caseId}/workflow/resume`,
      { comment } as never
    ),
  status: (caseId: string) => get<WorkflowStatus>(`/cases/${caseId}/workflow/status`),
  history: (caseId: string) =>
    get<Array<{ stage_name: string; status: string; started_at?: string; completed_at?: string }>>(
      `/cases/${caseId}/workflow/history`
    ),
  interrupt: (caseId: string) =>
    post<{ message: string }>(`/cases/${caseId}/workflow/interrupt`),
}

// ═══ 守门审批 ═══
export const approvalApi = {
  pending: (caseId: string) => get<PendingApproval>(`/cases/${caseId}/approval/pending`),
  submit: (caseId: string, stage: string, action: string, comment?: string) =>
    post<{ status: string; next_stage?: string }>(
      `/cases/${caseId}/approval/${stage}`,
      { action, comment } as never
    ),
  regenerate: (caseId: string, stage: string, selectedText: string, instruction: string) =>
    post<{ regenerated_text: string }>(`/cases/${caseId}/approval/${stage}/regenerate`, {
      selected_text: selectedText,
      instruction,
    } as never),
  history: (caseId: string) =>
    get<Array<{ id: string; stage_name: string; reviewer_id: string; action: string; comment?: string; created_at: string }>>(
      `/cases/${caseId}/approval/history`
    ),
}

// ═══ 文档管理 ═══
export const documentsApi = {
  list: (caseId: string) =>
    get<Array<{ id: string; type: string; name: string; format: string; version: number }>>(
      `/cases/${caseId}/documents`
    ),
  upload: (caseId: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return http.post(`/cases/${caseId}/speech-to-text`, formData).then((r) => r.data)
  },
}

// ═══ 知识库 ═══
import type {
  IngestionResult,
  KnowledgeBaseBrief,
  KnowledgeDocumentBrief,
  KnowledgeDocumentDetail,
  RAGRequest,
  RAGResponse,
} from '@/types'

export const knowledgeApi = {
  /** 知识库检索（完整 RAG 流水线） */
  retrieve: (data: RAGRequest) =>
    post<RAGResponse>('/knowledge-bases/retrieve', data as never),
  /** 知识库搜索（简化接口，向后兼容） */
  search: (query: string, kbTypes?: string, topK = 5) =>
    get<Array<{ doc_id: string; kb_type: string; title: string; content_snippet: string; relevance: number; updated_at?: string }>>(
      '/knowledge-bases/search',
      { query, kb_types: kbTypes, top_k: topK }
    ),
  /** 知识库列表 */
  list: () =>
    get<KnowledgeBaseBrief[]>('/knowledge-bases'),
  /** 文档列表 */
  listDocuments: (kbType: string, params?: Record<string, unknown>) =>
    get<PaginatedResponse<KnowledgeDocumentBrief>['data']>(
      `/knowledge-bases/${kbType}/documents`,
      params as never
    ),
  /** 文档详情 */
  getDocument: (kbType: string, docId: string) =>
    get<KnowledgeDocumentDetail>(`/knowledge-bases/${kbType}/documents/${docId}`),
  /** 上传文件 */
  uploadFile: (kbType: string, file: File, client?: string, orgId?: string, securityLevel?: string) => {
    const formData = new FormData()
    formData.append('file', file)
    const params = new URLSearchParams()
    if (client) params.set('client', client)
    if (orgId) params.set('org_id', orgId)
    if (securityLevel) params.set('security_level', securityLevel)
    const qs = params.toString()
    return http.post<ApiResponse<IngestionResult>>(
      `/knowledge-bases/${kbType}/upload${qs ? '?' + qs : ''}`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    ).then((r) => r.data)
  },
  /** 上传纯文本 */
  uploadText: (kbType: string, title: string, content: string, client?: string, securityLevel?: string) =>
    post<IngestionResult>(`/knowledge-bases/${kbType}/upload-text`, {
      title, content, client, security_level: securityLevel,
    } as never),
  /** 删除文档 */
  deleteDocument: (kbType: string, docId: string) =>
    del<{ message: string }>(`/knowledge-bases/${kbType}/documents/${docId}`),
  /** 检索反馈 */
  feedback: (data: { trace_id: string; accepted_refs: string[]; rejected_refs: string[] }) =>
    post<{ message: string }>('/knowledge-bases/feedback', data as never),
}

// ═══ AI Agent 模块管理 ═══
import type { ModuleAgentProfile } from '@/types'

export const agentsApi = {
  /** 获取所有模块 Agent Profile 列表 */
  list: () => get<ModuleAgentProfile[]>('/agents/profiles'),
  /** 获取单个模块 Agent Profile */
  get: (module: string) => get<ModuleAgentProfile | null>(`/agents/profiles/${module}`),
}

// ═══ 风险监控 ═══
import type {
  RiskRule,
  RiskAlertBrief,
  RiskAlertDetail,
  RiskScanTask,
  RuleIteration,
  RiskPushRecord,
} from '@/types'

export const riskMonitorApi = {
  // 规则管理
  rules: {
    list: (params?: Record<string, unknown>) =>
      get<PaginatedResponse<RiskRule>['data']>('/risk-monitor/rules', params),
    get: (id: string) =>
      get<{ rule: RiskRule; iterations: RuleIteration[] }>(`/risk-monitor/rules/${id}`),
    create: (data: Record<string, unknown>) =>
      post<RiskRule>('/risk-monitor/rules', data),
    update: (id: string, data: Record<string, unknown>) =>
      put<RiskRule>(`/risk-monitor/rules/${id}`, data),
    approve: (id: string, action: string, comment?: string) =>
      post<RiskRule>(`/risk-monitor/rules/${id}/approve`, { action, comment }),
    delete: (id: string) =>
      del<{ message: string }>(`/risk-monitor/rules/${id}`),
  },
  // 扫描任务
  scans: {
    list: (params?: Record<string, unknown>) =>
      get<PaginatedResponse<RiskScanTask>['data']>('/risk-monitor/scans', params),
    trigger: (data?: Record<string, unknown>) =>
      post<{ message: string; rule_count: number; rules: Array<{ id: string; rule_code: string; level3_scene: string }> }>(
        '/risk-monitor/scans',
        data
      ),
  },
  // 预警管理
  alerts: {
    list: (params?: Record<string, unknown>) =>
      get<PaginatedResponse<RiskAlertBrief>['data']>('/risk-monitor/alerts', params),
    get: (id: string) =>
      get<RiskAlertDetail>(`/risk-monitor/alerts/${id}`),
    approve: (id: string, action: string, comment?: string, modifications?: Record<string, unknown>) =>
      post<RiskAlertDetail>(`/risk-monitor/alerts/${id}/approve`, { action, comment, modifications: modifications ? JSON.stringify(modifications) : undefined }),
    pushes: (id: string) =>
      get<RiskPushRecord[]>(`/risk-monitor/alerts/${id}/pushes`),
  },
}

// ═══ 管理员 ═══
export const adminApi = {
  users: (params?: Record<string, unknown>) =>
    get<PaginatedResponse<UserInfo>['data']>('/admin/users', params),
  createUser: (data: { username: string; password: string; display_name: string; department: string; role: string; email?: string }) =>
    post<UserInfo>('/admin/users', data as never),
  toggleUser: (userId: string) => http.patch(`/admin/users/${userId}/status`).then((r) => r.data),
  auditLogs: (params?: Record<string, unknown>) =>
    get<PaginatedResponse<Record<string, unknown>>['data']>('/admin/audit-logs', params),
}
