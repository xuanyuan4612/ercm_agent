<template>
  <div class="case-list">
    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card stat-card--total">
        <div class="stat-card-icon">
          <el-icon :size="24"><Document /></el-icon>
        </div>
        <div class="stat-card-body">
          <span class="stat-card-num">{{ total }}</span>
          <span class="stat-card-label">案件总数</span>
        </div>
      </div>
      <div class="stat-card stat-card--pending">
        <div class="stat-card-icon">
          <el-icon :size="24"><Clock /></el-icon>
        </div>
        <div class="stat-card-body">
          <span class="stat-card-num">{{ statusCounts.pending }}</span>
          <span class="stat-card-label">待处理</span>
        </div>
      </div>
      <div class="stat-card stat-card--active">
        <div class="stat-card-icon">
          <el-icon :size="24"><Loading /></el-icon>
        </div>
        <div class="stat-card-body">
          <span class="stat-card-num">{{ statusCounts.investigating + statusCounts.disposing + statusCounts.enforcing }}</span>
          <span class="stat-card-label">处理中</span>
        </div>
      </div>
      <div class="stat-card stat-card--closed">
        <div class="stat-card-icon">
          <el-icon :size="24"><CircleCheckFilled /></el-icon>
        </div>
        <div class="stat-card-body">
          <span class="stat-card-num">{{ statusCounts.closed }}</span>
          <span class="stat-card-label">已结案</span>
        </div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <el-card class="filter-card" shadow="never">
      <el-form :model="filters" inline>
        <el-form-item label="事业部">
          <el-select v-model="filters.client" clearable placeholder="全部" style="width: 120px">
            <el-option label="科沃斯" value="ecovacs" />
            <el-option label="添可" value="tineco" />
            <el-option label="集团" value="group" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-select v-model="filters.source" clearable placeholder="全部" style="width: 130px">
            <el-option label="手动录入" value="manual" />
            <el-option label="公众号" value="wechat" />
            <el-option label="邮箱举报" value="email" />
            <el-option label="电话举报" value="phone" />
            <el-option label="智能体推送" value="agent" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width: 120px">
            <el-option label="待处理" value="pending" />
            <el-option label="调查中" value="investigating" />
            <el-option label="处置中" value="disposing" />
            <el-option label="执行中" value="enforcing" />
            <el-option label="已结案" value="closed" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键字">
          <el-input v-model="filters.keyword" placeholder="案件编号 / 详情" clearable style="width: 200px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="search">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 案件表格 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="table-header">
          <span>案件列表（共 {{ total }} 条）</span>
          <el-button type="primary" size="small" @click="$router.push('/cases/create')">
            <el-icon><Plus /></el-icon> 创建案件
          </el-button>
        </div>
      </template>
      <el-table :data="cases" v-loading="loading" stripe highlight-current-row>
        <el-table-column prop="task_id" label="案件编号" width="170" />
        <el-table-column label="事业部" width="90">
          <template #default="{ row }">
            <el-tag :type="clientTagType(row.client)" size="small" effect="light">{{ clientLabel(row.client) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="110">
          <template #default="{ row }">{{ sourceLabel(row.fraud_source) }}</template>
        </el-table-column>
        <el-table-column label="当前阶段" width="170">
          <template #default="{ row }">
            <div class="stage-cell">
              <el-icon v-if="row.current_stage" :size="14" :color="stageIconColor(row.current_stage)">
                <component :is="stageIcon(row.current_stage)" />
              </el-icon>
              <el-tag v-if="row.current_stage" :type="stageTagType(row.current_stage)" size="small" effect="light">
                {{ stageLabel(row.current_stage) }}
              </el-tag>
              <span v-else class="text-muted">— 未启动 —</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" effect="light">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建人" width="100" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div class="action-cells">
              <el-button size="small" link type="primary" @click="$router.push(`/cases/${row.id}`)">详情</el-button>
              <el-button
                v-if="!row.current_stage"
                size="small"
                type="success"
                @click="startWorkflow(row)"
              >
                启动流程
              </el-button>
              <el-button
                v-if="row.current_stage && row.status !== 'closed'"
                size="small"
                type="warning"
                @click="$router.push(`/cases/${row.id}/approval`)"
              >
                守门
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          :page-size="pagination.pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchCases"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Loading, Clock, CircleCheckFilled } from '@element-plus/icons-vue'
import { casesApi, workflowApi } from '@/api'
import { CLIENT_LABELS, SOURCE_LABELS, STAGE_LABELS } from '@/types'
import type { CaseBrief } from '@/types'

const cases = ref<CaseBrief[]>([])
const loading = ref(false)
const total = ref(0)

const filters = reactive({
  client: '',
  source: '',
  status: '',
  keyword: '',
})

const pagination = reactive({ page: 1, pageSize: 20 })

// 状态统计
const statusCounts = computed(() => {
  const counts: Record<string, number> = { pending: 0, investigating: 0, disposing: 0, enforcing: 0, closed: 0, transferred: 0 }
  for (const c of cases.value) {
    if (c.status && counts[c.status] !== undefined) counts[c.status]++
  }
  return counts
})

// ── Label helpers ──
function clientLabel(v: string) { return CLIENT_LABELS[v] || v }
function sourceLabel(v: string) { return SOURCE_LABELS[v] || v }
function stageLabel(v: string) { return STAGE_LABELS[v] || v }
function statusLabel(v: string) {
  const m: Record<string, string> = { pending: '待处理', investigating: '调查中', disposing: '处置中', enforcing: '执行中', closed: '已结案', transferred: '已转交' }
  return m[v] || v
}
function clientTagType(v: string) {
  const m: Record<string, string> = { ecovacs: 'success', tineco: 'warning', group: 'danger' }
  return m[v] || 'info'
}
function stageTagType(v: string) {
  const m: Record<string, string> = { intake: '', investigation: 'primary', analysis: 'warning', disposition: 'danger', enforcement: 'success', post_report: 'info' }
  return m[v] || 'info'
}
function statusTagType(v: string) {
  const m: Record<string, string> = { pending: 'info', investigating: 'warning', disposing: 'warning', enforcing: '', closed: 'success', transferred: '' }
  return m[v] || 'info'
}
function stageIcon(v: string) {
  const m: Record<string, string> = { intake: 'Search', investigation: 'DocumentCopy', analysis: 'DataAnalysis', disposition: 'Connection', enforcement: 'Finished', post_report: 'Message' }
  return m[v] || 'Operation'
}
function stageIconColor(v: string) {
  const m: Record<string, string> = { intake: '#909399', investigation: '#409EFF', analysis: '#E6A23C', disposition: '#F56C6C', enforcement: '#67C23A', post_report: '#909399' }
  return m[v] || '#909399'
}

// ── API ──
async function fetchCases() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: pagination.page, page_size: pagination.pageSize }
    if (filters.client) params.client = filters.client
    if (filters.source) params.source = filters.source
    if (filters.status) params.status = filters.status
    if (filters.keyword) params.keyword = filters.keyword
    const res = await casesApi.list(params)
    cases.value = res.data.items
    total.value = res.data.total
  } catch {
    ElMessage.error('查询案件列表失败')
  } finally {
    loading.value = false
  }
}

function search() { pagination.page = 1; fetchCases() }
function resetFilters() {
  filters.client = ''; filters.source = ''; filters.status = ''; filters.keyword = ''
  search()
}

async function startWorkflow(row: CaseBrief) {
  try {
    await workflowApi.start(row.id)
    ElMessage.success('工作流已启动')
    fetchCases()
  } catch {
    ElMessage.error('启动工作流失败')
  }
}

onMounted(fetchCases)
</script>

<style scoped>
.case-list { max-width: 1400px; margin: 0 auto; }

/* ── 统计卡片 ── */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid #EBEEF5;
  transition: all 0.2s ease;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
.stat-card-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-card--total .stat-card-icon { background: #409EFF15; color: #409EFF; }
.stat-card--pending .stat-card-icon { background: #90939915; color: #909399; }
.stat-card--active .stat-card-icon { background: #E6A23C15; color: #E6A23C; }
.stat-card--closed .stat-card-icon { background: #67C23A15; color: #67C23A; }

.stat-card-body { display: flex; flex-direction: column; }
.stat-card-num { font-size: 24px; font-weight: 700; color: #303133; line-height: 1.2; }
.stat-card-label { font-size: 13px; color: #909399; margin-top: 2px; }

/* ── 卡片 ── */
.filter-card { margin-bottom: 16px; border-radius: 8px; }
.table-card { border-radius: 8px; }
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* ── 表格 ── */
.stage-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.action-cells {
  display: flex;
  gap: 4px;
  align-items: center;
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}

.text-muted { color: #909399; font-size: 13px; }

@media (max-width: 768px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
