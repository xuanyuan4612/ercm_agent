<template>
  <div class="case-detail" v-loading="loading">
    <!-- 案件基本信息 -->
    <el-card style="margin-bottom: 16px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>案件信息 — {{ detail?.task_id }}</span>
          <div>
            <el-button v-if="!detail?.langgraph_thread_id" type="success" size="small" @click="startWorkflow">
              启动工作流
            </el-button>
            <el-button v-if="detail?.current_stage && detail?.status !== 'closed'" type="warning" size="small" @click="$router.push(`/cases/${caseId}/approval`)">
              碳基守门
            </el-button>
            <el-button size="small" @click="$router.push('/cases')">返回列表</el-button>
          </div>
        </div>
      </template>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="案件编号">{{ detail?.task_id }}</el-descriptions-item>
        <el-descriptions-item label="事业部">
          <el-tag :type="clientTag(detail?.client)">{{ clientLabel(detail?.client) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="来源">{{ sourceLabel(detail?.fraud_source) }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusTag(detail?.status)">{{ statusLabel(detail?.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="当前阶段">
          <el-tag v-if="detail?.current_stage" type="primary">{{ stageLabel(detail?.current_stage) }}</el-tag>
          <span v-else class="text-muted">— 未启动 —</span>
        </el-descriptions-item>
        <el-descriptions-item label="创建人">{{ detail?.created_by }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ detail?.created_at }}</el-descriptions-item>
        <el-descriptions-item label="风控案件ID">{{ detail?.risk_control_case_id || '—' }}</el-descriptions-item>
        <el-descriptions-item label="事件详情" :span="2">{{ detail?.fraud_event_detail || '—' }}</el-descriptions-item>
        <el-descriptions-item label="证据" :span="2">{{ detail?.proof || '—' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 工作流阶段进度 -->
    <el-card style="margin-bottom: 16px" v-if="workflowStatus">
      <template #header><span>工作流进度</span></template>
      <el-steps :active="currentStepIndex" finish-status="success" align-center>
        <el-step v-for="s in allStages" :key="s.key" :title="s.label" :description="stageStatusDesc(s.key)" />
      </el-steps>
    </el-card>

    <!-- 工作流历史 -->
    <el-card style="margin-bottom: 16px" v-if="stageHistory.length > 0">
      <template #header><span>阶段流转记录</span></template>
      <el-timeline>
        <el-timeline-item v-for="item in stageHistory" :key="item.stage_name"
          :timestamp="item.started_at || ''"
          :type="item.status === 'approved' ? 'success' : item.status === 'rejected' ? 'danger' : 'primary'">
          {{ stageLabel(item.stage_name) }} — {{ item.status }}
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <!-- 生成文档 -->
    <el-card>
      <template #header><span>生成文档</span></template>
      <el-table :data="detail?.generated_documents || []" empty-text="暂无生成文档">
        <el-table-column prop="type" label="文档类型" width="150" />
        <el-table-column prop="name" label="文件名" />
        <el-table-column prop="format" label="格式" width="80" />
        <el-table-column prop="created_at" label="生成时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { casesApi, workflowApi } from '@/api'
import { CLIENT_LABELS, SOURCE_LABELS, STAGE_LABELS } from '@/types'
import type { CaseDetail, WorkflowStatus, StageHistoryEntry } from '@/types'

const route = useRoute()
const caseId = route.params.id as string
const detail = ref<CaseDetail | null>(null)
const workflowStatus = ref<WorkflowStatus | null>(null)
const stageHistory = ref<StageHistoryEntry[]>([])
const loading = ref(false)

const allStages = [
  { key: 'intake', label: '材料初判' },
  { key: 'investigation', label: '调查方案' },
  { key: 'analysis', label: '分析报告' },
  { key: 'disposition', label: '处置分流' },
  { key: 'enforcement', label: '处罚执行' },
  { key: 'post_report', label: '报案协助' },
]

const currentStepIndex = computed(() => {
  if (!workflowStatus.value) return -1
  const idx = allStages.findIndex(s => s.key === workflowStatus.value!.current_stage)
  return idx >= 0 ? idx : 0
})

function stageLabel(v?: string) { return v ? STAGE_LABELS[v] || v : '—' }
function clientLabel(v?: string) { return v ? CLIENT_LABELS[v] || v : '—' }
function sourceLabel(v?: string) { return v ? SOURCE_LABELS[v] || v : '—' }
function statusLabel(v?: string) {
  const m: Record<string, string> = { pending: '待处理', investigating: '调查中', closed: '已结案', transferred: '已转交' }
  return v ? (m[v] || v) : '—'
}
function clientTag(v?: string) { return v === 'ecovacs' ? 'success' : v === 'tineco' ? 'warning' : 'danger' }
function statusTag(v?: string) { return v === 'pending' ? 'info' : v === 'investigating' ? 'warning' : v === 'closed' ? 'success' : 'info' }

function stageStatusDesc(key: string): string {
  const histories = stageHistory.value.filter(h => h.stage_name === key)
  if (histories.length === 0) return '—'
  const latest = histories[histories.length - 1]
  if (latest.status === 'approved') return '✓ 已通过'
  if (latest.status === 'rejected') return '✗ 已驳回'
  if (latest.status === 'pending_approval') return '⏳ 待守门'
  return '—'
}

async function fetchDetail() {
  loading.value = true
  try {
    const [detailRes, statusRes, historyRes] = await Promise.allSettled([
      casesApi.get(caseId),
      workflowApi.status(caseId),
      workflowApi.history(caseId),
    ])
    if (detailRes.status === 'fulfilled') detail.value = detailRes.value.data
    if (statusRes.status === 'fulfilled') workflowStatus.value = statusRes.value.data
    if (historyRes.status === 'fulfilled') stageHistory.value = historyRes.value.data
  } finally {
    loading.value = false
  }
}

async function startWorkflow() {
  try {
    await workflowApi.start(caseId)
    ElMessage.success('工作流已启动')
    fetchDetail()
  } catch { ElMessage.error('启动失败') }
}

onMounted(fetchDetail)
</script>

<style scoped>
.text-muted { color: #909399; }
</style>
