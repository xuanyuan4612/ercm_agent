import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { guest: true },
    },
    {
      path: '/',
      name: 'Layout',
      component: () => import('@/views/LayoutView.vue'),
      redirect: '/cases',
      children: [
        {
          path: 'cases',
          name: 'CaseList',
          component: () => import('@/views/CaseList.vue'),
          meta: { title: '案件列表' },
        },
        {
          path: 'cases/create',
          name: 'CaseCreate',
          component: () => import('@/views/CaseCreate.vue'),
          meta: { title: '创建案件' },
        },
        {
          path: 'cases/:id',
          name: 'CaseDetail',
          component: () => import('@/views/CaseDetail.vue'),
          meta: { title: '案件详情' },
        },
        {
          path: 'cases/:id/approval',
          name: 'Approval',
          component: () => import('@/views/ApprovalView.vue'),
          meta: { title: '碳基守门' },
        },
        {
          path: 'knowledge',
          name: 'Knowledge',
          component: () => import('@/views/KnowledgeView.vue'),
          meta: { title: '知识库' },
        },
        {
          path: 'admin',
          name: 'Admin',
          component: () => import('@/views/AdminView.vue'),
          meta: { title: '管理后台', group: true },
        },
      ],
    },
  ],
})

// 路由守卫
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.meta.guest) {
    next()
    return
  }
  if (!token && to.name !== 'Login') {
    next('/login')
    return
  }
  next()
})

export default router
