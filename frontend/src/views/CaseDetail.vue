<template>
  <div class="case-detail" v-loading="loading">
    <!-- 头部操作栏 -->
    <div class="detail-toolbar" v-if="detail">
      <div class="toolbar-left">
        <el-button text @click="$router.push('/cases')">
          <el-icon><ArrowLeft /></el-icon> 返回列表
        </el-button>
        <el-divider direction="vertical" />
        <span class="toolbar-title">{{ detail.task_id }}</span>
        <el-tag size="small" :type="statusTag(detail.status)" effect="light" style="margin-left: 12px">
          {{ statusLabel(detail.status) }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-button
          v-if="!detail.langgraph_thread_id"
          type="success"
          :icon="VideoPlay"
          @click="startWorkflow"
        >
          启动工作流
        </el-button>
        <el-button
          v-if="detail.current_stage && detail.status !== 'closed'"
          type="warning"
          :icon="Finished"
          @click="$router.push(`/cases/${caseId}/approval`)"
        >
          碳基守门
        </el-button>
      </div>
    </div>

    <!-- 案件基本信息 -->
    <el-card class="detail-card" shadow="never">
      <template #header>
        <div class="card-header-title">
          <el-icon :size="16"><InfoFilled /></el-icon> 案件信息
        </div>
      </template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="案件编号">{{ detail?.task_id || '—' }}</el-descriptions-item>
        <el-descriptions-item label="事业部">
          <el-tag :type="clientTag(detail?.client)" effect="light">{{ clientLabel(detail?.client) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="来源">{{ sourceLabel(detail?.fraud_source) }}</el-descriptions-item>
        <el-descriptions-item label="当前阶段">
          <el-tag v-if="detail?.current_stage" type="primary" effect="light">{{ stageLabel(detail?.current_stage) }}</el-tag>
          <span v-else class="text-muted">— 未启动 —</span>
        </el-descriptions-item>
        <el-descriptions-item label="创建人">{{ detail?.created_by || '—' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ detail?.created_at || '—' }}</el-descriptions-item>
        <el-descriptions-item label="风控案件ID" :span="2">{{ detail?.risk_control_case_id || '—' }}</el-descriptions-item>
        <el-descriptions-item label="事件详情" :span="3">
          <div class="content-block">{{ detail?.fraud_event_detail || '—' }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="证据" :span="3">
          <div class="content-block">{{ detail?.proof || '—' }}</div>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 工作流阶段进度 -->
    <el-card v-if="workflowStatus" class="detail-card" shadow="never">
      <template #header>
        <div class="card-header-title">
          <el-icon :size="16"><Connection /></el-icon> 工作流进度
        </div>
      </template>
      <el-steps :active="currentStepIndex" finish-status="success" align-center>
        <el-step
          v-for="s in allStages"
          :key="s.key"
          :title="s.label"
          :description="stageStatusDesc(s.key)"
          :status="stepStatus(s.key)"
        />
      </el-steps>
    </el-card>

    <!-- 工作流历史 -->
    <el-card v-if="stageHistory.length > 0" class="detail-card" shadow="never">
      <template #header>
        <div class="card-header-title">
          <el-icon :size="16"><Timer /></el-icon> 阶段流转记录
        </div>
      </template>
      <el-timeline>
        <el-timeline-item
          v-for="item in stageHistory"
          :key="item.stage_name + (item.started_at || '')"
          :timestamp="item.started_at || ''"
          :type="item.status === 'approved' ? 'success' : item.status === 'rejected' ? 'danger' : 'primary'"
          :hollow="item.status === 'running'"
        >
          <span class="timeline-stage">{{ stageLabel(item.stage_name) }}</span>
          <el-tag size="small" :type="item.status === 'approved' ? 'success' : item.status === 'rejected' ? 'danger' : 'info'" effect="light">
            {{ item.status === 'approved' ? '已通过' : item.status === 'rejected' ? '已驳回' : item.status === 'pending_approval' ? '待守门' : item.status === 'running' ? '进行中' : item.status }}
          </el-tag>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <!-- 生成文档 -->
    <el-card class="detail-card" shadow="never">
      <template #header>
        <div class="card-header-title">
          <el-icon :size="16"><Document /></el-icon> 生成文档
        </div>
      </template>
      <el-table :data="detail?.generated_documents || []" empty-text="暂无 AI 生成的文档" stripe>
        <el-table-column label="类型" width="160">
          <template #default="{ row }">
            <el-tag size="small" effect="light">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="文件名" min-width="200">
          <template #default="{ row }">
            <el-link type="primary" :underline="false">
              <el-icon :size="14"><Document /></el-icon> {{ row.name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="format" label="格式" width="80" />
        <el-table-column prop="created_at" label="生成时间" width="180" />
      </el-table>
    </el-card>

    <!-- 空状态 -->
    <el-empty v-if="!loading && !detail" description="案件不存在或已被删除">
      <el-button type="primary" @click="$router.push('/cases')">返回案件列表</el-button>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  Connection,
  Document,
  Finished,
  InfoFilled,
  Timer,
  VideoPlay,
} from '@element-plus/icons-vue'
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
  const idx = allStages.findIndex((s) => s.key === workflowStatus.value!.current_stage)
  return idx >= 0 ? idx : 0
})

function stageLabel(v?: string) { return v ? STAGE_LABELS[v] || v : '—' }
function clientLabel(v?: string) { return v ? CLIENT_LABELS[v] || v : '—' }
function sourceLabel(v?: string) { return v ? SOURCE_LABELS[v] || v : '—' }
function statusLabel(v?: string) {
  const m: Record<string, string> = { pending: '待处理', investigating: '调查中', disposing: '处置中', enforcing: '执行中', closed: '已结案', transferred: '已转交' }
  return v ? (m[v] || v) : '—'
}
function clientTag(v?: string) { return v === 'ecovacs' ? 'success' : v === 'tineco' ? 'warning' : 'danger' }
function statusTag(v?: string) { return v === 'pending' ? 'info' : v === 'investigating' ? 'warning' : v === 'closed' ? 'success' : 'info' }

function stageStatusDesc(key: string): string {
  const histories = stageHistory.value.filter((h) => h.stage_name === key)
  if (histories.length === 0) return ''
  const latest = histories[histories.length - 1]
  if (latest.status === 'approved') return '✓ 通过'
  if (latest.status === 'rejected') return '✗ 驳回'
  if (latest.status === 'pending_approval') return '⏳ 守门中'
  if (latest.status === 'running') return '⚙ 运行中'
  return ''
}

function stepStatus(key: string) {
  const histories = stageHistory.value.filter((h) => h.stage_name === key)
  if (histories.length === 0) return 'wait'
  const latest = histories[histories.length - 1]
  if (latest.status === 'approved') return 'success'
  if (latest.status === 'rejected') return 'error'
  if (latest.status === 'running') return 'process'
  return 'wait'
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
.case-detail { max-width: 1200px; margin: 0 auto; }

/* ── 头部操作栏 ── */
.detail-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 20px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #EBEEF5;
}
.toolbar-left { display: flex; align-items: center; gap: 8px; }
.toolbar-right { display: flex; gap: 8px; }
.toolbar-title { font-size: 15px; font-weight: 600; color: #303133; }

/* ── 内容卡片 ── */
.detail-card { margin-bottom: 16px; border-radius: 8px; }
.card-header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #303133;
}

/* ── 内容块 ── */
.content-block {
  white-space: pre-wrap;
  line-height: 1.8;
  color: #606266;
}

.timeline-stage {
  font-weight: 500;
  margin-right: 8px;
}

.text-muted { color: #909399; }
</style>
