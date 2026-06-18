<template>
  <div class="scan-dashboard">
    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card stat-card--rules">
        <div class="stat-card-icon"><el-icon :size="24"><List /></el-icon></div>
        <div class="stat-card-body">
          <span class="stat-card-num">{{ stats.activeRules }}</span>
          <span class="stat-card-label">生效规则</span>
        </div>
      </div>
      <div class="stat-card stat-card--scans">
        <div class="stat-card-icon"><el-icon :size="24"><VideoPlay /></el-icon></div>
        <div class="stat-card-body">
          <span class="stat-card-num">{{ stats.todayScans }}</span>
          <span class="stat-card-label">今日扫描批次</span>
        </div>
      </div>
      <div class="stat-card stat-card--pending">
        <div class="stat-card-icon"><el-icon :size="24"><Clock /></el-icon></div>
        <div class="stat-card-body">
          <span class="stat-card-num">{{ stats.pendingAlerts }}</span>
          <span class="stat-card-label">待审核预警</span>
        </div>
      </div>
      <div class="stat-card stat-card--pushed">
        <div class="stat-card-icon"><el-icon :size="24"><Finished /></el-icon></div>
        <div class="stat-card-body">
          <span class="stat-card-num">{{ stats.pushedAlerts }}</span>
          <span class="stat-card-label">已推送预警</span>
        </div>
      </div>
    </div>

    <!-- 扫描配置 -->
    <el-card shadow="never" class="config-card">
      <template #header>
        <div class="config-header">
          <span>
            <el-icon :size="16"><Timer /></el-icon>
            定时扫描配置
          </span>
          <el-tag type="success" size="small" effect="light">7×24 无人值守运行中</el-tag>
        </div>
      </template>
      <el-descriptions :column="3" size="small" border>
        <el-descriptions-item label="扫描频率">每 4 小时一次</el-descriptions-item>
        <el-descriptions-item label="上次扫描">2026-06-18 14:00</el-descriptions-item>
        <el-descriptions-item label="下次扫描">2026-06-18 18:00</el-descriptions-item>
        <el-descriptions-item label="生效规则数">{{ stats.activeRules }}</el-descriptions-item>
        <el-descriptions-item label="覆盖事业部">科沃斯 / 添可 / 集团</el-descriptions-item>
        <el-descriptions-item label="扫描 Worker">3 路并行（按事业部隔离）</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 手动触发 -->
    <el-card shadow="never" class="trigger-card">
      <template #header>
        <span>
          <el-icon :size="16"><CaretRight /></el-icon>
          手动触发扫描
        </span>
      </template>
      <el-form :model="triggerForm" inline>
        <el-form-item label="目标规则">
          <el-select v-model="triggerForm.target_rules" placeholder="全部生效规则" clearable multiple filterable style="width: 320px">
            <el-option
              v-for="r in activeRules"
              :key="r.id"
              :label="`${r.rule_code} - ${r.level3_scene}`"
              :value="r.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="目标事业部">
          <el-select v-model="triggerForm.target_business_units" placeholder="全部事业部" clearable multiple style="width: 200px">
            <el-option label="科沃斯" value="ecovacs" />
            <el-option label="添可" value="tineco" />
            <el-option label="集团" value="group" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="VideoPlay" :loading="triggering" @click="handleTrigger">立即扫描</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 扫描任务列表 -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <span>近期扫描任务（共 {{ total }} 批次）</span>
      </template>
      <el-table :data="scans" v-loading="loading" stripe>
        <el-table-column prop="scan_id" label="批次编号" width="170" />
        <el-table-column prop="scan_time" label="扫描时间" width="180" />
        <el-table-column label="预警数量" width="100">
          <template #default="{ row }">{{ row.alert_count }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.status === 'completed' ? 'success' : 'warning'" size="small" effect="light">
              {{ row.status === 'completed' ? '已完成' : '进行中' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="navigateToAlerts(row.scan_id)">查看预警</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          :page-size="pagination.pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchScans"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { List, VideoPlay, Clock, Finished, Timer, CaretRight } from '@element-plus/icons-vue'
import { riskMonitorApi } from '@/api'
import type { RiskScanTask } from '@/types'

const router = useRouter()
const scans = ref<RiskScanTask[]>([])
const loading = ref(false)
const triggering = ref(false)
const total = ref(0)

const activeRules = ref<Array<{ id: string; rule_code: string; level3_scene: string }>>([])

const stats = reactive({
  activeRules: 0,
  todayScans: 0,
  pendingAlerts: 0,
  pushedAlerts: 0,
})

const pagination = reactive({ page: 1, pageSize: 20 })

const triggerForm = reactive({
  target_rules: [] as string[],
  target_business_units: [] as string[],
})

async function fetchScans() {
  loading.value = true
  try {
    const res = await riskMonitorApi.scans.list({ page: pagination.page, page_size: pagination.pageSize })
    scans.value = res.data.items
    total.value = res.data.total

    // 更新统计信息
    stats.todayScans = res.data.items.filter((s: { status: string }) => s.status === 'completed').length
    stats.pendingAlerts = 0 // TODO: 从预警列表获取
    stats.pushedAlerts = 0 // TODO: 从预警列表获取
  } catch {
    // 扫描数据可能为空，静默处理
  } finally {
    loading.value = false
  }
}

async function fetchActiveRules() {
  try {
    const res = await riskMonitorApi.rules.list({ status: 'active', page_size: 100 })
    stats.activeRules = res.data.total
    activeRules.value = res.data.items.map((r: { id: string; rule_code: string; level3_scene: string }) => ({ id: r.id, rule_code: r.rule_code, level3_scene: r.level3_scene }))
  } catch { /* ignore */ }
}

async function handleTrigger() {
  triggering.value = true
  try {
    const data: Record<string, unknown> = {}
    if (triggerForm.target_rules.length > 0) data.target_rules = triggerForm.target_rules.join(',')
    if (triggerForm.target_business_units.length > 0) data.target_business_units = triggerForm.target_business_units.join(',')
    const res = await riskMonitorApi.scans.trigger(data)
    ElMessage.success(res.data.message)
    fetchScans()
  } catch {
    ElMessage.error('触发扫描失败')
  } finally {
    triggering.value = false
  }
}

function navigateToAlerts(scanId: string) {
  router.push(`/risk-monitor/alerts?scan=${scanId}`)
}

onMounted(() => {
  fetchScans()
  fetchActiveRules()
})
</script>

<style scoped>
.scan-dashboard { max-width: 1400px; margin: 0 auto; }

.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
.stat-card { display: flex; align-items: center; gap: 16px; padding: 20px; border-radius: 10px; background: #fff; border: 1px solid #EBEEF5; transition: all 0.2s ease; }
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
.stat-card-icon { width: 48px; height: 48px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.stat-card--rules .stat-card-icon { background: #409EFF15; color: #409EFF; }
.stat-card--scans .stat-card-icon { background: #67C23A15; color: #67C23A; }
.stat-card--pending .stat-card-icon { background: #E6A23C15; color: #E6A23C; }
.stat-card--pushed .stat-card-icon { background: #9B59B615; color: #9B59B6; }
.stat-card-body { display: flex; flex-direction: column; }
.stat-card-num { font-size: 24px; font-weight: 700; color: #303133; line-height: 1.2; }
.stat-card-label { font-size: 13px; color: #909399; margin-top: 2px; }

.config-card, .trigger-card { margin-bottom: 16px; border-radius: 8px; }
.config-header { display: flex; justify-content: space-between; align-items: center; }
.table-card { border-radius: 8px; }

.pagination-wrapper { margin-top: 16px; display: flex; justify-content: center; }
</style>
