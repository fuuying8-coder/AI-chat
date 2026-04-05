import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'


// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver({ importStyle: false })],
    }),
    Components({
      resolvers: [ElementPlusResolver({ importStyle: false })],
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  build: {
    // 增加代码分割阈值，优化加载速度
    rollupOptions: {
      output: {
        manualChunks: {
          // 将依赖分离到独立chunks
          'vue-flow': ['@vue-flow/core', '@vue-flow/background', '@vue-flow/controls', '@vue-flow/minimap'],
          'element-plus': ['element-plus', '@element-plus/icons-vue'],
          'markdown': ['markdown-it', 'markdown-it-emoji', 'markdown-it-link-attributes', 'highlight.js'],
          'idb': ['idb'],
          'virtual-scroller': ['vue-virtual-scroller'],
        },
      },
    },
    // 减少chunk大小警告阈值
    chunkSizeWarningLimit: 1000,
  },
  // 优化依赖预构建
  optimizeDeps: {
    include: [
      'vue',
      'vue-router',
      'pinia',
      'element-plus',
      '@element-plus/icons-vue',
      'idb',
      'lodash-es',
      'markdown-it',
    ],
  },
})
