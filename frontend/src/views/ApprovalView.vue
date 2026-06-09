<template>
  <div class="approval-view" v-loading="loading">
    <el-card style="margin-bottom: 16px">
      <template #header>
        <span>碳基守门 — {{ stageLabel(pending?.stage) }}</span>
      </template>

      <el-alert v-if="!pending" title="当前没有待审批的阶段" type="info" show-icon :closable="false" />

      <!-- AI 输出展示 -->
      <div v-if="pending" class="approval-content">
        <el-alert
          v-if="pending.ai_output?.status === 'skeleton'"
          :title="`AI Agent 不可用（${(pending.ai_output as any)?.error || '未知错误'}）`"
          type="warning" show-icon :closable="false" style="margin-bottom: 16px"
        />

        <div class="ai-output-section">
          <h4>AI 分析结果</h4>
          <el-card shadow="never">
            <template v-for="(value, key) in displayFields" :key="key">
              <div class="output-field" v-if="value !== undefined && value !== null">
                <strong>{{ fieldLabel(key) }}：</strong>
                <template v-if="typeof value === 'boolean'">
                  <el-tag :type="value ? 'success' : 'danger'">{{ value ? '是' : '否' }}</el-tag>
                </template>
                <template v-else-if="Array.isArray(value)">
                  <div v-for="(item, i) in value" :key="i" style="margin-left: 16px">• {{ item }}</div>
                </template>
                <template v-else>
                  <span>{{ value }}</span>
                </template>
              </div>
            </template>
          </el-card>
        </div>

        <!-- 守门操作 -->
        <div class="approval-actions" style="margin-top: 24px">
          <h4>守门决策</h4>
          <el-radio-group v-model="action" style="margin-bottom: 16px">
            <el-radio-button value="approved">✓ 确认通过</el-radio-button>
            <el-radio-button value="rejected">✗ 驳回重做</el-radio-button>
            <el-radio-button value="modified">✎ 修改后通过</el-radio-button>
          </el-radio-group>
          <br />
          <el-input v-model="comment" type="textarea" :rows="3" :placeholder="action === 'approved' ? '可选：补充审核意见' : '请说明原因'" />
          <br />
          <div style="margin-top: 16px">
            <el-button type="primary" :loading="submitting" @click="submitApproval" :disabled="!action">
              提交守门决定
            </el-button>
            <el-button @click="$router.back()">返回</el-button>
          </div>
        </div>

        <!-- 划词调整 -->
        <div class="regenerate-section" style="margin-top: 24px" v-if="false /* 暂不启用 */">
          <el-divider />
          <h4>划词调整（重新生成指定内容）</h4>
          <el-input v-model="selectedText" type="textarea" :rows="2" placeholder="选中 AI 输出中的文本粘贴到此" />
          <el-input v-model="instruction" type="textarea" :rows="2" placeholder="输入修改指令" style="margin-top: 8px" />
          <el-button size="small" style="margin-top: 8px" @click="regenerate">重新生成</el-button>
        </div>
      </div>
    </el-card>

    <!-- 守门历史 -->
    <el-card v-if="approvalHistory.length > 0">
      <template #header><span>守门历史</span></template>
      <el-timeline>
        <el-timeline-item v-for="item in approvalHistory" :key="item.id"
          :timestamp="item.created_at"
          :type="item.action === 'approved' ? 'success' : item.action === 'rejected' ? 'danger' : 'warning'">
          {{ item.reviewer_id }} — {{ item.action === 'approved' ? '通过' : item.action === 'rejected' ? '驳回' : '修改' }}
          <template v-if="item.comment"><br />备注：{{ item.comment }}</template>
        </el-timeline-item>
      </el-timeline>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { approvalApi } from '@/api'
import { STAGE_LABELS } from '@/types'
import type { PendingApproval } from '@/types'

const route = useRoute()
const router = useRouter()
const caseId = route.params.id as string

const pending = ref<PendingApproval | null>(null)
const approvalHistory = ref<Array<{ id: string; stage_name: string; reviewer_id: string; action: string; comment?: string; created_at: string }>>([])
const loading = ref(false)
const submitting = ref(false)
const action = ref<string>('')
const comment = ref('')
const selectedText = ref('')
const instruction = ref('')

const displayFields = computed(() => {
  const output = pending.value?.ai_output || {}
  // 过滤掉内部元数据字段
  const skip = ['status', 'sections', 'error', 'generated_at', 'a2a_targets']
  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(output)) {
    if (!skip.includes(key) && value !== undefined && value !== null) {
      result[key] = value
    }
  }
  return result
})

function stageLabel(v?: string) { return v ? STAGE_LABELS[v] || v : '—' }

function fieldLabel(key: string): string {
  const labels: Record<string, string> = {
    summary: '摘要', case_summary: '案件摘要', key_facts: '关键事实',
    should_investigate: '是否立案', should_transfer: '是否转交', is_hr_related: '是否HR管辖',
    investigation_reason: '立案理由', transfer_target: '转交目标', risk_level: '风险等级',
    confidence: '置信度', confidence_reason: '置信度理由',
    involved_entity_type: '调查对象类型', urgency: '紧急程度',
    has_penalty: '是否追责', estimated_amount_range: '预估金额范围',
    uncertainty_factors: '不确定因素', missing_information: '缺失信息',
    suggested_next_steps: '建议后续步骤', suggested_interview_targets: '建议访谈人员',
    legal_references: '法律依据', plan_rationale: '方案理由',
    investigation_plan: '调查方案',
  }
  return labels[key] || key
}

async function fetchApproval() {
  loading.value = true
  try {
    const [pendingRes, historyRes] = await Promise.allSettled([
      approvalApi.pending(caseId),
      approvalApi.history(caseId),
    ])
    if (pendingRes.status === 'fulfilled') pending.value = pendingRes.value.data
    if (historyRes.status === 'fulfilled') approvalHistory.value = historyRes.value.data
  } finally {
    loading.value = false
  }
}

async function submitApproval() {
  if (!action.value || !pending.value) return
  submitting.value = true
  try {
    await approvalApi.submit(caseId, pending.value.stage, action.value, comment.value)
    ElMessage.success('守门决定已提交')
    router.push(`/cases/${caseId}`)
  } catch {
    ElMessage.error('提交失败')
  } finally {
    submitting.value = false
  }
}

async function regenerate() {
  if (!pending.value || !selectedText.value || !instruction.value) return
  try {
    const res = await approvalApi.regenerate(caseId, pending.value.stage, selectedText.value, instruction.value)
    ElMessage.success('内容已重新生成')
    // 显示重新生成的结果（简化处理）
    ElMessage.info(res.data.regenerated_text)
  } catch { ElMessage.error('重新生成失败') }
}

onMounted(fetchApproval)
</script>

<style scoped>
.ai-output-section { margin-bottom: 16px; }
.output-field { margin-bottom: 12px; line-height: 1.6; }
.output-field strong { color: #303133; }
</style>
