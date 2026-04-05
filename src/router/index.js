import { createRouter, createWebHistory } from 'vue-router'
import { defineAsyncComponent } from 'vue'

import HomePage from '@/views/HomePage.vue'

// 首页使用同步加载，其他页面使用懒加载
const ChatView = defineAsyncComponent(() => import('@/views/ChatView.vue'))
const JobDetailView = defineAsyncComponent(() => import('@/views/JobDetailView.vue'))

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomePage,
    },
    {
      path: '/chat',
      name: 'chat',
      component: ChatView,
    },
    {
      path: '/job/:id',
      name: 'job-detail',
      component: JobDetailView,
    },
  ],
})

export default router
