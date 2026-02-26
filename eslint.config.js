import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'
import tseslint from '@typescript-eslint/eslint-plugin'
import tsParser from '@typescript-eslint/parser'

export default [
  {
    name: 'app/files-to-lint',
    files: ['**/*.{js,mjs,jsx,ts,tsx,vue}'], // ⚡ 加 TS 文件
  },

  {
    name: 'app/files-to-ignore',
    ignores: ['**/dist/**', '**/dist-ssr/**', '**/coverage/**', '**/node_modules/**', '**/server_python/.venv/**'],
  },

  // JS 基础规则
  js.configs.recommended,

  // Vue3 规则
  ...pluginVue.configs['flat/essential'],

  // Prettier skip
  skipFormatting,

  // 将易触发的规则改为警告，避免阻塞提交
  {
    rules: {
      'no-unused-vars': 'warn',
      'no-empty': 'warn',
    },
  },

  // TS 文件专用规则（仅 .ts/.tsx；.vue 由 pluginVue 用 vue-eslint-parser 解析）
  {
    files: ['**/*.ts', '**/*.tsx'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
    plugins: {
      '@typescript-eslint': tseslint,
    },
    rules: {
      '@typescript-eslint/no-unused-vars': 'warn',
    },
  },
  // .vue 的 script 用 TS 解析，仅加规则不覆盖主 parser
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tsParser,
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
    plugins: {
      '@typescript-eslint': tseslint,
    },
    rules: {
      '@typescript-eslint/no-unused-vars': 'warn',
    },
  },
]
