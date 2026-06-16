<template>
  <div class="approval-view" v-loading="loading">
    <!-- 头部 -->
    <div class="approval-toolbar" v-if="pending">
      <div class="toolbar-left">
        <el-button text @click="$router.back()">
          <el-icon><ArrowLeft /></el-icon> 返回
        </el-button>
        <el-divider direction="vertical" />
        <span class="toolbar-title">碳基守门 — {{ stageLabel(pending.stage) }}</span>
      </div>
    </div>

    <el-alert
      v-if="!pending && !loading"
      title="当前没有待审批的阶段"
      type="info"
      show-icon
      :closable="false"
      class="approval-empty-alert"
    />

    <!-- AI 输出展示 -->
    <div v-if="pending" class="approval-content">
      <!-- 降级警告 -->
      <el-alert
        v-if="pending.ai_output?.status === 'skeleton'"
        :title="`AI Agent 不可用（${(pending.ai_output as any)?.error || '未知错误'}），以下为骨架输出`"
        type="warning"
        show-icon
        :closable="false"
        class="alert-block"
      />

      <!-- AI 分析结果 -->
      <el-card class="output-card" shadow="never">
        <template #header>
          <div class="card-header-title">
            <el-icon :size="16"><Cpu /></el-icon> AI 分析结果
          </div>
        </template>
        <div class="output-fields">
          <div v-for="(value, key) in displayFields" :key="key" class="output-field">
            <div class="field-label">{{ fieldLabel(key as string) }}</div>
            <div class="field-value">
              <template v-if="value === undefined || value === null || value === ''">
                <span class="text-muted">—</span>
              </template>
              <template v-else-if="typeof value === 'boolean'">
                <el-tag :type="value ? 'success' : 'danger'" effect="light">
                  {{ value ? '是 ✓' : '否 ✗' }}
                </el-tag>
              </template>
              <template v-else-if="typeof value === 'object'">
                <pre class="field-json">{{ JSON.stringify(value, null, 2) }}</pre>
              </template>
              <template v-else>
                <span>{{ String(value) }}</span>
              </template>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 知识库引用 -->
      <el-card v-if="pending.knowledge_refs?.length" class="ref-card" shadow="never">
        <template #header>
          <div class="card-header-title">
            <el-icon :size="16"><Collection /></el-icon> 知识库引用
          </div>
        </template>
        <div class="ref-list">
          <div v-for="ref in pending.knowledge_refs" :key="ref.doc_id" class="ref-item">
            <div class="ref-title">
              <el-icon :size="14"><Document /></el-icon>
              {{ ref.title }}
              <el-tag size="small" type="info" effect="light">{{ ref.kb_type }}</el-tag>
            </div>
            <div class="ref-snippet">{{ ref.content_snippet }}</div>
            <el-progress
              :percentage="Math.round(ref.relevance * 100)"
              :status="ref.relevance >= 0.7 ? 'success' : ref.relevance >= 0.4 ? '' : 'exception'"
              :show-text="true"
              :stroke-width="4"
              style="max-width: 200px"
            />
          </div>
        </div>
      </el-card>

      <!-- 守门操作 -->
      <el-card class="action-card" shadow="never">
        <template #header>
          <div class="card-header-title">
            <el-icon :size="16"><Finished /></el-icon> 守门决策
          </div>
        </template>
        <el-radio-group v-model="action" class="action-radio-group">
          <el-radio-button value="approved">
            <el-icon :size="14"><Check /></el-icon>
            确认通过
          </el-radio-button>
          <el-radio-button value="rejected">
            <el-icon :size="14"><Close /></el-icon>
            驳回重做
          </el-radio-button>
          <el-radio-button value="modified">
            <el-icon :size="14"><Edit /></el-icon>
            修改后通过
          </el-radio-button>
        </el-radio-group>
        <el-input
          v-model="comment"
          type="textarea"
          :rows="3"
          :placeholder="action === 'approved' ? '可选：补充审核意见' : '请说明原因'"
          class="comment-input"
        />
        <div class="action-buttons">
          <el-button type="primary" :loading="submitting" :disabled="!action" size="large" @click="submitApproval">
            <el-icon :size="16"><Finished /></el-icon>
            提交守门决定
          </el-button>
          <el-button size="large" @click="$router.back()">返回</el-button>
        </div>
      </el-card>
    </div>

    <!-- 守门历史 -->
    <el-card v-if="approvalHistory.length > 0" class="history-card" shadow="never">
      <template #header>
        <div class="card-header-title">
          <el-icon :size="16"><Timer /></el-icon> 守门历史
        </div>
      </template>
      <el-timeline>
        <el-timeline-item
          v-for="item in approvalHistory"
          :key="item.id"
          :timestamp="item.created_at"
          :type="item.action === 'approved' ? 'success' : item.action === 'rejected' ? 'danger' : 'warning'"
          placement="top"
        >
          <div class="history-item">
            <span class="history-reviewer">{{ item.reviewer_id }}</span>
            <el-tag
              size="small"
              :type="item.action === 'approved' ? 'success' : item.action === 'rejected' ? 'danger' : 'warning'"
              effect="light"
            >
              {{ item.action === 'approved' ? '通过' : item.action === 'rejected' ? '驳回' : '修改' }}
            </el-tag>
            <div v-if="item.comment" class="history-comment">{{ item.comment }}</div>
          </div>
        </el-timeline-item>
      </el-timeline>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft, Check, Close, Collection, Cpu, Edit, Finished, Timer,
} from '@element-plus/icons-vue'
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
    summary: '摘要',
    case_summary: '案件摘要',
    key_facts: '关键事实',
    should_investigate: '是否立案',
    should_transfer: '是否转交',
    is_hr_related: '是否 HR 管辖',
    investigation_reason: '立案理由',
    transfer_target: '转交目标',
    transfer_reason: '转交理由',
    risk_level: '风险等级',
    confidence: '置信度',
    confidence_reason: '置信度理由',
    involved_entity_type: '调查对象类型',
    urgency: '紧急程度',
    has_penalty: '是否追责',
    estimated_amount_range: '预估金额范围',
    uncertainty_factors: '不确定因素',
    missing_information: '缺失信息',
    suggested_next_steps: '建议后续步骤',
    suggested_interview_targets: '建议访谈人员',
    legal_references: '法律依据',
    plan_rationale: '方案理由',
    investigation_plan: '调查方案',
    disposition_type: '处置类型',
    disposition_reason: '处置理由',
    penalty_opinions: '追责意见',
    involved_personnel: '涉及人员',
    case_conclusion: '案件结论',
    evidence_sufficiency: '证据充分性',
    material_checklist: '报案材料清单',
    prosecution_letter: '报案书',
    follow_up_suggestions: '后续建议',
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

onMounted(fetchApproval)
</script>

<style scoped>
.approval-view { max-width: 1000px; margin: 0 auto; }

/* ── 工具栏 ── */
.approval-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 20px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #EBEEF5;
}
.toolbar-left { display: flex; align-items: center; gap: 8px; }
.toolbar-title { font-size: 15px; font-weight: 600; color: #303133; }
.approval-empty-alert { border-radius: 8px; }

/* ── 卡片 ── */
.output-card, .ref-card, .action-card, .history-card {
  margin-bottom: 16px;
  border-radius: 8px;
}
.card-header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #303133;
}
.alert-block { margin-bottom: 16px; border-radius: 8px; }

/* ── AI 输出字段 ── */
.output-fields { display: flex; flex-direction: column; gap: 0; }
.output-field {
  padding: 14px 0;
  border-bottom: 1px solid #F2F3F5;
}
.output-field:last-child { border-bottom: none; }
.field-label {
  font-size: 13px;
  font-weight: 600;
  color: #909399;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.field-value { color: #303133; line-height: 1.6; }
.field-json {
  background: #F5F7FA;
  padding: 12px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
  overflow-x: auto;
  max-height: 300px;
}

/* ── 知识库引用 ── */
.ref-list { display: flex; flex-direction: column; gap: 16px; }
.ref-item {
  padding: 12px;
  background: #F5F7FA;
  border-radius: 8px;
}
.ref-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  margin-bottom: 6px;
}
.ref-snippet {
  color: #606266;
  font-size: 13px;
  margin-bottom: 8px;
  line-height: 1.5;
}

/* ── 守门操作 ── */
.action-radio-group { margin-bottom: 16px; display: flex; gap: 12px; }
.comment-input { margin-bottom: 16px; }
.action-buttons { display: flex; gap: 12px; }

/* ── 守门历史 ── */
.history-item { line-height: 1.6; }
.history-reviewer { font-weight: 500; margin-right: 8px; }
.history-comment { color: #606266; font-size: 13px; margin-top: 4px; }

.text-muted { color: #909399; }
</style>
