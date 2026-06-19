<template>
  <el-container class="layout-container">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapsed ? '64px' : '220px'" class="layout-aside">
      <div class="logo" @click="$router.push('/')">
        <div class="logo-icon">🔱</div>
        <transition name="fade">
          <div v-show="!isCollapsed" class="logo-text">
            <h3>赫尔墨斯</h3>
            <small>风控 AI 智能体</small>
          </div>
        </transition>
      </div>

      <el-menu
        :default-active="route.path"
        :default-openeds="openSubmenus"
        router
        :collapse="isCollapsed"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
        class="side-menu"
      >
        <el-sub-menu index="/integrity">
          <template #title>
            <el-icon><Search /></el-icon>
            <span>廉洁监察</span>
          </template>
          <el-menu-item index="/cases">案件管理</el-menu-item>
          <el-menu-item index="/cases/create">创建案件</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/agents">
          <el-icon><Cpu /></el-icon>
          <template #title>AI Agent</template>
        </el-menu-item>
        <el-sub-menu index="/risk-monitor">
          <template #title>
            <el-icon><WarningFilled /></el-icon>
            <span>风险监控</span>
          </template>
          <el-menu-item index="/risk-monitor/rules">规则管理</el-menu-item>
          <el-menu-item index="/risk-monitor/scans">扫描任务</el-menu-item>
          <el-menu-item index="/risk-monitor/alerts">预警列表</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/knowledge">
          <el-icon><Collection /></el-icon>
          <template #title>知识库</template>
        </el-menu-item>
        <el-menu-item v-if="authStore.isGroup()" index="/admin">
          <el-icon><Setting /></el-icon>
          <template #title>管理后台</template>
        </el-menu-item>
      </el-menu>

      <!-- 折叠按钮 -->
      <div class="collapse-btn" @click="isCollapsed = !isCollapsed">
        <el-icon :size="18">
          <component :is="isCollapsed ? 'Expand' : 'Fold'" />
        </el-icon>
      </div>
    </el-aside>

    <!-- 右侧主区域 -->
    <el-container>
      <el-header class="layout-header">
        <div class="header-left">
          <el-breadcrumb separator="›">
            <el-breadcrumb-item :to="{ path: '/' }">
              <el-icon :size="14"><HomeFilled /></el-icon>
              首页
            </el-breadcrumb-item>
            <el-breadcrumb-item v-if="route.meta.title">{{ route.meta.title }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tooltip content="知识库检索" placement="bottom">
            <el-button text circle @click="$router.push('/knowledge')">
              <el-icon :size="18"><Search /></el-icon>
            </el-button>
          </el-tooltip>
          <el-divider direction="vertical" />
          <el-dropdown trigger="click">
            <span class="user-info">
              <el-avatar :size="28" icon="UserFilled" />
              <span class="user-name">{{ authStore.user?.display_name || authStore.user?.username }}</span>
              <el-tag size="small" effect="light" :type="roleTagType">
                {{ roleLabel }}
              </el-tag>
              <el-icon :size="14"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  <div class="dropdown-user-info">
                    <div>{{ authStore.user?.display_name }}</div>
                    <small>{{ authStore.user?.department }} · {{ authStore.user?.email }}</small>
                  </div>
                </el-dropdown-item>
                <el-dropdown-item divided @click="authStore.logout()">
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="layout-main">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  ArrowDown,
  Expand,
  Fold,
  HomeFilled,
  Search,
  SwitchButton,
  WarningFilled,
} from '@element-plus/icons-vue'

const route = useRoute()
const authStore = useAuthStore()
const isCollapsed = ref(false)

const openSubmenus = computed(() => {
  const opened: string[] = []
  if (route.path.startsWith('/cases')) opened.push('/integrity')
  if (route.path.startsWith('/risk-monitor')) opened.push('/risk-monitor')
  return opened
})

const roleLabel = computed(() => {
  const labels: Record<string, string> = {
    group: '集团管理员', ecovacs: '科沃斯', tineco: '添可',
  }
  return labels[authStore.user?.role || ''] || authStore.user?.role || ''
})

const roleTagType = computed(() => {
  const map: Record<string, string> = { group: 'danger', ecovacs: 'success', tineco: 'warning' }
  return map[authStore.user?.role || ''] || 'info'
})
</script>

<style scoped>
.layout-container { height: 100vh; }
.layout-aside {
  background-color: #304156;
  overflow-y: auto;
  transition: width 0.3s ease;
  display: flex;
  flex-direction: column;
  position: relative;
}

/* ── Logo ── */
.logo {
  padding: 20px 16px;
  text-align: center;
  color: #fff;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  transition: padding 0.3s ease;
}
.logo-icon { font-size: 28px; flex-shrink: 0; }
.logo-text { transition: opacity 0.2s ease; }
.logo-text h3 { margin: 0; font-size: 16px; white-space: nowrap; }
.logo-text small { font-size: 11px; opacity: 0.6; display: block; }

/* ── 菜单 ── */
.side-menu { border-right: none; flex: 1; }
.side-menu .el-menu-item { transition: all 0.2s ease; }
.side-menu .el-menu-item:hover { background-color: rgba(255,255,255,0.05) !important; }

/* ── 折叠按钮 ── */
.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  cursor: pointer;
  color: rgba(255,255,255,0.4);
  border-top: 1px solid rgba(255,255,255,0.08);
  transition: color 0.2s ease;
}
.collapse-btn:hover { color: rgba(255,255,255,0.8); background: rgba(255,255,255,0.04); }

/* ── 头部 ── */
.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #EBEEF5;
  padding: 0 24px;
  height: 56px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.header-left { display: flex; align-items: center; }
.header-right { display: flex; align-items: center; gap: 4px; }

/* ── 用户信息 ── */
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 8px;
  transition: background 0.2s ease;
}
.user-info:hover { background: #F5F7FA; }
.user-name { font-size: 14px; color: #303133; }

.dropdown-user-info { line-height: 1.4; }
.dropdown-user-info small { color: #909399; font-size: 12px; }

/* ── 主区域 ── */
.layout-main {
  background: #F0F2F5;
  padding: 24px;
  min-height: 0;
  overflow-y: auto;
}

/* ── 页面过渡动画 ── */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.page-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.fade-enter-active,
.fade-leave-active { transition: opacity 0.25s ease; }
.fade-enter-from,
.fade-leave-to { opacity: 0; }
</style>
