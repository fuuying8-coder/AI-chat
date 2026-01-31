## Python 版 LLM Chat 后端（`server_python`）

这是使用 **FastAPI** 实现的 Python 版后端，与原有 `server/index.js` 中的接口保持兼容：

- **GET** `/health`：健康检查
- **GET** `/api/test`：测试连接
- **POST** `/api/chat/completions`：代理转发到 SiliconFlow 的 `/chat/completions` 接口，支持流式响应

### 1. 安装依赖

在项目根目录执行：

```bash
cd server_python

# 建议创建虚拟环境（可选）
py -3.10 -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

在 `server_python` 目录下新建 `.env` 文件（也可以复用原来 `server` 目录的配置），示例：

```env
# API 配置
API_BASE_URL=https://api.siliconflow.com/v1
API_KEY=your-api-key-here

# 服务器配置
PORT=3001
```

说明：
- `API_KEY` 可以不写在 `.env`，也可以在请求体里通过 `apiKey` 字段，或通过 `Authorization: Bearer <key>` 传入。
- 若三者都没提供，则会返回 400 错误提示缺少 API Key。

### 3. 启动 Python 后端

在 `server_python` 目录下执行：

```bash
# 确保虚拟环境已激活（若有）
python main.py
```

默认会在 `http://localhost:3001` 启动服务（端口可通过 `.env` 中的 `PORT` 修改）。

也可以使用 `uvicorn` 命令手动启动：

```bash
uvicorn main:app --host 0.0.0.0 --port 3001 --reload
```

### 4. 与前端联动/切换说明

- 前端原本连接的是 Node 版后端：`http://localhost:3001/api/...`
- 现在 Python 版保持相同的路径和行为，只要：
  - 保持端口相同（默认为 3001），或者
  - 在前端通过环境变量（如 `VITE_API_BASE_URL`）把后端地址改为 Python 版服务地址，
即可无缝切换到 Python 后端。

### 5. 接口行为说明

- **API Key 解析优先级**：
  1. HTTP 头：`Authorization: Bearer <your-key>`
  2. 请求体字段：`apiKey`
  3. 环境变量：`.env` 中的 `API_KEY`

- **流式转发**：
  - `/api/chat/completions` 会把上游 SiliconFlow 的响应（包含 SSE 流）**原样转发**给前端，
    与原来 Node 版通过 `https.request(...).pipe(res)` 的行为一致。

