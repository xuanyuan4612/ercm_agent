<template>
  <div class="knowledge-view">
    <el-card>
      <template #header><span>知识库检索</span></template>
      <!-- 搜索栏 -->
      <div style="margin-bottom: 16px">
        <el-input v-model="query" placeholder="输入搜索关键词..." style="width: 400px; margin-right: 12px" @keyup.enter="search" clearable>
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="kbTypes" multiple placeholder="限定知识库类型" style="width: 300px; margin-right: 12px" clearable>
          <el-option label="初筛入口" value="intake" />
          <el-option label="调查方案" value="investigation" />
          <el-option label="分析报告" value="analysis" />
          <el-option label="处置分流" value="disposition" />
          <el-option label="处罚执行" value="enforcement" />
          <el-option label="公共" value="common" />
        </el-select>
        <el-button type="primary" @click="search" :loading="loading">搜索</el-button>
      </div>

      <!-- 搜索结果 -->
      <el-table :data="results" v-loading="loading" stripe empty-text="请输入搜索关键词查询">
        <el-table-column prop="kb_type" label="知识库类型" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ kbTypeLabel(row.kb_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" width="200" />
        <el-table-column prop="content_snippet" label="内容摘要" />
        <el-table-column label="相关度" width="100">
          <template #default="{ row }">
            <el-progress :percentage="Math.round(row.relevance * 100)" :status="row.relevance >= 0.7 ? 'success' : row.relevance >= 0.4 ? '' : 'exception'" />
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && searched && results.length === 0" description="未找到相关知识库内容" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { knowledgeApi } from '@/api'

const query = ref('')
const kbTypes = ref<string[]>([])
const results = ref<Array<{ doc_id: string; kb_type: string; title: string; content_snippet: string; relevance: number }>>([])
const loading = ref(false)
const searched = ref(false)

function kbTypeLabel(v: string): string {
  const m: Record<string, string> = {
    intake: '初筛', investigation: '调查方案', analysis: '分析报告',
    disposition: '处置分流', enforcement: '处罚执行', common: '公共',
    risk_monitor: '风险监控', ic_evaluation: '内控评价',
    special_audit: '专项审计', exit_audit: '离任审计',
    trade_secret: '商业秘密', improvement: '持续改善', behavior_risk: '行为风险',
  }
  return m[v] || v
}

async function search() {
  if (!query.value.trim()) return
  loading.value = true
  searched.value = true
  try {
    const res = await knowledgeApi.search(query.value, kbTypes.value.join(',') || undefined, 10)
    results.value = res.data
  } catch {
    results.value = []
  } finally {
    loading.value = false
  }
}
</script>
