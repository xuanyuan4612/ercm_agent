<template>
  <div class="knowledge-view">
    <el-tabs v-model="activeTab" type="border-card">
      <!-- ═══════════════════════════════════════════════════ -->
      <!-- Tab 1: 知识检索 -->
      <!-- ═══════════════════════════════════════════════════ -->
      <el-tab-pane name="search">
        <template #label>
          <span class="tab-label"><el-icon :size="16"><Search /></el-icon> 知识检索</span>
        </template>

        <!-- 搜索栏 -->
        <div class="search-row">
          <el-input
            v-model="query"
            placeholder="输入搜索关键词..."
            size="large"
            clearable
            @keyup.enter="search"
            class="search-input"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select
            v-model="kbTypes"
            multiple
            placeholder="限定知识库类型（可选）"
            size="large"
            clearable
            collapse-tags
            collapse-tags-tooltip
            class="kb-select"
          >
            <el-option-group v-for="group in kbGroups" :key="group.label" :label="group.label">
              <el-option v-for="kb in group.options" :key="kb.value" :label="kb.label" :value="kb.value" />
            </el-option-group>
          </el-select>
          <el-select v-model="searchMode" size="large" style="width: 130px">
            <el-option label="混合检索" value="hybrid" />
            <el-option label="语义检索" value="semantic" />
            <el-option label="关键词" value="keyword" />
          </el-select>
          <el-button type="primary" size="large" :loading="loading" :icon="Search" @click="search">
            搜索
          </el-button>
        </div>

        <!-- 活跃筛选标签 -->
        <div v-if="kbTypes.length > 0" class="active-filters">
          <span class="filter-label">限定类型：</span>
          <el-tag v-for="kb in kbTypes" :key="kb" size="small" closable @close="removeKbType(kb)">
            {{ KB_TYPE_LABELS[kb] || kb }}
          </el-tag>
        </div>

        <!-- 诊断信息 -->
        <el-alert
          v-if="diagnostics"
          :title="diagnosticsTitle"
          :type="diagnostics.degraded ? 'warning' : 'info'"
          :closable="false"
          show-icon
          class="diag-alert"
        >
          <template #default>
            <div class="diag-detail">
              <span>耗时 {{ diagnostics.total_latency_ms }}ms</span>
              <span v-if="diagnostics.embedding_unavailable">· Embedding 不可用</span>
              <span v-if="diagnostics.knowledge_insufficient">· 知识不足</span>
              <span v-if="diagnostics.blocked_candidates > 0">· 拦截 {{ diagnostics.blocked_candidates }} 条</span>
              <span v-if="diagnostics.prompt_injection_suspected" class="inject-warn">· ⚠️ 疑似注入</span>
            </div>
            <div v-if="diagnostics.suggested_actions.length > 0" class="diag-actions">
              建议：{{ diagnostics.suggested_actions.join('；') }}
            </div>
          </template>
        </el-alert>

        <!-- 结果表格 -->
        <el-table :data="results" v-loading="loading" stripe empty-text="输入关键词开始搜索" highlight-current-row class="results-table">
          <el-table-column label="类型" width="130">
            <template #default="{ row }">
              <el-tag size="small" effect="light">
                {{ KB_TYPE_LABELS[row.kb_type] || row.kb_type }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="标题" min-width="180">
            <template #default="{ row }">
              <div class="title-cell">
                <el-icon :size="14"><Document /></el-icon>
                {{ row.title }}
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="content_snippet" label="内容摘要" min-width="280">
            <template #default="{ row }">
              <div class="snippet-cell">{{ row.content_snippet }}</div>
            </template>
          </el-table-column>
          <el-table-column label="相关度" width="150">
            <template #default="{ row }">
              <div class="relevance-cell">
                <el-progress
                  :percentage="Math.round(row.relevance * 100)"
                  :status="row.relevance >= 0.7 ? 'success' : row.relevance >= 0.4 ? '' : 'exception'"
                  :stroke-width="6"
                  :show-text="true"
                  style="flex: 1"
                />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="通道" width="100">
            <template #default="{ row }">
              <el-tag
                v-for="ch in (row.retrieval?.channels || [])"
                :key="ch"
                size="small"
                :type="ch === 'vector' ? 'success' : 'warning'"
                class="channel-tag"
              >
                {{ ch === 'vector' ? '语义' : '全文' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-if="!loading && searched && results.length === 0" description="未找到相关知识库内容，请尝试其他关键词" />
      </el-tab-pane>

      <!-- ═══════════════════════════════════════════════════ -->
      <!-- Tab 2: 文档上传 -->
      <!-- ═══════════════════════════════════════════════════ -->
      <el-tab-pane name="upload">
        <template #label>
          <span class="tab-label"><el-icon :size="16"><Upload /></el-icon> 文档上传</span>
        </template>

        <el-tabs v-model="uploadTabType" type="card" class="upload-subtabs">
          <!-- 文件上传 -->
          <el-tab-pane name="file">
            <template #label><el-icon :size="14"><Folder /></el-icon> 文件上传</template>

            <div class="upload-form">
              <el-row :gutter="20">
                <el-col :span="12">
                  <el-form label-position="top" size="large">
                    <el-form-item label="目标知识库">
                      <el-select v-model="upload.kbType" placeholder="选择知识库类型" style="width: 100%">
                        <el-option v-for="kb in allKbTypeOptions" :key="kb.value" :label="kb.label" :value="kb.value" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="密级">
                      <el-select v-model="upload.securityLevel" style="width: 100%">
                        <el-option label="公开 - public" value="public" />
                        <el-option label="内部 - internal" value="internal" />
                        <el-option label="机密 - confidential" value="confidential" />
                        <el-option label="绝密 - secret" value="secret" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="租户">
                      <el-select v-model="upload.client" style="width: 100%">
                        <el-option label="集团" value="group" />
                        <el-option label="科沃斯" value="ecovacs" />
                        <el-option label="添可" value="tineco" />
                      </el-select>
                    </el-form-item>
                  </el-form>
                </el-col>
                <el-col :span="12">
                  <el-upload
                    ref="fileUploadRef"
                    v-model:file-list="upload.fileList"
                    :auto-upload="false"
                    :limit="5"
                    :on-exceed="onExceed"
                    drag
                    multiple
                    accept=".txt,.md,.json,.docx,.pdf"
                    class="upload-dragger"
                  >
                    <el-icon :size="48" color="#C0C4CC"><UploadFilled /></el-icon>
                    <div class="upload-hint">
                      <p>拖拽文件到此处，或点击上传</p>
                      <small>支持 .txt .md .json .docx .pdf（单文件 ≤ 50MB）</small>
                    </div>
                  </el-upload>
                </el-col>
              </el-row>

              <el-button
                type="primary"
                size="large"
                :loading="upload.loading"
                :disabled="upload.fileList.length === 0 || !upload.kbType"
                @click="submitUpload"
                style="margin-top: 20px; width: 100%"
              >
                上传文件（{{ upload.fileList.length }} 个）
              </el-button>

              <!-- 上传结果 -->
              <div v-if="upload.results.length > 0" class="upload-results">
                <el-alert
                  v-for="(r, i) in upload.results"
                  :key="i"
                  :title="r.success ? `${r.doc_id ? '✅ 入库成功' : '⚠️ 部分跳过'} (${r.chunks_created} 块)` : `❌ 失败`"
                  :type="r.success ? 'success' : 'error'"
                  :description="r.success ? `创建 ${r.chunks_created} 个 chunk，跳过 ${r.chunks_skipped} 个重复` : r.error"
                  show-icon
                  :closable="true"
                  class="upload-result-item"
                />
              </div>
            </div>
          </el-tab-pane>

          <!-- 纯文本上传 -->
          <el-tab-pane name="text">
            <template #label><el-icon :size="14"><Edit /></el-icon> 纯文本上传</template>

            <el-form label-position="top" size="large">
              <el-row :gutter="20">
                <el-col :span="8">
                  <el-form-item label="目标知识库">
                    <el-select v-model="textUpload.kbType" placeholder="选择知识库类型" style="width: 100%">
                      <el-option v-for="kb in allKbTypeOptions" :key="kb.value" :label="kb.label" :value="kb.value" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item label="密级">
                    <el-select v-model="textUpload.securityLevel" style="width: 100%">
                      <el-option label="公开 - public" value="public" />
                      <el-option label="内部 - internal" value="internal" />
                      <el-option label="机密 - confidential" value="confidential" />
                      <el-option label="绝密 - secret" value="secret" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item label="租户">
                    <el-select v-model="textUpload.client" style="width: 100%">
                      <el-option label="集团" value="group" />
                      <el-option label="科沃斯" value="ecovacs" />
                      <el-option label="添可" value="tineco" />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item label="标题">
                <el-input v-model="textUpload.title" placeholder="条目标题" />
              </el-form-item>
              <el-form-item label="内容">
                <el-input
                  v-model="textUpload.content"
                  type="textarea"
                  :rows="8"
                  placeholder="输入知识条目内容..."
                />
              </el-form-item>
              <el-button
                type="primary"
                size="large"
                :loading="textUpload.loading"
                :disabled="!textUpload.title || !textUpload.content || !textUpload.kbType"
                @click="submitTextUpload"
              >
                提交
              </el-button>
            </el-form>

            <el-alert
              v-if="textUpload.result"
              :title="textUpload.result.success ? `✅ 入库成功 — ${textUpload.result.chunks_created} 个 chunk` : `❌ ${textUpload.result.error}`"
              :type="textUpload.result.success ? 'success' : 'error'"
              show-icon
              :closable="true"
              class="upload-result-item"
            />
          </el-tab-pane>
        </el-tabs>
      </el-tab-pane>

      <!-- ═══════════════════════════════════════════════════ -->
      <!-- Tab 3: 文档管理 -->
      <!-- ═══════════════════════════════════════════════════ -->
      <el-tab-pane name="manage">
        <template #label>
          <span class="tab-label"><el-icon :size="16"><Setting /></el-icon> 文档管理</span>
        </template>

        <div class="manage-toolbar">
          <el-select v-model="manage.kbType" placeholder="筛选知识库类型" clearable size="large" style="width: 240px" @change="loadDocuments">
            <el-option v-for="kb in allKbTypeOptions" :key="kb.value" :label="kb.label" :value="kb.value" />
          </el-select>
          <el-input
            v-model="manage.keyword"
            placeholder="搜索标题..."
            size="large"
            clearable
            :prefix-icon="Search"
            style="width: 280px; margin-left: 12px"
            @keyup.enter="loadDocuments"
          />
          <el-button size="large" :icon="Search" @click="loadDocuments">查询</el-button>
          <span class="manage-total" v-if="manage.total > 0">共 {{ manage.total }} 条</span>
        </div>

        <el-table :data="manage.documents" v-loading="manage.loading" stripe empty-text="请选择知识库类型查看文档">
          <el-table-column prop="title" label="标题" min-width="240">
            <template #default="{ row }">
              <el-link type="primary" @click="showDocDetail(row)">{{ row.title }}</el-link>
            </template>
          </el-table-column>
          <el-table-column label="租户" width="80">
            <template #default="{ row }">{{ CLIENT_LABELS[row.client] || row.client }}</template>
          </el-table-column>
          <el-table-column label="密级" width="90">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="row.security_level === 'secret' ? 'danger' : row.security_level === 'confidential' ? 'warning' : row.security_level === 'internal' ? '' : 'info'"
              >
                {{ SECURITY_LABELS[row.security_level] || row.security_level }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="chunk_index" label="分块" width="80">
            <template #default="{ row }">{{ row.chunk_index }}/{{ row.total_chunks }}</template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新时间" width="170">
            <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-popconfirm title="确定删除此文档？" confirm-button-text="删除" cancel-button-text="取消" @confirm="deleteDocument(row)">
                <template #reference>
                  <el-button type="danger" size="small" text :icon="Delete">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-if="manage.total > 0"
          v-model:current-page="manage.page"
          v-model:page-size="manage.pageSize"
          :total="manage.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadDocuments"
          @size-change="loadDocuments"
          style="margin-top: 16px; justify-content: flex-end"
        />

        <!-- 文档详情抽屉 -->
        <el-drawer v-model="manage.detailVisible" title="文档详情" size="600px">
          <template v-if="manage.currentDoc">
            <el-descriptions :column="2" border>
              <el-descriptions-item label="标题" :span="2">{{ manage.currentDoc.title }}</el-descriptions-item>
              <el-descriptions-item label="知识库">{{ KB_TYPE_LABELS[manage.currentDoc.kb_type] || manage.currentDoc.kb_type }}</el-descriptions-item>
              <el-descriptions-item label="密级">
                <el-tag size="small" :type="manage.currentDoc.security_level === 'secret' ? 'danger' : ''">
                  {{ SECURITY_LABELS[manage.currentDoc.security_level] }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="租户">{{ manage.currentDoc.client }}</el-descriptions-item>
              <el-descriptions-item label="组织">{{ manage.currentDoc.org_id }}</el-descriptions-item>
              <el-descriptions-item label="审核状态">{{ manage.currentDoc.approval_status }}</el-descriptions-item>
              <el-descriptions-item label="来源">{{ manage.currentDoc.source_path || '-' }}</el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ formatDate(manage.currentDoc.created_at) }}</el-descriptions-item>
              <el-descriptions-item label="更新时间">{{ formatDate(manage.currentDoc.updated_at) }}</el-descriptions-item>
            </el-descriptions>

            <h4 style="margin-top: 20px">Chunk 列表（{{ manage.currentDoc.chunks.length }} 个）</h4>
            <div v-for="chunk in manage.currentDoc.chunks" :key="chunk.chunk_id" class="chunk-item">
              <div class="chunk-header">
                <el-tag size="small" type="info">Chunk #{{ chunk.chunk_index }}</el-tag>
                <span v-if="chunk.content_hash" class="chunk-hash">{{ chunk.content_hash?.substring(0, 12) }}...</span>
              </div>
              <div class="chunk-content">{{ chunk.content_snippet }}</div>
            </div>
          </template>
        </el-drawer>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import {
  Collection,
  Delete,
  Document,
  Edit,
  Folder,
  Search,
  Setting,
  Upload,
  UploadFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { knowledgeApi } from '@/api'
import {
  CLIENT_LABELS,
  KB_TYPE_LABELS,
} from '@/types'
import type {
  IngestionResult,
  KnowledgeDocumentBrief,
  KnowledgeDocumentDetail,
  RAGDiagnostics,
  RAGResult,
} from '@/types'

const activeTab = ref('search')

// ═══════════════════════════════════════════════════════════════
// Tab 1: 搜索
// ═══════════════════════════════════════════════════════════════
const query = ref('')
const kbTypes = ref<string[]>([])
const searchMode = ref('hybrid')
const results = ref<RAGResult[]>([])
const diagnostics = ref<RAGDiagnostics | null>(null)
const loading = ref(false)
const searched = ref(false)

const diagnosticsTitle = computed(() => {
  const d = diagnostics.value
  if (!d) return ''
  if (d.knowledge_insufficient) return `检索完成 — ⚠️ 知识不足（${d.total_latency_ms}ms）`
  if (d.degraded) return `检索完成 — ⚠️ 已降级（${d.total_latency_ms}ms）`
  return `检索完成 — ${results.value.length} 条结果（${d.total_latency_ms}ms）`
})

const kbGroups = [
  {
    label: '廉洁监察',
    options: [
      { value: 'intake', label: '初筛入口' }, { value: 'investigation', label: '调查方案' },
      { value: 'analysis', label: '分析报告' }, { value: 'disposition', label: '处置分流' },
      { value: 'enforcement', label: '处罚执行' },
    ],
  },
  {
    label: '风险监控',
    options: [
      { value: 'risk_rules', label: '风险规则' }, { value: 'risk_cases', label: '风险案例' },
      { value: 'database_schema', label: '数据库 Schema' }, { value: 'disposition_feedback', label: '处置反馈' },
    ],
  },
  {
    label: '内控/审计',
    options: [
      { value: 'ic_policy', label: '内控制度' }, { value: 'control_matrix', label: '控制矩阵' },
      { value: 'audit_plan', label: '审计计划' }, { value: 'interview_template', label: '访谈模板' },
      { value: 'sa_plan', label: '专项审计计划' }, { value: 'sa_history', label: '专项审计历史' },
      { value: 'ea_plan', label: '离任审计计划' }, { value: 'position_duty', label: '岗位职责' },
    ],
  },
  {
    label: '商业秘密/行为/改善',
    options: [
      { value: 'trade_secret_policy', label: '商业秘密制度' }, { value: 'trade_secret_law', label: '商业秘密法律' },
      { value: 'behavior_policy', label: '行为规范制度' }, { value: 'improvement_case', label: '改善案例' },
    ],
  },
  {
    label: '共享',
    options: [
      { value: 'common', label: '公共知识' }, { value: 'law_and_regulation', label: '法律法规' },
    ],
  },
]

const SECURITY_LABELS: Record<string, string> = {
  public: '公开', internal: '内部', confidential: '机密', secret: '绝密',
}

function removeKbType(kb: string) {
  kbTypes.value = kbTypes.value.filter((t) => t !== kb)
}

async function search() {
  if (!query.value.trim()) return
  loading.value = true
  searched.value = true
  diagnostics.value = null
  try {
    const res = await knowledgeApi.retrieve({
      query: query.value,
      module: 'common',
      stage: 'search',
      tenant_scope: { client: 'group', role: 'admin', security_levels: ['public', 'internal', 'confidential', 'secret'] },
      trace_id: 'ui-' + Date.now(),
      kb_types: kbTypes.value.length > 0 ? kbTypes.value : null,
      top_k: 10,
      mode: searchMode.value as 'hybrid' | 'semantic' | 'keyword',
    })
    results.value = res.data.results || []
    diagnostics.value = res.data.diagnostics
  } catch {
    ElMessage.error('检索失败，请稍后重试')
    results.value = []
  } finally {
    loading.value = false
  }
}

// ═══════════════════════════════════════════════════════════════
// Tab 2: 上传
// ═══════════════════════════════════════════════════════════════
const uploadTabType = ref('file')
const fileUploadRef = ref()

const allKbTypeOptions = computed(() =>
  Object.entries(KB_TYPE_LABELS).map(([value, label]) => ({ value, label }))
)

const upload = reactive({
  kbType: '',
  securityLevel: 'internal',
  client: 'group',
  fileList: [] as any[],
  loading: false,
  results: [] as IngestionResult[],
})

function onExceed() {
  ElMessage.warning('最多同时上传 5 个文件')
}

async function submitUpload() {
  if (!upload.kbType) {
    ElMessage.warning('请选择目标知识库')
    return
  }
  upload.loading = true
  upload.results = []
  for (const f of upload.fileList) {
    try {
      const res = await knowledgeApi.uploadFile(
        upload.kbType,
        f.raw,
        upload.client,
        undefined,
        upload.securityLevel,
      )
      upload.results.push(res.data)
    } catch (e: any) {
      upload.results.push({
        success: false,
        doc_id: '',
        chunks_created: 0,
        chunks_skipped: 0,
        error: e?.response?.data?.message || e?.message || '上传失败',
      })
    }
  }
  upload.loading = false
  if (upload.results.every((r) => r.success)) {
    upload.fileList = []
    ElMessage.success('全部文件上传完成')
  }
}

const textUpload = reactive({
  kbType: '',
  securityLevel: 'internal',
  client: 'group',
  title: '',
  content: '',
  loading: false,
  result: null as IngestionResult | null,
})

async function submitTextUpload() {
  if (!textUpload.title || !textUpload.content || !textUpload.kbType) {
    ElMessage.warning('请填写标题、内容和目标知识库')
    return
  }
  textUpload.loading = true
  textUpload.result = null
  try {
    const res = await knowledgeApi.uploadText(
      textUpload.kbType,
      textUpload.title,
      textUpload.content,
      textUpload.client,
      textUpload.securityLevel,
    )
    textUpload.result = res.data
    if (res.data.success) {
      ElMessage.success(`入库成功 — ${res.data.chunks_created} 个 chunk`)
      textUpload.title = ''
      textUpload.content = ''
    } else {
      ElMessage.error(res.data.error || '入库失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '提交失败')
  } finally {
    textUpload.loading = false
  }
}

// ═══════════════════════════════════════════════════════════════
// Tab 3: 文档管理
// ═══════════════════════════════════════════════════════════════
const manage = reactive({
  kbType: '',
  keyword: '',
  page: 1,
  pageSize: 20,
  total: 0,
  loading: false,
  documents: [] as KnowledgeDocumentBrief[],
  detailVisible: false,
  currentDoc: null as KnowledgeDocumentDetail | null,
})

async function loadDocuments() {
  if (!manage.kbType) return
  manage.loading = true
  try {
    const res = await knowledgeApi.listDocuments(manage.kbType, {
      page: manage.page,
      page_size: manage.pageSize,
      keyword: manage.keyword || undefined,
    })
    manage.documents = res.data.items
    manage.total = res.data.total
  } catch {
    ElMessage.error('加载文档列表失败')
  } finally {
    manage.loading = false
  }
}

async function showDocDetail(row: KnowledgeDocumentBrief) {
  try {
    const res = await knowledgeApi.getDocument(manage.kbType, row.id)
    manage.currentDoc = res.data
    manage.detailVisible = true
  } catch {
    ElMessage.error('加载文档详情失败')
  }
}

async function deleteDocument(row: KnowledgeDocumentBrief) {
  try {
    await knowledgeApi.deleteDocument(manage.kbType, row.id)
    ElMessage.success(`已删除：${row.title}`)
    loadDocuments()
  } catch {
    ElMessage.error('删除失败')
  }
}

function formatDate(d?: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN')
}
</script>

<script lang="ts">
import { computed } from 'vue'
</script>

<style scoped>
.knowledge-view { max-width: 1200px; margin: 0 auto; }

/* ── Tabs ── */
.tab-label { display: flex; align-items: center; gap: 6px; }

/* ── 搜索 ── */
.search-row { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
.search-input { flex: 1; max-width: 360px; }
.kb-select { flex: 1; max-width: 420px; }
.active-filters { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.filter-label { font-size: 13px; color: #909399; }

/* ── 诊断 ── */
.diag-alert { margin-bottom: 12px; }
.diag-detail { display: flex; gap: 12px; font-size: 13px; color: #606266; }
.diag-actions { margin-top: 4px; font-size: 12px; color: #909399; }
.inject-warn { color: #E6A23C; font-weight: 600; }

/* ── 表格 ── */
.results-table { margin-top: 8px; }
.title-cell { display: flex; align-items: center; gap: 6px; }
.snippet-cell {
  color: #606266; line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.relevance-cell { display: flex; align-items: center; }
.channel-tag + .channel-tag { margin-left: 4px; }

/* ── 上传 ── */
.upload-subtabs { margin-bottom: 16px; }
.upload-form { margin-top: 8px; }
.upload-dragger { width: 100%; }
.upload-hint { margin-top: 12px; }
.upload-hint p { margin: 0; font-size: 14px; color: #606266; }
.upload-hint small { color: #C0C4CC; font-size: 12px; }
.upload-results { margin-top: 16px; }
.upload-result-item { margin-bottom: 8px; }

/* ── 管理 ── */
.manage-toolbar { display: flex; align-items: center; margin-bottom: 16px; }
.manage-total { margin-left: 12px; color: #909399; font-size: 14px; }

/* ── Chunk ── */
.chunk-item {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #EBEEF5;
  border-radius: 6px;
  background: #FAFAFA;
}
.chunk-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.chunk-hash { font-size: 11px; color: #C0C4CC; font-family: monospace; }
.chunk-content { font-size: 13px; color: #606266; line-height: 1.6; }
</style>
