# 阶段 1: 前端构建
FROM node:18-alpine AS frontend-build
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN npm install -g pnpm && pnpm install
COPY . .
RUN npm run build

# 阶段 2: Python 后端运行
FROM python:3.10-slim
WORKDIR /app

# 复制前端构建产物
COPY --from=frontend-build /app/dist ./dist

# 复制 Python 后端代码
COPY server_python ./server_python

WORKDIR /app/server_python

# 安装 Python 依赖
COPY server_python/requirements.txt .
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install --no-cache-dir -r requirements.txt

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PORT=3001

EXPOSE 3001

CMD ["python", "server_python/main.py"]
