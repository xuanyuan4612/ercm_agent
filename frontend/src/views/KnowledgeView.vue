<template>
  <div class="knowledge-view">
    <!-- 搜索区域 -->
    <el-card class="search-card" shadow="never">
      <template #header>
        <div class="card-header-title">
          <el-icon :size="16"><Search /></el-icon> 知识库检索
        </div>
      </template>
      <div class="search-row">
        <el-input
          v-model="query"
          placeholder="输入搜索关键词..."
          size="large"
          clearable
          @keyup.enter="search"
          class="search-input"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select
          v-model="kbTypes"
          multiple
          placeholder="限定知识库类型（可选）"
          size="large"
          clearable
          collapse-tags
          collapse-tags-tooltip
          class="kb-select"
        >
          <el-option-group label="廉洁监察">
            <el-option v-for="kb in kbGroups.integrity" :key="kb.value" :label="kb.label" :value="kb.value" />
          </el-option-group>
          <el-option-group label="风险监控">
            <el-option v-for="kb in kbGroups.risk" :key="kb.value" :label="kb.label" :value="kb.value" />
          </el-option-group>
          <el-option-group label="内控评价">
            <el-option v-for="kb in kbGroups.control" :key="kb.value" :label="kb.label" :value="kb.value" />
          </el-option-group>
          <el-option-group label="专项审计">
            <el-option v-for="kb in kbGroups.special" :key="kb.value" :label="kb.label" :value="kb.value" />
          </el-option-group>
          <el-option-group label="离任审计">
            <el-option v-for="kb in kbGroups.exit" :key="kb.value" :label="kb.label" :value="kb.value" />
          </el-option-group>
          <el-option-group label="商业秘密保护">
            <el-option v-for="kb in kbGroups.secret" :key="kb.value" :label="kb.label" :value="kb.value" />
          </el-option-group>
          <el-option-group label="行为风险">
            <el-option v-for="kb in kbGroups.behavior" :key="kb.value" :label="kb.label" :value="kb.value" />
          </el-option-group>
          <el-option-group label="持续改善">
            <el-option v-for="kb in kbGroups.improvement" :key="kb.value" :label="kb.label" :value="kb.value" />
          </el-option-group>
          <el-option-group label="共享">
            <el-option v-for="kb in kbGroups.shared" :key="kb.value" :label="kb.label" :value="kb.value" />
          </el-option-group>
        </el-select>
        <el-button type="primary" size="large" :loading="loading" :icon="Search" @click="search">
          搜索
        </el-button>
      </div>

      <!-- 活跃的 KB 类型标签 -->
      <div v-if="kbTypes.length > 0" class="active-filters">
        <span class="filter-label">当前限定：</span>
        <el-tag
          v-for="kb in kbTypes"
          :key="kb"
          size="small"
          closable
          @close="removeKbType(kb)"
        >
          {{ KB_TYPE_LABELS[kb] || kb }}
        </el-tag>
      </div>
    </el-card>

    <!-- 搜索结果 -->
    <el-card class="results-card" shadow="never">
      <template #header>
        <div class="card-header-title">
          <el-icon :size="16"><Collection /></el-icon>
          搜索结果
          <span v-if="searched" class="result-count">（{{ results.length }} 条）</span>
        </div>
      </template>

      <el-table :data="results" v-loading="loading" stripe empty-text="请输入搜索关键词查询" highlight-current-row>
        <el-table-column label="类型" width="140">
          <template #default="{ row }">
            <el-tag size="small" effect="light" :color="kbTypeColor(row.kb_type)">
              {{ KB_TYPE_LABELS[row.kb_type] || row.kb_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200">
          <template #default="{ row }">
            <div class="title-cell">
              <el-icon :size="14"><Document /></el-icon>
              {{ row.title }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="content_snippet" label="内容摘要" min-width="300">
          <template #default="{ row }">
            <div class="snippet-cell">{{ row.content_snippet }}</div>
          </template>
        </el-table-column>
        <el-table-column label="相关度" width="150">
          <template #default="{ row }">
            <div class="relevance-cell">
              <el-progress
                :percentage="Math.round(row.relevance * 100)"
                :status="row.relevance >= 0.7 ? 'success' : row.relevance >= 0.4 ? '' : 'exception'"
                :stroke-width="6"
                :show-text="true"
                style="flex: 1"
              />
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!loading && searched && results.length === 0"
        description="未找到相关知识库内容，请尝试其他关键词"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { knowledgeApi } from '@/api'
import { KB_TYPE_LABELS } from '@/types'

const query = ref('')
const kbTypes = ref<string[]>([])
const results = ref<Array<{ doc_id: string; kb_type: string; title: string; content_snippet: string; relevance: number }>>([])
const loading = ref(false)
const searched = ref(false)

// 知识库分组
const kbGroups = {
  integrity: [
    { value: 'intake', label: '初筛入口' },
    { value: 'investigation', label: '调查方案' },
    { value: 'analysis', label: '分析报告' },
    { value: 'disposition', label: '处置分流' },
    { value: 'enforcement', label: '处罚执行' },
    { value: 'kb_integrity_policy', label: '廉洁制度' },
    { value: 'kb_integrity_cases', label: '廉洁案例' },
  ],
  risk: [
    { value: 'risk_rules', label: '风险规则' },
    { value: 'risk_cases', label: '风险案例' },
    { value: 'database_schema', label: '数据库 Schema' },
    { value: 'disposition_feedback', label: '处置反馈' },
  ],
  control: [
    { value: 'ic_policy', label: '内控制度' },
    { value: 'control_matrix', label: '控制矩阵' },
    { value: 'audit_plan', label: '审计计划' },
    { value: 'interview_template', label: '访谈模板' },
    { value: 'deficiency_rating', label: '缺陷评级' },
  ],
  special: [
    { value: 'sa_plan', label: '专项审计计划' },
    { value: 'sa_history', label: '专项审计历史' },
    { value: 'audit_workpaper_template', label: '审计底稿模板' },
    { value: 'improvement_suggestion', label: '改善建议' },
  ],
  exit: [
    { value: 'ea_plan', label: '离任审计计划' },
    { value: 'position_duty', label: '岗位职责' },
    { value: 'personal_risk_case', label: '个人风险案例' },
    { value: 'business_audit_case', label: '业务审计案例' },
    { value: 'behavioral_risk_history', label: '行为风险历史' },
  ],
  secret: [
    { value: 'trade_secret_policy', label: '商业秘密制度' },
    { value: 'ip_policy', label: '知识产权制度' },
    { value: 'trade_secret_law', label: '商业秘密法律' },
    { value: 'trade_secret_cases', label: '商业秘密案例' },
    { value: 'historical_secret_review', label: '历史定密评审' },
  ],
  behavior: [
    { value: 'behavior_policy', label: '行为规范制度' },
    { value: 'employee_lifecycle', label: '员工生命周期' },
    { value: 'historical_behavior_analysis', label: '历史行为分析' },
  ],
  improvement: [
    { value: 'improvement_case', label: '改善案例' },
    { value: 'rectification_template', label: '整改模板' },
    { value: 'audit_issue_history', label: '审计问题历史' },
    { value: 'policy_and_process', label: '制度与流程' },
  ],
  shared: [
    { value: 'common', label: '公共知识' },
    { value: 'law_and_regulation', label: '法律法规' },
  ],
}

function removeKbType(kb: string) {
  kbTypes.value = kbTypes.value.filter((t) => t !== kb)
}

function kbTypeColor(kb: string): string {
  const colors: Record<string, string> = {
    intake: '#409EFF20', investigation: '#67C23A20', analysis: '#E6A23C20',
    disposition: '#F56C6C20', enforcement: '#2C3E5020', common: '#90939920',
  }
  return colors[kb] || ''
}

async function search() {
  if (!query.value.trim()) return
  loading.value = true
  searched.value = true
  try {
    const res = await knowledgeApi.search(query.value, kbTypes.value.join(',') || undefined, 10)
    results.value = res.data as Array<{ doc_id: string; kb_type: string; title: string; content_snippet: string; relevance: number }>
  } catch {
    results.value = []
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.knowledge-view { max-width: 1200px; margin: 0 auto; }

/* ── 卡片 ── */
.search-card, .results-card {
  border-radius: 8px;
  margin-bottom: 16px;
}
.card-header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #303133;
}
.result-count { font-weight: 400; color: #909399; font-size: 13px; }

/* ── 搜索行 ── */
.search-row {
  display: flex;
  gap: 12px;
  align-items: center;
}
.search-input { flex: 1; max-width: 480px; }
.kb-select { flex: 1; max-width: 520px; }

/* ── 活跃筛选 ── */
.active-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.filter-label { font-size: 13px; color: #909399; }

/* ── 表格 ── */
.title-cell { display: flex; align-items: center; gap: 6px; }
.snippet-cell {
  color: #606266;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.relevance-cell { display: flex; align-items: center; }
</style>
