# 赫尔墨斯（Hermes）前端开发文档

> 版本：v1.0 | 更新日期：2026-06-08 | 适用模块：廉洁监察

---

## 一、项目概述

赫尔墨斯前端是基于 **Vue 3 + TypeScript + Element Plus** 的企业级单页应用（SPA），面向科沃斯集团风控部门，提供廉洁监察案件管理、碳基守门（HITL）、知识库检索等功能。

部署口径遵循 `doc/architecture-design.md`：P1 为正式生产 K8s 高可用架构，D0 Docker Compose 仅用于本地开发、测试、PoC 和容量验证。前端不得在 D0 配置中保存或展示生产密钥、生产账号或未脱敏生产数据。

### 1.1 技术栈

| 组件 | 选型 | 版本 |
|------|------|------|
| 框架 | Vue 3 (Composition API) | 3.5+ |
| 语言 | TypeScript | 5.6+ |
| 构建工具 | Vite | 6.0+ |
| UI 组件库 | Element Plus | 2.9+ |
| 状态管理 | Pinia | 2.2+ |
| 路由 | Vue Router | 4.4+ |
| HTTP 客户端 | Axios | 1.7+ |
| 工具函数 | @vueuse/core | 11.0+ |

### 1.2 项目结构

```
frontend/
├── index.html                # 应用入口 HTML
├── package.json              # 项目依赖
├── vite.config.ts            # Vite 配置（含代理配置）
├── tsconfig.json             # TypeScript 配置
├── env.d.ts                  # 类型声明
└── src/
    ├── main.ts               # 应用入口（注册 Pinia/Router/ElementPlus）
    ├── App.vue               # 根组件
    ├── api/
    │   └── index.ts          # API 封装（axios 实例 + 拦截器 + 各模块 API）
    ├── router/
    │   └── index.ts          # 路由配置 + 导航守卫
    ├── stores/
    │   └── auth.ts           # 认证状态管理（Pinia）
    ├── types/
    │   └── index.ts          # TypeScript 类型定义 + 业务常量
    └── views/
        ├── LoginView.vue     # 登录页
        ├── LayoutView.vue    # 主布局（侧边栏 + 头部 + 内容区）
        ├── CaseList.vue      # 案件列表（筛选/分页/启动工作流）
        ├── CaseCreate.vue    # 创建案件表单
        ├── CaseDetail.vue    # 案件详情（工作流步骤/阶段记录/文档）
        ├── ApprovalView.vue  # 碳基守门页（AI 输出展示/审批决策/划词调整）
        ├── KnowledgeView.vue # 知识库检索
        └── AdminView.vue     # 管理后台（用户管理/审计日志）
```

---

## 二、快速开始

### 2.1 环境准备

```bash
# Node.js >= 18
node --version

# 安装依赖
cd frontend
npm install
```

### 2.2 启动开发服务器

```bash
npm run dev
# 访问 http://localhost:5173
# API 请求自动代理到 http://localhost:8000
```

### 2.3 构建生产版本

```bash
npm run build
# 产出在 frontend/dist/ 目录
# 部署到 Nginx 静态资源目录
```

### 2.4 Nginx 生产部署配置

```nginx
server {
    listen 80;
    server_name hermes.example.com;

    root /var/www/hermes/frontend/dist;
    index index.html;

    # Vue SPA 路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api/ {
        proxy_pass http://api-svc:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket 代理
    location /ws {
        proxy_pass http://api-svc:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|svg|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 2.5 安全与生产治理约定

| 领域 | 前端实现要求 |
|------|--------------|
| 请求链路 | Axios 拦截器为每个请求生成或透传 `X-Request-Id`；异步任务、Webhook 状态页和 WebSocket 消息展示 `correlation_id` |
| 幂等提交 | 创建案件、启动工作流、审批、外部推送等写入动作必须带 `Idempotency-Key`，按钮在请求完成前进入 loading/disabled 状态 |
| 认证 | P1 生产使用企业 SSO/OIDC/AD 登录入口；D0 可使用本地登录页，但禁止复用生产账号密码 |
| 租户隔离 | 前端只展示后端授权返回的数据；不得通过手写 `client` 参数绕过 RBAC/RLS；集团全局视角需有显式权限提示 |
| 敏感信息 | 手机号、邮箱、身份证号、举报人、机密文件名默认脱敏；机密级下载需显示审批状态，不在浏览器缓存明文 |
| AI 输出 | 高风险 AI 结论必须显示证据/法规引用、置信度和"待人工复核"状态；前端不得把 AI 输出渲染成已确认事实 |
| Prompt 注入 | 用户输入和附件解析内容作为普通内容展示，不渲染为系统指令；富文本输出需做 XSS 清理 |
| 测试环境 | D0 测试环境页面应有环境标识，防止用户误以为是正式生产；测试数据需脱敏 |

---

## 三、路由设计

### 3.1 路由表

| 路径 | 组件 | 说明 | 权限 |
|------|------|------|------|
| `/login` | LoginView | 登录页 | 无需认证 |
| `/cases` | CaseList | 案件列表（首页） | 登录用户 |
| `/cases/create` | CaseCreate | 创建案件 | 登录用户 |
| `/cases/:id` | CaseDetail | 案件详情 | 登录用户 |
| `/cases/:id/approval` | ApprovalView | 碳基守门 | 登录用户 |
| `/knowledge` | KnowledgeView | 知识库检索 | 登录用户 |
| `/admin` | AdminView | 管理后台 | 集团角色 |

### 3.2 导航守卫

```typescript
// src/router/index.ts
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('access_token')
  // 白名单：登录页无需认证
  if (to.meta.guest) { next(); return }
  // 未登录重定向
  if (!token) { next('/login'); return }
  next()
})
```

---

## 四、状态管理

### 4.1 认证 Store (Pinia)

```typescript
// src/stores/auth.ts
export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const token = ref<string>(localStorage.getItem('access_token') || '')

  // 计算属性
  const isLoggedIn = () => !!token.value
  const isGroup = () => user.value?.role === 'group'
  const isEcovacs = () => user.value?.role === 'ecovacs'

  // 方法
  async function login(data: LoginRequest) { /* ... */ }
  async function fetchUser() { /* ... */ }
  function logout() { /* ... */ }

  return { user, token, isLoggedIn, isGroup, isEcovacs, login, fetchUser, logout }
})
```

---

## 五、API 集成

### 5.1 Axios 实例配置

```typescript
// src/api/index.ts
const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// 请求拦截：自动注入 JWT Token
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：401 自动跳转登录
http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)
```

### 5.2 API 模块说明

| 模块 | 函数 | 说明 |
|------|------|------|
| `authApi` | `login`, `logout`, `me` | 认证相关 |
| `casesApi` | `list`, `get`, `create`, `update`, `delete` | 案件 CRUD |
| `workflowApi` | `start`, `resume`, `status`, `history`, `interrupt` | 工作流操作 |
| `approvalApi` | `pending`, `submit`, `regenerate`, `history` | 守门审批 |
| `documentsApi` | `list`, `upload` | 文档管理 |
| `knowledgeApi` | `search`, `list` | 知识库检索 |
| `adminApi` | `users`, `createUser`, `toggleUser`, `auditLogs` | 管理后台 |

---

## 六、页面说明

### 6.1 登录页 (`LoginView.vue`)

- 登录表单：用户名 + 密码
- 表单校验
- 登录成功后写入 localStorage 并跳转首页
- 渐变紫色背景

### 6.2 主布局 (`LayoutView.vue`)

- 左侧导航：案件管理 / 创建案件 / 知识库 / 管理后台（集团角色可见）
- 顶部：面包屑导航 + 用户信息 + 角色标签 + 退出按钮
- 内容区：`<router-view />`

### 6.3 案件列表 (`CaseList.vue`)

- 筛选栏：事业部 / 来源 / 状态 / 关键字搜索
- 案件表格：编号 / 事业部 / 来源 / 阶段 / 状态 / 创建人 / 时间 / 操作
- 操作按钮：详情 / 启动工作流 / 碳基守门
- 分页组件

### 6.4 创建案件 (`CaseCreate.vue`)

- 表单字段：事业部 / 来源 / 事件详情 / 证据简述 / 涉及员工 / 涉及供应商 / 涉及经销商 / 举报人信息 / 风控案件ID
- 表单校验
- 提示：当前风控系统尚未接入，为手动上传模式

### 6.5 案件详情 (`CaseDetail.vue`)

- 案件基本信息：`el-descriptions` 组件展示
- 工作流进度：`el-steps` 组件展示 6 个阶段
- 阶段流转记录：`el-timeline` 组件展示
- 生成文档列表：`el-table` 组件展示

### 6.6 碳基守门 (`ApprovalView.vue`)

关键的人机协同（HITL）页面，提供：
- AI 输出展示：结构化展示 AI Agent 的分析结果
- 守门决策：确认通过 / 驳回重做 / 修改后通过
- 审核意见输入
- 划词调整（预留）：选中 AI 输出段落 → 输入修改指令 → AI 重新生成
- 守门历史记录

### 6.7 知识库检索 (`KnowledgeView.vue`)

- 搜索栏：关键词 + 知识库类型多选
- 结果表格：类型 / 标题 / 内容摘要 / 相关度（进度条）

### 6.8 管理后台 (`AdminView.vue`)

- Tab 1: 用户管理（列表 / 创建 / 启用禁用）
- Tab 2: 审计日志（只读查询）

---

## 七、开发规范

### 7.1 组件开发

```vue
<template>
  <div class="component-name">
    <!-- 模板 -->
  </div>
</template>

<script setup lang="ts">
// 使用 Composition API + <script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { apiModule } from '@/api'

// 响应式数据
const data = ref<Type[]>([])
const loading = ref(false)

// 计算属性
const displayValue = computed(() => /* ... */)

// 生命周期
onMounted(() => { /* fetch data */ })

// 方法
async function fetchData() { /* ... */ }
</script>

<style scoped>
/* 组件样式 */
</style>
```

### 7.2 类型定义

所有业务类型在 `src/types/index.ts` 中统一定义，包括：
- API 请求/响应类型
- 业务实体类型（Case, User, Document 等）
- 枚举映射常量（STAGE_LABELS, CLIENT_LABELS, SOURCE_LABELS）

### 7.3 API 调用

```typescript
// ✅ 推荐：使用封装的 API 模块
import { casesApi } from '@/api'

const res = await casesApi.list({ page: 1, page_size: 20 })
cases.value = res.data.items

// ❌ 避免：直接使用 axios
import axios from 'axios'
axios.get('/api/v1/cases')  // 不会自动注入 token
```

### 7.4 错误处理

```typescript
// 使用 try-catch + ElMessage
try {
  await casesApi.create(payload)
  ElMessage.success('案件创建成功')
  router.push('/cases')
} catch {
  ElMessage.error('创建案件失败')
}
```

### 7.5 权限控制

```typescript
// 组件级权限控制
const authStore = useAuthStore()

// 模板中条件渲染
<el-menu-item v-if="authStore.isGroup()" index="/admin">管理后台</el-menu-item>

// 路由级权限：在 meta 中标记 { group: true }
```

---

## 八、页面状态管理

### 8.1 案件工作流状态流转

```
pending (待处理)
  → investigating (调查中: workflow started)
    → pending_approval (待守门: 每个阶段完成后)
      → approved (守门通过: 进入下一阶段)
      → rejected (守门驳回: 重新执行当前阶段)
  → closed (已结案: 工作流完成或终止)
  → transferred (已转交: HR/其他部门)
```

### 8.2 前端状态显示

| 后端状态 | 前端显示 | 标签颜色 |
|----------|----------|---------|
| pending | 待处理 | info (灰) |
| investigating | 调查中 | warning (橙) |
| closed | 已结案 | success (绿) |
| pending_approval | 待守门 | primary (蓝) |

---

## 九、构建与部署

### 9.1 开发环境

```bash
npm run dev
# Vite 开发服务器，支持 HMR 热更新
# API 代理配置在 vite.config.ts 中
```

### 9.2 生产构建

```bash
npm run build
# TypeScript 类型检查 + Vite 打包
# 产出目录: dist/
#    ├── index.html
#    ├── assets/
#    │   ├── index-<hash>.js     (~200KB gzip)
#    │   └── index-<hash>.css    (~80KB gzip)
#    └── ...
```

### 9.3 Docker 部署

```dockerfile
# 多阶段构建
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM nginx:1.26-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

---

## 十、参考文档

- [系统架构设计](./architecture-design.md)
- [廉洁监察模块需求](./modules/01-integrity-supervision.md)
- [API 设计文档](./api-design.md)
- [后端开发文档](./backend-development-guide.md)
- [Vue 3 官方文档](https://vuejs.org/)
- [Element Plus 官方文档](https://element-plus.org/)
- [Vite 官方文档](https://vitejs.dev/)
