<template>
  <div class="agents-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="page-title">
        <h2>
          <el-icon :size="24"><Cpu /></el-icon>
          AI Agent 管理
        </h2>
        <p class="page-desc">赫尔墨斯风控系统共部署 8 个模块化 AI Agent，覆盖风控全业务场景</p>
      </div>
      <div class="page-stats">
        <div class="stat-item">
          <span class="stat-num">{{ profiles.length }}</span>
          <span class="stat-label">活跃模块</span>
        </div>
        <div class="stat-item">
          <span class="stat-num">{{ totalKnowledgeScopes }}</span>
          <span class="stat-label">知识库分区</span>
        </div>
        <div class="stat-item">
          <span class="stat-num">{{ totalTools }}</span>
          <span class="stat-label">工具权限</span>
        </div>
      </div>
    </div>

    <!-- 搜索和筛选 -->
    <div class="filter-bar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索模块名称、描述、工具或知识库..."
        clearable
        :prefix-icon="Search"
        class="search-input"
        @input="updateFilteredProfiles"
      />
      <el-select v-model="filterPolicy" placeholder="模型路由策略" clearable class="filter-select" @change="updateFilteredProfiles">
        <el-option label="全部策略" value="" />
        <el-option :label="ROUTING_POLICY_LABELS['primary_only']" value="primary_only" />
        <el-option :label="ROUTING_POLICY_LABELS['primary_with_fallback']" value="primary_with_fallback" />
        <el-option :label="ROUTING_POLICY_LABELS['sensitive_data']" value="sensitive_data" />
      </el-select>
    </div>

    <!-- 模块卡片网格 -->
    <div class="modules-grid" v-loading="loading">
      <el-card
        v-for="profile in filteredProfiles"
        :key="profile.profile_id"
        class="module-card"
        :class="{ 'module-card--expanded': expandedModule === profile.module }"
        shadow="hover"
        @click="toggleExpand(profile.module)"
      >
        <!-- 卡片抬头 -->
        <template #header>
          <div class="card-header">
            <div class="card-title-row">
              <span
                class="card-icon"
                :style="{ background: MODULE_COLORS[profile.module] || '#409EFF' }"
              >
                <el-icon :size="18">
                  <component :is="MODULE_ICONS[profile.module] || 'Setting'" />
                </el-icon>
              </span>
              <div>
                <div class="card-module-name">{{ MODULE_LABELS[profile.module] || profile.module }}</div>
                <div class="card-module-key">{{ profile.module }}</div>
              </div>
            </div>
            <div class="card-badges">
              <el-tag
                :color="(MODULE_COLORS[profile.module] || '#409EFF') + '20'"
                :style="{ color: MODULE_COLORS[profile.module] || '#409EFF', borderColor: (MODULE_COLORS[profile.module] || '#409EFF') + '40' }"
                size="small"
                effect="plain"
              >
                {{ ROUTING_POLICY_LABELS[profile.model_routing_policy] || profile.model_routing_policy }}
              </el-tag>
            </div>
          </div>
        </template>

        <!-- 卡片摘要 -->
        <div class="card-summary">
          <p>{{ profile.description }}</p>
        </div>

        <!-- 知识库范围 -->
        <div class="card-section">
          <div class="section-label">
            <el-icon :size="14"><Collection /></el-icon>
            知识库范围（{{ profile.knowledge_scopes.length }}）
          </div>
          <div class="tag-group">
            <el-tag
              v-for="kb in profile.knowledge_scopes"
              :key="kb"
              size="small"
              type="info"
              effect="light"
            >
              {{ KB_TYPE_LABELS[kb] || kb }}
            </el-tag>
          </div>
        </div>

        <!-- 工具权限 -->
        <div class="card-section">
          <div class="section-label">
            <el-icon :size="14"><Switch /></el-icon>
            可用工具（{{ profile.allowed_tools.length }}）
          </div>
          <div class="tag-group">
            <el-tag
              v-for="tool in profile.allowed_tools"
              :key="tool"
              size="small"
              type="success"
              effect="light"
            >
              {{ TOOL_LABELS[tool] || tool }}
            </el-tag>
          </div>
        </div>

        <!-- 展开详情：模型路由 + 质量门禁 -->
        <el-collapse-transition>
          <div v-show="expandedModule === profile.module" class="card-detail">
            <el-divider style="margin: 12px 0" />

            <!-- 模型路由 -->
            <div class="card-section">
              <div class="section-label">
                <el-icon :size="14"><Connection /></el-icon>
                模型路由配置
              </div>
              <el-descriptions :column="1" size="small" border class="detail-table">
                <el-descriptions-item label="路由策略">
                  <el-tag size="small" :type="routingPolicyTag(profile.model_routing_policy)">
                    {{ ROUTING_POLICY_LABELS[profile.model_routing_policy] || profile.model_routing_policy }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="主模型">{{ profile.primary_provider }}</el-descriptions-item>
                <el-descriptions-item label="备用模型">{{ profile.fallback_provider }}</el-descriptions-item>
                <el-descriptions-item label="敏感数据模型">{{ profile.sensitive_fallback }}</el-descriptions-item>
              </el-descriptions>
            </div>

            <!-- 质量门禁 -->
            <div class="card-section">
              <div class="section-label">
                <el-icon :size="14"><CircleCheck /></el-icon>
                质量门禁
              </div>
              <div class="quality-gates">
                <div
                  v-for="(enabled, key) in profile.quality_gates"
                  :key="key"
                  class="gate-item"
                  :class="{ 'gate-item--active': enabled }"
                >
                  <el-icon :size="14" :color="enabled ? '#67C23A' : '#C0C4CC'">
                    <component :is="enabled ? 'CircleCheckFilled' : 'CircleClose'" />
                  </el-icon>
                  <span :style="{ color: enabled ? '#303133' : '#C0C4CC' }">
                    {{ QUALITY_GATE_LABELS[key] || key }}
                  </span>
                </div>
              </div>
            </div>

            <!-- 元数据 -->
            <el-divider style="margin: 12px 0" />
            <div class="card-meta">
              <span><strong>Profile ID:</strong> {{ profile.profile_id }}</span>
              <span><strong>Graph:</strong> {{ profile.module_graph }}</span>
              <span><strong>Schema:</strong> v{{ profile.schema_version }}</span>
            </div>
          </div>
        </el-collapse-transition>
      </el-card>
    </div>

    <!-- 空状态 -->
    <el-empty v-if="!loading && filteredProfiles.length === 0" description="未找到匹配的 Agent 模块">
      <el-button type="primary" @click="resetFilters">重置筛选</el-button>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Search, Cpu, Setting, Connection, CircleCheck, CircleCheckFilled, CircleClose } from '@element-plus/icons-vue'
import { agentsApi } from '@/api'
import {
  MODULE_LABELS,
  MODULE_COLORS,
  MODULE_ICONS,
  KB_TYPE_LABELS,
  TOOL_LABELS,
  QUALITY_GATE_LABELS,
  ROUTING_POLICY_LABELS,
} from '@/types'
import type { ModuleAgentProfile } from '@/types'

const profiles = ref<ModuleAgentProfile[]>([])
const filteredProfiles = ref<ModuleAgentProfile[]>([])
const loading = ref(false)
const expandedModule = ref<string | null>(null)
const searchQuery = ref('')
const filterPolicy = ref('')

// 统计信息
const totalKnowledgeScopes = computed(() => {
  const all = new Set(profiles.value.flatMap((p) => p.knowledge_scopes))
  return all.size
})

const totalTools = computed(() => {
  const all = new Set(profiles.value.flatMap((p) => p.allowed_tools))
  return all.size
})

function toggleExpand(module: string) {
  expandedModule.value = expandedModule.value === module ? null : module
}

function routingPolicyTag(policy: string) {
  const map: Record<string, string> = {
    primary_only: 'info',
    primary_with_fallback: 'success',
    sensitive_data: 'danger',
  }
  return map[policy] || 'info'
}

function updateFilteredProfiles() {
  let result = profiles.value

  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter((p) => {
      const searchText = [
        MODULE_LABELS[p.module] || '',
        p.module,
        p.description,
        ...p.knowledge_scopes.map((k) => KB_TYPE_LABELS[k] || k),
        ...p.allowed_tools.map((t) => TOOL_LABELS[t] || t),
      ].join(' ').toLowerCase()
      return searchText.includes(q)
    })
  }

  if (filterPolicy.value) {
    result = result.filter((p) => p.model_routing_policy === filterPolicy.value)
  }

  filteredProfiles.value = result
}

function resetFilters() {
  searchQuery.value = ''
  filterPolicy.value = ''
  updateFilteredProfiles()
}

async function fetchProfiles() {
  loading.value = true
  try {
    const res = await agentsApi.list()
    profiles.value = res.data
    filteredProfiles.value = res.data
  } finally {
    loading.value = false
  }
}

onMounted(fetchProfiles)
</script>

<style scoped>
.agents-view {
  max-width: 1400px;
  margin: 0 auto;
}

/* ── 页面头部 ── */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  padding: 24px;
  background: linear-gradient(135deg, #409EFF08 0%, #67C23A08 100%);
  border-radius: 12px;
  border: 1px solid #EBEEF5;
}

.page-title h2 {
  margin: 0 0 8px 0;
  font-size: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #303133;
}

.page-desc {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.page-stats {
  display: flex;
  gap: 32px;
}

.stat-item {
  text-align: center;
}

.stat-num {
  display: block;
  font-size: 28px;
  font-weight: 700;
  color: #409EFF;
  line-height: 1.2;
}

.stat-label {
  font-size: 12px;
  color: #909399;
}

/* ── 筛选栏 ── */
.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.search-input {
  max-width: 480px;
}

.filter-select {
  width: 200px;
}

/* ── 模块网格 ── */
.modules-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
}

.module-card {
  cursor: pointer;
  transition: all 0.25s ease;
  border-radius: 10px;
}

.module-card:hover {
  transform: translateY(-2px);
}

.module-card--expanded {
  grid-column: 1 / -1;
  max-width: 100%;
}

/* ── 卡片头部 ── */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.card-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.card-module-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.card-module-key {
  font-size: 12px;
  color: #909399;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.card-badges {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* ── 卡片摘要 ── */
.card-summary {
  margin-bottom: 14px;
}

.card-summary p {
  margin: 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}

/* ── 卡片区块 ── */
.card-section {
  margin-bottom: 14px;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}

.tag-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* ── 展开详情 ── */
.card-detail {
  margin-top: 4px;
}

.detail-table {
  margin-top: 4px;
}

/* ── 质量门禁 ── */
.quality-gates {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}

.gate-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  background: #F5F7FA;
  font-size: 13px;
  transition: all 0.2s ease;
}

.gate-item--active {
  background: #F0F9EB;
}

/* ── 卡片元数据 ── */
.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  font-size: 12px;
  color: #909399;
}

.card-meta strong {
  font-weight: 500;
  color: #606266;
}

/* ── 响应式 ── */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 16px;
  }
  .page-stats {
    width: 100%;
    justify-content: space-around;
  }
  .modules-grid {
    grid-template-columns: 1fr;
  }
  .quality-gates {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
