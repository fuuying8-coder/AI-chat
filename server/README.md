# LLM Chat Backend Server

这是 LLM Chat 应用的后端服务，使用 Node.js 和 Express 构建。

## 功能特性

- 🔄 API 代理：代理前端请求到实际的 LLM API
- 🌊 流式响应支持：完整支持流式数据传输
- 🔒 安全：API Key 在后端处理，不暴露给前端
- 🌐 CORS 支持：允许跨域请求
- ⚡ 快速启动：简单的配置和启动流程

## 安装依赖

```bash
cd server
npm install
```

或者使用 pnpm：

```bash
cd server
pnpm install
```

## 配置

1. 编辑 `.env` 文件，设置你的配置：

```env
# API 配置
API_BASE_URL=https://api.siliconflow.com/v1
API_KEY=your-api-key-here

# 服务器配置
PORT=3001
```

## 启动服务

### 开发模式（自动重启）

```bash
npm run dev
```

### 生产模式

```bash
npm start
```

服务将在 `http://localhost:3001` 启动。

## API 端点

### POST /api/chat/completions

聊天完成接口，支持流式和非流式响应。

**请求体：**
```json
{
  "model": "deepseek-ai/DeepSeek-R1",
  "messages": [
    {
      "role": "user",
      "content": "Hello!"
    }
  ],
  "stream": true,
  "max_tokens": 4096,
  "temperature": 0.7,
  "top_p": 0.7,
  "top_k": 50,
  "apiKey": "your-api-key" // 可选，也可以通过 Authorization 头传递
}
```

**响应：**
- 流式响应：返回 `text/event-stream` 格式的数据流
- 非流式响应：返回 JSON 格式的完整响应

### GET /health

健康检查接口，返回服务器状态。

## 前端配置

前端会自动尝试连接本地后端服务（`http://localhost:3001/api`）。如果后端服务不可用，会自动回退到直接调用 API。

你也可以通过环境变量 `VITE_API_BASE_URL` 自定义后端地址。

## 注意事项

- 确保后端服务在运行前端应用之前启动
- API Key 可以通过请求体或 Authorization 头传递
- 如果 `.env` 文件中设置了 `API_KEY`，将作为默认值使用

