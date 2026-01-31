
# Copilot Instructions for LLM Chat Box 2.0

## 项目架构概览
- 前端：`src/` 目录，基于 Vue 3 + Vite，主入口 `src/main.js`，页面在 `views/`，核心组件在 `components/`。
- 状态管理：Pinia，集中于 `src/stores/`，持久化用 `pinia-plugin-persistedstate`。
- 样式：SCSS，主样式在 `src/assets/styles/`，采用变量和模块化。
- 后端：
  - Node.js/Express 版在 `server/`，主入口 `server/index.js`，API 代理、流式响应、安全校验。
  - Python/FastAPI 版在 `server_python/`，主入口 `server_python/main.py`，接口与 Node 版兼容。
- 典型数据流：前端所有 API 调用通过 `src/utils/api.js` 统一封装，走 `/api/chat/completions`，后端代理到 SiliconFlow API，支持流式返回。

## 关键开发工作流
- 前端依赖安装：`pnpm install` 或 `npm install`
- 前端开发启动：`pnpm dev` 或 `npm run dev`
- 前端构建：`pnpm build` 或 `npm run build`
- Node.js 后端依赖：`cd server && pnpm install` 或 `npm install`
- Node.js 后端启动：`cd server && node index.js`（需配置 `.env`）
- Python 后端依赖：`cd server_python && pip install -r requirements.txt`
- Python 后端启动：`cd server_python && uvicorn main:app --reload`（需配置 `.env`）

## 配置与环境变量
- `.env` 文件需包含：
  - `API_BASE_URL`：目标 LLM API 地址
  - `API_KEY`：API 密钥（可选，支持多种传递方式）
  - `PORT`：服务端口
- Python 后端支持 API Key 通过 `.env`、请求体 `apiKey` 字段或 `Authorization` 头传递

## 主要约定与模式
- 组件命名统一采用 PascalCase。
- 前端所有 API 调用通过 `src/utils/api.js` 统一封装，便于切换后端实现和接口扩展。
- 状态管理集中于 `src/stores/`，如 `chat.js`、`setting.js`。
- 组件按功能拆分于 `src/components/`，如 `ChatInput.vue`、`ChatMessage.vue`、`SettingsPanel.vue`。
- 支持多会话、消息历史、流式响应、文件/图片上传、主题切换等。

## 跨端/多后端兼容
- 前端通过统一 API 适配 Node.js/Express 与 Python/FastAPI 两种后端。
- 后端接口需保持 `/api/chat/completions`、`/api/test`、`/health` 等路径兼容。

## 典型文件/目录参考
- `src/utils/api.js`：前端 API 封装
- `src/stores/`：Pinia 状态管理
- `server/index.js`：Node.js 后端主入口
- `server_python/main.py`：Python 后端主入口
- `README.md`、`server/README.md`、`server_python/README.md`：详细说明

---
如需扩展功能、适配新后端或调整 API，优先参考现有封装和接口规范。遇到不明确的约定或流程，请先查阅上述 README 或相关源码。