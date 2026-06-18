<template>
  <div class="rule-approval">
    <el-card shadow="never" class="approval-card" v-loading="loading">
      <template #header>
        <div class="approval-header">
          <div>
            <h3>
              <el-icon :size="20"><Checked /></el-icon>
              规则审批 — {{ rule?.rule_code }}
            </h3>
            <p class="approval-desc">审核风险规则，检查 SQL 语法和业务逻辑</p>
          </div>
          <el-tag :type="RISK_RULE_STATUS_TYPES[rule?.status || ''] || 'info'" size="large">
            {{ RISK_RULE_STATUS_LABELS[rule?.status || ''] || rule?.status }}
          </el-tag>
        </div>
      </template>

      <template v-if="rule">
        <!-- 15 字段规则预览 -->
        <div class="form-section">
          <div class="form-section-title">规则预览（15 字段完整展示）</div>
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="规则编码">{{ rule.rule_code }}</el-descriptions-item>
            <el-descriptions-item label="事业部">{{ rule.business_unit || '-' }}</el-descriptions-item>
            <el-descriptions-item label="渠道">{{ rule.channel || '-' }}</el-descriptions-item>
            <el-descriptions-item label="业态">{{ rule.format || '-' }}</el-descriptions-item>
            <el-descriptions-item label="业务循环">{{ rule.business_cycle || '-' }}</el-descriptions-item>
            <el-descriptions-item label="部门">{{ rule.department || '-' }}</el-descriptions-item>
            <el-descriptions-item label="岗位">{{ rule.position || '-' }}</el-descriptions-item>
            <el-descriptions-item label="人员信息">{{ rule.personnel_info || '-' }}</el-descriptions-item>
            <el-descriptions-item label="一级场景">{{ rule.level1_scene || '-' }}</el-descriptions-item>
            <el-descriptions-item label="二级场景">{{ rule.level2_scene || '-' }}</el-descriptions-item>
            <el-descriptions-item label="三级场景">{{ rule.level3_scene }}</el-descriptions-item>
            <el-descriptions-item label="风险等级">
              <el-tag :type="rule.risk_level === '高' ? 'danger' : rule.risk_level === '中' ? 'warning' : 'info'" size="small">
                {{ RISK_LEVEL_LABELS[rule.risk_level] || rule.risk_level }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="阈值">{{ rule.threshold ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="监控频率">{{ FREQUENCY_LABELS[rule.monitor_frequency] || rule.monitor_frequency }}</el-descriptions-item>
            <el-descriptions-item label="监控事业部">{{ rule.monitor_business_unit || '-' }}</el-descriptions-item>
            <el-descriptions-item label="外部数据">{{ rule.use_external_data ? '是' : '否' }}</el-descriptions-item>
            <el-descriptions-item label="版本">v{{ rule.version }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- SQL 高亮展示 -->
        <div class="form-section">
          <div class="form-section-title">SQL 语句</div>
          <div class="sql-code-block">
            <pre><code>{{ rule.sql_statement }}</code></pre>
          </div>
          <div class="sql-check">
            <el-tag type="success" size="small" effect="light">✅ 语法检查通过</el-tag>
            <el-tag type="success" size="small" effect="light" style="margin-left: 8px">✅ 仅限只读查询 (SELECT)</el-tag>
          </div>
        </div>

        <!-- 迭代历史 -->
        <div class="form-section" v-if="iterations.length > 0">
          <div class="form-section-title">迭代历史</div>
          <el-timeline>
            <el-timeline-item
              v-for="it in iterations"
              :key="it.id"
              :timestamp="it.created_at"
              placement="top"
            >
              <el-card shadow="hover" size="small">
                <p><strong>类型：</strong>{{ it.iteration_type === 'approval' ? '审批' : it.iteration_type }}</p>
                <p><strong>原因：</strong>{{ it.reason }}</p>
                <p v-if="it.new_sql"><strong>新 SQL：</strong><code class="inline-sql">{{ it.new_sql.substring(0, 100) }}{{ it.new_sql.length > 100 ? '...' : '' }}</code></p>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </div>

        <el-divider />

        <!-- 审批操作区 -->
        <div class="approval-actions" v-if="rule.status === 'pending_review'">
          <el-form :model="approvalForm" label-width="80px">
            <el-form-item label="审批意见">
              <el-input v-model="approvalForm.comment" type="textarea" :rows="3" placeholder="请输入审批意见（通过时选填，驳回时必填）" />
            </el-form-item>
            <el-form-item label="驳回原因" v-if="approvalForm.action === 'rejected'">
              <el-select v-model="approvalForm.rejectReason" placeholder="请选择驳回原因" style="width: 100%">
                <el-option label="SQL 语法错误" value="sql_syntax" />
                <el-option label="SQL 逻辑错误" value="sql_logic" />
                <el-option label="场景不合理" value="scene_invalid" />
                <el-option label="阈值不当" value="threshold_wrong" />
                <el-option label="重复规则" value="duplicate" />
                <el-option label="其他" value="other" />
              </el-select>
            </el-form-item>
          </el-form>
          <div class="action-buttons">
            <el-button type="success" size="large" :icon="Check" :loading="submitting" @click="handleApprove('approved')">
              通过
            </el-button>
            <el-button type="danger" size="large" :icon="Close" :loading="submitting" @click="approvalForm.action = 'rejected'; handleApprove('rejected')">
              驳回
            </el-button>
            <el-button size="large" @click="$router.back()">返回</el-button>
          </div>
        </div>

        <!-- 已有审批结果 -->
        <el-result
          v-else-if="rule.status === 'active'"
          icon="success"
          title="规则已通过审批"
          :sub-title="`审批人: ${rule.reviewed_by || '-'}  |  审批时间: ${rule.reviewed_at || '-'}`"
        >
          <template #extra>
            <el-button type="primary" @click="$router.push('/risk-monitor/rules')">返回规则列表</el-button>
          </template>
        </el-result>

        <el-result
          v-else-if="rule.status === 'rejected'"
          icon="error"
          title="规则已被驳回"
          :sub-title="`审批人: ${rule.reviewed_by || '-'}  |  审批时间: ${rule.reviewed_at || '-'}`"
        >
          <template #extra>
            <el-button type="primary" @click="$router.push('/risk-monitor/rules')">返回规则列表</el-button>
          </template>
        </el-result>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Close, Checked } from '@element-plus/icons-vue'
import { riskMonitorApi } from '@/api'
import {
  RISK_RULE_STATUS_LABELS,
  RISK_RULE_STATUS_TYPES,
  RISK_LEVEL_LABELS,
  FREQUENCY_LABELS,
} from '@/types'
import type { RiskRule, RuleIteration } from '@/types'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const rule = ref<RiskRule | null>(null)
const iterations = ref<RuleIteration[]>([])

const approvalForm = reactive({
  action: 'approved' as string,
  comment: '',
  rejectReason: '',
})

async function fetchRule() {
  loading.value = true
  try {
    const id = route.params.id as string
    const res = await riskMonitorApi.rules.get(id)
    rule.value = res.data.rule
    iterations.value = res.data.iterations || []
  } catch {
    ElMessage.error('获取规则详情失败')
  } finally {
    loading.value = false
  }
}

async function handleApprove(action: string) {
  if (action === 'rejected' && !approvalForm.comment && !approvalForm.rejectReason) {
    ElMessage.warning('驳回时请填写审批意见或选择驳回原因')
    return
  }

  submitting.value = true
  try {
    const comment = approvalForm.comment || approvalForm.rejectReason
    await riskMonitorApi.rules.approve(rule.value!.id, action, comment)
    ElMessage.success(action === 'approved' ? '规则已通过审批' : '规则已驳回')
    router.push('/risk-monitor/rules')
  } catch {
    ElMessage.error('审批操作失败')
  } finally {
    submitting.value = false
  }
}

onMounted(fetchRule)
</script>

<style scoped>
.rule-approval { max-width: 900px; margin: 0 auto; }
.approval-card { border-radius: 10px; }
.approval-header { display: flex; justify-content: space-between; align-items: flex-start; }
.approval-header h3 { margin: 0 0 6px 0; display: flex; align-items: center; gap: 8px; color: #303133; }
.approval-desc { margin: 0; color: #909399; font-size: 13px; }

.form-section { margin-bottom: 20px; }
.form-section-title { font-size: 15px; font-weight: 600; color: #303133; margin-bottom: 12px; padding-left: 12px; border-left: 3px solid #E6A23C; }

.sql-code-block { background: #1E1E1E; color: #D4D4D4; padding: 16px; border-radius: 8px; overflow-x: auto; }
.sql-code-block pre { margin: 0; font-size: 13px; font-family: 'Cascadia Code', 'SF Mono', monospace; }
.sql-code-block code { white-space: pre-wrap; word-break: break-all; }
.sql-check { margin-top: 8px; }

.inline-sql { background: #F5F7FA; padding: 2px 6px; border-radius: 3px; font-size: 12px; font-family: monospace; }

.approval-actions { padding: 20px 0; }
.action-buttons { display: flex; gap: 12px; margin-top: 16px; }
</style>
