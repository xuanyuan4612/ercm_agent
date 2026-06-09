<template>
  <el-container class="layout-container">
    <el-aside width="220px" class="layout-aside">
      <div class="logo">
        <h3>🔱 赫尔墨斯</h3>
        <small>风控 AI 智能体</small>
      </div>
      <el-menu :default-active="route.path" router background-color="#304156" text-color="#bfcbd9" active-text-color="#409EFF">
        <el-menu-item index="/cases">
          <el-icon><Folder /></el-icon>
          <span>案件管理</span>
        </el-menu-item>
        <el-menu-item index="/cases/create">
          <el-icon><Plus /></el-icon>
          <span>创建案件</span>
        </el-menu-item>
        <el-menu-item index="/knowledge">
          <el-icon><Collection /></el-icon>
          <span>知识库检索</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.isGroup()" index="/admin">
          <el-icon><Setting /></el-icon>
          <span>管理后台</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="layout-header">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="route.meta.title">{{ route.meta.title }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <span class="user-info">
            <el-icon><User /></el-icon>
            {{ authStore.user?.display_name || authStore.user?.username }}
            <el-tag size="small" style="margin-left: 8px">
              {{ roleLabel }}
            </el-tag>
          </span>
          <el-button text @click="authStore.logout()">退出</el-button>
        </div>
      </el-header>

      <el-main class="layout-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()

const roleLabel = computed(() => {
  const labels: Record<string, string> = {
    group: '集团管理员', ecovacs: '科沃斯', tineco: '添可',
  }
  return labels[authStore.user?.role || ''] || authStore.user?.role || ''
})
</script>

<style scoped>
.layout-container { height: 100vh; }
.layout-aside { background-color: #304156; overflow-y: auto; }
.logo { padding: 20px 16px; text-align: center; color: #fff; border-bottom: 1px solid rgba(255,255,255,0.1); }
.logo h3 { margin: 0; font-size: 18px; }
.logo small { font-size: 12px; opacity: 0.7; }
.layout-header { display: flex; align-items: center; justify-content: space-between; background: #fff; border-bottom: 1px solid #e4e7ed; padding: 0 20px; }
.layout-main { background: #f5f7fa; padding: 20px; }
.user-info { display: flex; align-items: center; gap: 4px; margin-right: 12px; }
</style>
