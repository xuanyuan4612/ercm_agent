<template>
  <div class="alert-list">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <h2>
          <el-icon :size="22"><Bell /></el-icon>
          风险预警列表
        </h2>
        <p class="page-desc">查看和管理风险扫描产生的预警，支持逐条审核与风险定性</p>
      </div>
    </div>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-form :model="filters" inline>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width: 120px" @change="search">
            <el-option v-for="(label, key) in ALERT_STATUS_LABELS" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="风险类型">
          <el-select v-model="filters.risk_type" clearable placeholder="全部" style="width: 140px" @change="search">
            <el-option label="舞弊风险" value="舞弊风险" />
            <el-option label="合规风险" value="合规风险" />
            <el-option label="商业秘密风险" value="商业秘密风险" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item label="风险等级">
          <el-select v-model="filters.risk_level" clearable placeholder="全部" style="width: 120px" @change="search">
            <el-option label="高风险" value="高" />
            <el-option label="中风险" value="中" />
            <el-option label="低风险" value="低" />
          </el-select>
        </el-form-item>
        <el-form-item label="事业部">
          <el-select v-model="filters.business_unit" clearable placeholder="全部" style="width: 120px" @change="search">
            <el-option label="科沃斯" value="ecovacs" />
            <el-option label="添可" value="tineco" />
            <el-option label="集团" value="group" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键字">
          <el-input v-model="filters.keyword" placeholder="预警编码 / 风险类型" clearable style="width: 200px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="search">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 预警表格 -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <span>预警列表（共 {{ total }} 条）</span>
      </template>
      <el-table :data="alerts" v-loading="loading" stripe highlight-current-row @row-click="goDetail">
        <el-table-column prop="alert_code" label="预警编码" width="130" />
        <el-table-column label="分析主体" min-width="160">
          <template #default="{ row }">
            <span class="subject-name">{{ row.analysis_subject_id ? '已关联主体' : '待合并' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险类型" width="120">
          <template #default="{ row }">{{ row.risk_type }}</template>
        </el-table-column>
        <el-table-column label="风险等级" width="90">
          <template #default="{ row }">
            <el-tag :type="row.risk_level === '高' ? 'danger' : row.risk_level === '中' ? 'warning' : 'info'" size="small" effect="light">
              {{ RISK_LEVEL_LABELS[row.risk_level] || row.risk_level }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="严重程度" width="90">
          <template #default="{ row }">{{ row.severity || '-' }}</template>
        </el-table-column>
        <el-table-column label="涉及金额" width="120">
          <template #default="{ row }">{{ row.impact_amount ? `¥${row.impact_amount.toLocaleString()}` : '-' }}</template>
        </el-table-column>
        <el-table-column label="预警时间" width="170">
          <template #default="{ row }">{{ row.alert_time || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="ALERT_STATUS_TYPES[row.status] || 'info'" size="small" effect="light">
              {{ ALERT_STATUS_LABELS[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div class="action-cells">
              <el-button size="small" link type="primary" @click.stop="goDetail(row)">详情</el-button>
              <el-button
                v-if="row.status === 'pending' || row.status === 'reviewing'"
                size="small" link type="warning"
                @click.stop="goDetail(row)"
              >审核</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          :page-size="pagination.pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchAlerts"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Bell } from '@element-plus/icons-vue'
import { riskMonitorApi } from '@/api'
import { ALERT_STATUS_LABELS, ALERT_STATUS_TYPES, RISK_LEVEL_LABELS } from '@/types'
import type { RiskAlertBrief } from '@/types'

const router = useRouter()
const alerts = ref<RiskAlertBrief[]>([])
const loading = ref(false)
const total = ref(0)

const filters = reactive({
  status: '',
  risk_type: '',
  risk_level: '',
  business_unit: '',
  keyword: '',
})

const pagination = reactive({ page: 1, pageSize: 20 })

async function fetchAlerts() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: pagination.page, page_size: pagination.pageSize }
    if (filters.status) params.status = filters.status
    if (filters.risk_type) params.risk_type = filters.risk_type
    if (filters.risk_level) params.risk_level = filters.risk_level
    if (filters.business_unit) params.business_unit = filters.business_unit
    if (filters.keyword) params.keyword = filters.keyword
    const res = await riskMonitorApi.alerts.list(params)
    alerts.value = res.data.items
    total.value = res.data.total
  } catch {
    ElMessage.error('查询预警列表失败')
  } finally {
    loading.value = false
  }
}

function search() { pagination.page = 1; fetchAlerts() }
function resetFilters() {
  filters.status = ''; filters.risk_type = ''; filters.risk_level = ''; filters.business_unit = ''; filters.keyword = ''
  search()
}
function goDetail(row: RiskAlertBrief) { router.push(`/risk-monitor/alerts/${row.id}`) }

onMounted(fetchAlerts)
</script>

<style scoped>
.alert-list { max-width: 1400px; margin: 0 auto; }

.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0 0 6px 0; display: flex; align-items: center; gap: 8px; color: #303133; }
.page-desc { margin: 0; color: #909399; font-size: 13px; }

.filter-card { margin-bottom: 16px; border-radius: 8px; }
.table-card { border-radius: 8px; }

.subject-name { font-size: 13px; }
.action-cells { display: flex; gap: 2px; }
.pagination-wrapper { margin-top: 16px; display: flex; justify-content: center; }
</style>
