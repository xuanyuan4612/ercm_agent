<template>
  <div class="rule-list">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <h2>
          <el-icon :size="22"><WarningFilled /></el-icon>
          风险规则管理
        </h2>
        <p class="page-desc">管理 7×24 自动扫描的风险规则清单，支持规则录入、AI 生成与审批</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" :icon="Plus" @click="$router.push('/risk-monitor/rules/create')">创建规则</el-button>
        <el-button :icon="Upload" @click="handleUpload">上传清单</el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-form :model="filters" inline>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width: 120px" @change="search">
            <el-option v-for="(label, key) in RISK_RULE_STATUS_LABELS" :key="key" :label="label" :value="key" />
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
          <el-input v-model="filters.keyword" placeholder="规则编码 / 场景 / SQL" clearable style="width: 260px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="search">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 规则表格 -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <span>规则列表（共 {{ total }} 条）</span>
      </template>
      <el-table :data="rules" v-loading="loading" stripe highlight-current-row @row-click="showDetail">
        <el-table-column prop="rule_code" label="规则编码" width="130" />
        <el-table-column label="风险场景" min-width="240">
          <template #default="{ row }">
            <div class="scene-cell">
              <span v-if="row.level1_scene" class="scene-l1">{{ row.level1_scene }}</span>
              <span v-if="row.level2_scene" class="scene-sep"> › </span>
              <span v-if="row.level2_scene" class="scene-l2">{{ row.level2_scene }}</span>
              <span class="scene-sep"> › </span>
              <span class="scene-l3">{{ row.level3_scene }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="90">
          <template #default="{ row }">
            <el-tag :type="row.risk_level === '高' ? 'danger' : row.risk_level === '中' ? 'warning' : 'info'" size="small" effect="light">
              {{ RISK_LEVEL_LABELS[row.risk_level] || row.risk_level }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="监控频率" width="100">
          <template #default="{ row }">
            {{ FREQUENCY_LABELS[row.monitor_frequency] || row.monitor_frequency }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="RISK_RULE_STATUS_TYPES[row.status] || 'info'" size="small" effect="light">
              {{ RISK_RULE_STATUS_LABELS[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建人" width="90" />
        <el-table-column prop="created_at" label="创建时间" width="170" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div class="action-cells">
              <el-button size="small" link type="primary" @click.stop="showDetail(row)">详情</el-button>
              <el-button
                v-if="row.status === 'draft' || row.status === 'rejected'"
                size="small" link type="warning"
                @click.stop="$router.push(`/risk-monitor/rules/create?id=${row.id}`)"
              >编辑</el-button>
              <el-button
                v-if="row.status === 'pending_review'"
                size="small" link type="success"
                @click.stop="$router.push(`/risk-monitor/rules/${row.id}/approval`)"
              >审批</el-button>
              <el-button
                v-if="row.status !== 'deprecated'"
                size="small" link type="danger"
                @click.stop="handleDeactivate(row)"
              >禁用</el-button>
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
          @current-change="fetchRules"
        />
      </div>
    </el-card>

    <!-- 规则详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="规则详情" size="600px">
      <template v-if="selectedRule">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="规则编码" :span="2">{{ selectedRule.rule_code }}</el-descriptions-item>
          <el-descriptions-item label="事业部">{{ selectedRule.business_unit || '-' }}</el-descriptions-item>
          <el-descriptions-item label="渠道">{{ selectedRule.channel || '-' }}</el-descriptions-item>
          <el-descriptions-item label="业态">{{ selectedRule.format || '-' }}</el-descriptions-item>
          <el-descriptions-item label="业务循环">{{ selectedRule.business_cycle || '-' }}</el-descriptions-item>
          <el-descriptions-item label="部门">{{ selectedRule.department || '-' }}</el-descriptions-item>
          <el-descriptions-item label="岗位">{{ selectedRule.position || '-' }}</el-descriptions-item>
          <el-descriptions-item label="一级场景">{{ selectedRule.level1_scene || '-' }}</el-descriptions-item>
          <el-descriptions-item label="二级场景">{{ selectedRule.level2_scene || '-' }}</el-descriptions-item>
          <el-descriptions-item label="三级场景">{{ selectedRule.level3_scene }}</el-descriptions-item>
          <el-descriptions-item label="风险等级">
            <el-tag :type="selectedRule.risk_level === '高' ? 'danger' : selectedRule.risk_level === '中' ? 'warning' : 'info'" size="small">
              {{ RISK_LEVEL_LABELS[selectedRule.risk_level] || selectedRule.risk_level }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="阈值">{{ selectedRule.threshold ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="监控频率">{{ FREQUENCY_LABELS[selectedRule.monitor_frequency] || selectedRule.monitor_frequency }}</el-descriptions-item>
          <el-descriptions-item label="监控事业部">{{ selectedRule.monitor_business_unit || '-' }}</el-descriptions-item>
          <el-descriptions-item label="外部数据">{{ selectedRule.use_external_data ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="RISK_RULE_STATUS_TYPES[selectedRule.status] || 'info'" size="small">
              {{ RISK_RULE_STATUS_LABELS[selectedRule.status] || selectedRule.status }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="版本">v{{ selectedRule.version }}</el-descriptions-item>
          <el-descriptions-item label="SQL 语句" :span="2">
            <pre class="sql-block">{{ selectedRule.sql_statement }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, Upload, WarningFilled } from '@element-plus/icons-vue'
import { riskMonitorApi } from '@/api'
import {
  RISK_RULE_STATUS_LABELS,
  RISK_RULE_STATUS_TYPES,
  RISK_LEVEL_LABELS,
  FREQUENCY_LABELS,
} from '@/types'
import type { RiskRule } from '@/types'

const rules = ref<RiskRule[]>([])
const loading = ref(false)
const total = ref(0)
const drawerVisible = ref(false)
const selectedRule = ref<RiskRule | null>(null)

const filters = reactive({
  status: '',
  risk_level: '',
  business_unit: '',
  keyword: '',
})

const pagination = reactive({ page: 1, pageSize: 20 })

async function fetchRules() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: pagination.page, page_size: pagination.pageSize }
    if (filters.status) params.status = filters.status
    if (filters.risk_level) params.risk_level = filters.risk_level
    if (filters.business_unit) params.business_unit = filters.business_unit
    if (filters.keyword) params.keyword = filters.keyword
    const res = await riskMonitorApi.rules.list(params)
    rules.value = res.data.items
    total.value = res.data.total
  } catch {
    ElMessage.error('查询规则列表失败')
  } finally {
    loading.value = false
  }
}

function search() { pagination.page = 1; fetchRules() }
function resetFilters() {
  filters.status = ''; filters.risk_level = ''; filters.business_unit = ''; filters.keyword = ''
  search()
}

async function showDetail(row: RiskRule) {
  try {
    const res = await riskMonitorApi.rules.get(row.id)
    selectedRule.value = res.data.rule
    drawerVisible.value = true
  } catch {
    ElMessage.error('获取规则详情失败')
  }
}

async function handleDeactivate(row: RiskRule) {
  try {
    await ElMessageBox.confirm(`确定要禁用规则 ${row.rule_code} 吗？`, '确认操作', { type: 'warning' })
    await riskMonitorApi.rules.delete(row.id)
    ElMessage.success('规则已禁用')
    fetchRules()
  } catch { /* cancelled */ }
}

function handleUpload() {
  ElMessage.info('清单上传功能即将上线，请使用"创建规则"进行人工录入')
}

onMounted(fetchRules)
</script>

<style scoped>
.rule-list { max-width: 1400px; margin: 0 auto; }

.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-header h2 { margin: 0 0 6px 0; display: flex; align-items: center; gap: 8px; color: #303133; }
.page-desc { margin: 0; color: #909399; font-size: 13px; }
.header-actions { display: flex; gap: 8px; flex-shrink: 0; }

.filter-card { margin-bottom: 16px; border-radius: 8px; }
.table-card { border-radius: 8px; }

.scene-cell { font-size: 13px; }
.scene-l1 { color: #909399; }
.scene-l2 { color: #606266; }
.scene-l3 { color: #303133; font-weight: 500; }
.scene-sep { color: #C0C4CC; margin: 0 2px; }

.action-cells { display: flex; gap: 2px; }
.sql-block { background: #F5F7FA; padding: 12px; border-radius: 6px; font-size: 12px; font-family: 'Cascadia Code', 'SF Mono', monospace; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow: auto; }
.pagination-wrapper { margin-top: 16px; display: flex; justify-content: center; }
</style>
