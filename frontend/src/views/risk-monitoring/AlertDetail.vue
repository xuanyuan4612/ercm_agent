<template>
  <div class="alert-detail">
    <el-card shadow="never" class="detail-card" v-loading="loading">
      <template #header>
        <div class="detail-header">
          <div>
            <h3>
              <el-icon :size="20"><Bell /></el-icon>
              预警详情 — {{ alert?.alert_code }}
            </h3>
            <p class="detail-desc">风险扫描预警的完整信息与碳基守门审核</p>
          </div>
          <div class="header-badges">
            <el-tag :type="alert?.risk_level === '高' ? 'danger' : alert?.risk_level === '中' ? 'warning' : 'info'" size="large" effect="light">
              {{ RISK_LEVEL_LABELS[alert?.risk_level || ''] || alert?.risk_level }}
            </el-tag>
            <el-tag :type="ALERT_STATUS_TYPES[alert?.status || ''] || 'info'" size="large" effect="light" style="margin-left: 8px">
              {{ ALERT_STATUS_LABELS[alert?.status || ''] || alert?.status }}
            </el-tag>
          </div>
        </div>
      </template>

      <template v-if="alert">
        <!-- 阶段时间线 -->
        <div class="stage-timeline">
          <el-steps :active="currentStepIndex" align-center>
            <el-step
              v-for="(label, key) in RISK_STAGE_LABELS"
              :key="key"
              :title="label"
              :status="key === currentStage ? 'process' : stepStatus(key)"
            />
          </el-steps>
        </div>

        <el-divider />

        <!-- 基本信息 -->
        <div class="form-section">
          <div class="form-section-title">基本信息</div>
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="预警编码">{{ alert.alert_code }}</el-descriptions-item>
            <el-descriptions-item label="风险类型">{{ alert.risk_type }}</el-descriptions-item>
            <el-descriptions-item label="风险等级">
              <el-tag :type="alert.risk_level === '高' ? 'danger' : alert.risk_level === '中' ? 'warning' : 'info'" size="small">
                {{ RISK_LEVEL_LABELS[alert.risk_level] || alert.risk_level }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="事业部">{{ alert.business_unit || '-' }}</el-descriptions-item>
            <el-descriptions-item label="预警时间">{{ alert.alert_time || '-' }}</el-descriptions-item>
            <el-descriptions-item label="涉及金额">{{ alert.impact_amount ? `¥${alert.impact_amount.toLocaleString()}` : '-' }}</el-descriptions-item>
            <el-descriptions-item label="严重程度">{{ alert.severity || '-' }}</el-descriptions-item>
            <el-descriptions-item label="广泛性">{{ alert.widespread || '-' }}</el-descriptions-item>
            <el-descriptions-item label="影响程度">{{ alert.impact_degree || '-' }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 处置建议 -->
        <div class="form-section" v-if="alert.handling_suggestion">
          <div class="form-section-title">处置建议</div>
          <el-alert type="warning" :closable="false" show-icon>
            <template #title>{{ alert.handling_suggestion }}</template>
          </el-alert>
        </div>

        <!-- 关联规则 -->
        <div class="form-section" v-if="alert.rule">
          <div class="form-section-title">触发规则</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="规则编码">{{ alert.rule.rule_code }}</el-descriptions-item>
            <el-descriptions-item label="三级场景">{{ alert.rule.level3_scene }}</el-descriptions-item>
            <el-descriptions-item label="SQL 语句" :span="2">
              <pre class="sql-block">{{ alert.rule.sql_statement }}</pre>
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 分析主体 -->
        <div class="form-section" v-if="alert.analysis_subject">
          <div class="form-section-title">分析主体</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="主体编码">{{ alert.analysis_subject.subject_code }}</el-descriptions-item>
            <el-descriptions-item label="主体名称">{{ alert.analysis_subject.subject_name }}</el-descriptions-item>
            <el-descriptions-item label="主体类型">{{ alert.analysis_subject.subject_type }}</el-descriptions-item>
            <el-descriptions-item label="涉及金额">{{ alert.analysis_subject.involved_amount ? `¥${alert.analysis_subject.involved_amount.toLocaleString()}` : '-' }}</el-descriptions-item>
            <el-descriptions-item label="风险行为" :span="2">{{ alert.analysis_subject.risk_behavior || '-' }}</el-descriptions-item>
            <el-descriptions-item label="风险业务" :span="2">{{ alert.analysis_subject.risk_business || '-' }}</el-descriptions-item>
            <el-descriptions-item label="影响范围" :span="2">{{ alert.analysis_subject.impact_scope || '-' }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 推送记录 -->
        <div class="form-section" v-if="alert.push_records && alert.push_records.length > 0">
          <div class="form-section-title">推送记录</div>
          <el-table :data="alert.push_records" size="small" border>
            <el-table-column label="目标模块" width="140">
              <template #default="{ row }">{{ PUSH_MODULE_LABELS[row.target_module] || row.target_module }}</template>
            </el-table-column>
            <el-table-column label="推送状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.push_status === 'success' ? 'success' : row.push_status === 'failed' ? 'danger' : 'warning'" size="small">
                  {{ row.push_status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="回调状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.callback_status === 'success' ? 'success' : row.callback_status === 'failed' ? 'danger' : 'info'" size="small">
                  {{ row.callback_status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="push_at" label="推送时间" width="170" />
            <el-table-column prop="callback_at" label="回调时间" width="170" />
          </el-table>
        </div>

        <el-divider />

        <!-- 碳基守门操作区 -->
        <div class="approval-section" v-if="alert.status === 'pending' || alert.status === 'reviewing'">
          <h4>
            <el-icon :size="18"><CircleCheck /></el-icon>
            碳基守门 — 风险定性审核
          </h4>
          <el-form :model="approvalForm" label-width="100px">
            <el-row :gutter="20">
              <el-col :span="8">
                <el-form-item label="修正风险类型">
                  <el-select v-model="approvalForm.modifications.risk_type" clearable placeholder="保持原值" style="width: 100%">
                    <el-option label="舞弊风险" value="舞弊风险" />
                    <el-option label="合规风险" value="合规风险" />
                    <el-option label="商业秘密风险" value="商业秘密风险" />
                    <el-option label="其他" value="其他" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="修正风险等级">
                  <el-select v-model="approvalForm.modifications.risk_level" clearable placeholder="保持原值" style="width: 100%">
                    <el-option label="高风险" value="高" />
                    <el-option label="中风险" value="中" />
                    <el-option label="低风险" value="低" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="修正严重程度">
                  <el-input v-model="approvalForm.modifications.severity" placeholder="保持原值" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="修正处置建议">
              <el-input v-model="approvalForm.modifications.handling_suggestion" type="textarea" :rows="2" placeholder="保持原处置建议" />
            </el-form-item>
            <el-form-item label="审批意见">
              <el-input v-model="approvalForm.comment" type="textarea" :rows="3" placeholder="请输入审批意见" />
            </el-form-item>
          </el-form>
          <div class="action-buttons">
            <el-button type="success" size="large" :icon="Check" :loading="submitting" @click="handleApprove('approved')">
              通过确认
            </el-button>
            <el-button type="primary" size="large" :icon="Edit" :loading="submitting" @click="handleApprove('revised')">
              修正后通过
            </el-button>
            <el-button type="danger" size="large" :icon="Close" :loading="submitting" @click="handleApprove('rejected')">
              驳回
            </el-button>
            <el-button size="large" @click="$router.back()">返回列表</el-button>
          </div>
        </div>

        <!-- 已处理结果 -->
        <el-result
          v-else
          :icon="alert.status === 'approved' || alert.status === 'pushed' ? 'success' : 'error'"
          :title="alert.status === 'approved' || alert.status === 'pushed' ? '预警已确认' : '预警已驳回'"
          :sub-title="`审核人: ${alert.reviewed_by || '-'}  |  审核时间: ${alert.reviewed_at || '-'}`"
        >
          <template #extra>
            <el-button type="primary" @click="$router.push('/risk-monitor/alerts')">返回预警列表</el-button>
          </template>
        </el-result>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Close, Edit, Bell, CircleCheck } from '@element-plus/icons-vue'
import { riskMonitorApi } from '@/api'
import {
  ALERT_STATUS_LABELS,
  ALERT_STATUS_TYPES,
  RISK_LEVEL_LABELS,
  RISK_STAGE_LABELS,
  PUSH_MODULE_LABELS,
} from '@/types'
import type { RiskAlertDetail } from '@/types'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const alert = ref<RiskAlertDetail | null>(null)
const currentStage = ref('risk_classify')

const approvalForm = reactive({
  comment: '',
  modifications: {} as Record<string, string>,
})

const currentStepIndex = computed(() => {
  const stages = Object.keys(RISK_STAGE_LABELS)
  return stages.indexOf(currentStage.value)
})

function stepStatus(key: string): string {
  const stages = Object.keys(RISK_STAGE_LABELS)
  const idx = stages.indexOf(key)
  const curIdx = stages.indexOf(currentStage.value)
  if (idx < curIdx) return 'success'
  if (idx > curIdx) return 'wait'
  return 'process'
}

async function fetchAlert() {
  loading.value = true
  try {
    const id = route.params.id as string
    const res = await riskMonitorApi.alerts.get(id)
    alert.value = res.data
  } catch {
    ElMessage.error('获取预警详情失败')
  } finally {
    loading.value = false
  }
}

async function handleApprove(action: string) {
  submitting.value = true
  try {
    const mods = { ...approvalForm.modifications }
    // Remove empty values
    Object.keys(mods).forEach(k => { if (!mods[k]) delete mods[k] })
    await riskMonitorApi.alerts.approve(
      alert.value!.id,
      action,
      approvalForm.comment || undefined,
      Object.keys(mods).length > 0 ? mods : undefined
    )
    ElMessage.success(action === 'approved' ? '预警已确认' : action === 'rejected' ? '预警已驳回' : '修正已保存')
    router.push('/risk-monitor/alerts')
  } catch {
    ElMessage.error('审核操作失败')
  } finally {
    submitting.value = false
  }
}

onMounted(fetchAlert)
</script>

<style scoped>
.alert-detail { max-width: 1100px; margin: 0 auto; }
.detail-card { border-radius: 10px; }
.detail-header { display: flex; justify-content: space-between; align-items: flex-start; }
.detail-header h3 { margin: 0 0 6px 0; display: flex; align-items: center; gap: 8px; color: #303133; }
.detail-desc { margin: 0; color: #909399; font-size: 13px; }
.header-badges { display: flex; gap: 8px; }

.stage-timeline { margin: 20px 0; padding: 0 20px; }

.form-section { margin-bottom: 20px; }
.form-section-title { font-size: 15px; font-weight: 600; color: #303133; margin-bottom: 12px; padding-left: 12px; border-left: 3px solid #E6A23C; }

.sql-block { background: #F5F7FA; padding: 12px; border-radius: 6px; font-size: 12px; font-family: 'Cascadia Code', 'SF Mono', monospace; white-space: pre-wrap; word-break: break-all; max-height: 150px; overflow: auto; margin: 0; }

.approval-section { background: #F0F9EB; border: 1px solid #B7EB8F; border-radius: 10px; padding: 24px; margin-top: 8px; }
.approval-section h4 { margin: 0 0 20px 0; display: flex; align-items: center; gap: 8px; color: #303133; }
.action-buttons { display: flex; gap: 12px; margin-top: 16px; }
</style>
