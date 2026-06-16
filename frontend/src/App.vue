<template>
  <router-view />
</template>

<script setup lang="ts">
// App 根组件 - 路由视图
</script>

<style>
/* ═══ 全局样式 ═══ */
:root {
  --color-primary: #409EFF;
  --color-success: #67C23A;
  --color-warning: #E6A23C;
  --color-danger: #F56C6C;
  --color-info: #909399;
  --bg-page: #F0F2F5;
  --bg-white: #FFFFFF;
  --border-color: #EBEEF5;
  --text-primary: #303133;
  --text-regular: #606266;
  --text-secondary: #909399;
  --text-placeholder: #C0C4CC;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --shadow-sm: 0 1px 4px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.06);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.08);
}

html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--text-primary);
  background: var(--bg-page);
}

/* ── 滚动条美化 ── */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #C0C4CC;
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: #909399;
}

/* ── Element Plus 微调 ── */
.el-card {
  border: 1px solid var(--border-color) !important;
}

.el-button--primary {
  --el-button-hover-bg-color: #66B1FF;
  --el-button-active-bg-color: #3A8EE6;
}

.el-table th.el-table__cell {
  background-color: #FAFAFA !important;
  color: var(--text-regular);
  font-weight: 600;
}

.el-table .el-table__row:hover > td {
  background-color: #F5F7FA !important;
}

.el-tag {
  border: none !important;
}

/* ── 通用工具类 ── */
.text-muted { color: var(--text-secondary) !important; }
.text-center { text-align: center; }
.mt-16 { margin-top: 16px; }
.mb-16 { margin-bottom: 16px; }
</style>
