<template>
  <div class="case-list">
    <!-- 筛选栏 -->
    <el-card style="margin-bottom: 16px">
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
          <el-input v-model="filters.keyword" placeholder="搜索案件编号/详情" clearable style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 案件列表 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>案件列表（共 {{ total }} 条）</span>
          <el-button type="primary" size="small" @click="$router.push('/cases/create')">
            <el-icon><Plus /></el-icon> 创建案件
          </el-button>
        </div>
      </template>
      <el-table :data="cases" v-loading="loading" stripe>
        <el-table-column prop="task_id" label="案件编号" width="160" />
        <el-table-column label="事业部" width="80">
          <template #default="{ row }">
            <el-tag :type="clientTagType(row.client)" size="small">{{ clientLabel(row.client) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">{{ sourceLabel(row.fraud_source) }}</template>
        </el-table-column>
        <el-table-column label="当前阶段" width="160">
          <template #default="{ row }">
            <el-tag v-if="row.current_stage" :type="stageTagType(row.current_stage)" size="small">
              {{ stageLabel(row.current_stage) }}
            </el-tag>
            <span v-else class="text-muted">— 未启动 —</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建人" width="100" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/cases/${row.id}`)">详情</el-button>
            <el-button v-if="!row.current_stage" size="small" type="success" @click="startWorkflow(row)">启动流程</el-button>
            <el-button v-if="row.current_stage && row.status !== 'closed'" size="small" type="warning" @click="$router.push(`/cases/${row.id}/approval`)">守门</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div style="margin-top: 16px; display: flex; justify-content: center">
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
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
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
  const m: Record<string, string> = { intake: 'info', investigation: 'primary', analysis: 'warning', disposition: 'danger', enforcement: 'success', post_report: '' }
  return m[v] || 'info'
}
function statusTagType(v: string) {
  const m: Record<string, string> = { pending: 'info', investigating: 'warning', closed: 'success', transferred: '' }
  return m[v] || 'info'
}

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
.text-muted { color: #909399; }
</style>
