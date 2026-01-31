import asyncio
import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from openai import OpenAI


load_dotenv()

PORT = int(os.getenv("PORT", "3001"))
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.siliconflow.com/v1")
DEFAULT_API_KEY = os.getenv("API_KEY", "")

# 阿里云千问相关配置（不修改原有 API_BASE_URL）
ALI_API_KEY = os.getenv("ALI_API_KEY", os.getenv("DASHSCOPE_API_KEY", "sk-4a33dceeb78a4a98a25f1945010b76c3"))
ALI_QWEN_MODEL = "qwen-max"
ALI_QWEN_LONG_MODEL = "qwen-long"  # 长文本 + 文件解析
ALI_API_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 百炼支持的模型前缀/名称（前端可能选 DeepSeek 等，千问接口只认 qwen 系列）
def _normalize_qwen_model(model: Optional[str], default: str = ALI_QWEN_MODEL) -> str:
    """若请求的 model 不是百炼模型（如 DeepSeek），则用 default，避免 404 model_not_found。"""
    name = (model or "").strip().lower()
    if not name or not name.startswith("qwen"):
        return default
    return (model or "").strip()


def get_dashscope_client() -> OpenAI:
    """百炼兼容 OpenAI 的客户端，用于 files API 和 qwen-long 等。"""
    return OpenAI(
        api_key=ALI_API_KEY,
        base_url=ALI_API_BASE_URL,
    )

# ========== 分片上传：chunk 存储、异步合并、超时清理 ==========
UPLOAD_ROOT = Path(os.getenv("UPLOAD_ROOT", "uploads"))
CHUNKS_DIR = UPLOAD_ROOT / "chunks"  # chunks/{file_hash}/0, 1, 2, ...
MERGED_DIR = UPLOAD_ROOT / "merged"   # 合并后的临时文件
MERGED_REGISTRY = UPLOAD_ROOT / "merged_registry.json"  # file_hash -> file_id，重启后可恢复
CHUNK_EXPIRE_HOURS = int(os.getenv("CHUNK_EXPIRE_HOURS", "24"))
merge_jobs: Dict[str, dict] = {}  # job_id -> { status, file_id?, error? }


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fa5.\-]", "_", name)[:200]


def _chunk_dir(file_hash: str) -> Path:
    return CHUNKS_DIR / file_hash


app = FastAPI(title="LLM Chat Python Backend")

# CORS：允许本地前端（5173）访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def resolve_api_key(authorization: Optional[str], body: dict) -> Optional[str]:
    """从 Authorization 头、请求体或环境变量中解析 API Key。"""
    api_key: Optional[str] = None

    if authorization and authorization.startswith("Bearer "):
        api_key = authorization.replace("Bearer ", "").strip()

    if not api_key:
        api_key = body.get("apiKey")

    if not api_key and DEFAULT_API_KEY:
        api_key = DEFAULT_API_KEY

    return api_key


@app.get("/health")
async def health():
    """健康检查接口。"""
    timestamp = datetime.utcnow().isoformat()
    return {
        "status": "ok",
        "message": "Python backend server is running",
        "timestamp": timestamp,
        "port": PORT,
    }


def _test_response():
    """测试接口统一响应（供 /api/test 与 /test 使用）。"""
    return {
        "success": True,
        "message": "Python 后端服务连接正常！",
        "timestamp": datetime.utcnow().isoformat(),
        "backendUrl": f"http://localhost:{PORT}",
    }


@app.get("/api/test")
async def api_test():
    """测试接口，前端 checkBackendConnection 会请求此路径。"""
    return _test_response()


@app.get("/test")
async def api_test_alias():
    """测试接口别名（防止代理或路径差异导致未命中）。"""
    return _test_response()


async def upstream_stream(payload: dict, headers: dict) -> AsyncIterator[bytes]:
    """
    以流式方式将上游 SiliconFlow 的响应原样转发给前端。
    行为等价于 Node 版的 https.request + pipe。
    """
    url = f"{API_BASE_URL.rstrip('/')}/chat/completions"
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            async for chunk in resp.aiter_raw():
                if chunk:
                    # 直接把上游返回的字节写给前端（保持 SSE 或 JSON 原样）
                    yield chunk


@app.post("/api/chat/completions")
async def chat_completions(request: Request, authorization: Optional[str] = Header(None)):
    """
    Chat Completions 代理接口（SiliconFlow）。

    - 请求体字段与现有 Node 服务保持一致：
      model, messages, stream, max_tokens, temperature, top_p, top_k, apiKey
    - API Key 优先级：Authorization Bearer > body.apiKey > .env 中 API_KEY
    - 为了与当前 Node 实现保持一致，这里总是以流式方式转发上游响应，
      并设置 Content-Type 为 text/event-stream。
    """
    body = await request.json()

    api_key = resolve_api_key(authorization, body)
    if not api_key:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": "Missing API key. Provide via Authorization header, apiKey field, or API_KEY env.",
                }
            },
        )

    payload = {
        "model": body.get("model"),
        "messages": body.get("messages", []),
        "stream": body.get("stream", False),
        "max_tokens": body.get("max_tokens"),
        "temperature": body.get("temperature"),
        "top_p": body.get("top_p"),
        "top_k": body.get("top_k"),
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    return StreamingResponse(
        upstream_stream(payload, headers),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ========== 阿里云千问（通过 HTTP 调用，兼容原 LangChain 封装的接口） ==========

@app.post("/api/files/upload")
async def upload_file_for_extract(file: UploadFile = File(...)):
    """
    上传文件到百炼，用于 qwen-long 的 file-extract（长文档解析）。
    返回 file_id，前端在聊天时可将 file_id 传给 /api/chat/qwen，后端会以 fileid:// 形式放入 system。
    """
    if not ALI_API_KEY:
        return JSONResponse(
            status_code=500,
            content={"error": {"message": "Missing ALI_API_KEY or DASHSCOPE_API_KEY"}},
        )
    try:
        contents = await file.read()
        # 写入临时文件，因为 OpenAI SDK 的 files.create 需要 file 路径或 file-like
        tmp_path = Path(os.environ.get("TEMP", "/tmp")) / f"upload_{file.filename}"
        tmp_path.write_bytes(contents)
        try:
            client = get_dashscope_client()
            with open(tmp_path, "rb") as f:
                file_object = client.files.create(
                    file=f,
                    purpose="file-extract",
                )
            return {"file_id": file_object.id, "filename": file.filename}
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": {"message": str(e)}},
        )


# ---------- 分片上传：check / chunk / complete / status ----------

@app.post("/api/upload/check")
async def upload_check(request: Request):
    """
    前端计算 file_hash 后询问：该文件是否已存在？哪些 chunk 已上传？
    返回 exists + file_id（若已合并）或 uploaded_chunks 列表，避免重复上传。
    """
    body = await request.json()
    file_hash = (body.get("file_hash") or "").strip()
    file_name = (body.get("file_name") or "").strip()
    total_chunks = int(body.get("total_chunks") or 0)
    if not file_hash or total_chunks <= 0:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "file_hash and total_chunks required"}},
        )
    chunk_dir = _chunk_dir(file_hash)
    uploaded = []
    if chunk_dir.exists():
        for f in chunk_dir.iterdir():
            if f.is_file() and f.name.isdigit():
                try:
                    uploaded.append(int(f.name))
                except ValueError:
                    pass
    uploaded = sorted(set(uploaded))
    # 若已合并过（内存 job 或持久化 registry），直接返回 file_id，避免重复上传
    file_id = None
    for j in merge_jobs.values():
        if j.get("file_hash") == file_hash and j.get("status") == "success":
            file_id = j.get("file_id")
            break
    if not file_id and MERGED_REGISTRY.exists():
        try:
            reg = json.loads(MERGED_REGISTRY.read_text(encoding="utf-8"))
            file_id = reg.get(file_hash)
        except Exception:
            pass
    if file_id:
        return {"exists": True, "file_id": file_id, "uploaded_chunks": uploaded}
    if len(uploaded) >= total_chunks:
        # 全部 chunk 都在，但可能合并任务尚未完成，先返回已上传列表，前端会调 complete 再轮询
        pass
    return {"exists": False, "uploaded_chunks": uploaded}


@app.post("/api/upload/chunk")
async def upload_chunk(request: Request):
    """
    上传单个 chunk。用 file_hash + chunk_index 标识，分目录存储，避免重复。
    """
    form = await request.form()
    file_hash = (form.get("file_hash") or "").strip()
    chunk_index = form.get("chunk_index")
    chunk_file = form.get("chunk")
    if not file_hash or chunk_index is None or not chunk_file:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "file_hash, chunk_index and chunk (file) required"}},
        )
    try:
        idx = int(chunk_index)
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "chunk_index must be int"}},
        )
    content = await chunk_file.read()
    chunk_dir = _chunk_dir(file_hash)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    (chunk_dir / str(idx)).write_bytes(content)
    return {"ok": True}


@app.post("/api/upload/complete")
async def upload_complete(request: Request):
    """
    前端所有 chunk 上传完成后调用。后端异步合并，不阻塞；返回 job_id，前端轮询 status。
    """
    body = await request.json()
    file_hash = (body.get("file_hash") or "").strip()
    file_name = (body.get("file_name") or "").strip()
    total_chunks = int(body.get("total_chunks") or 0)
    chunk_size = int(body.get("chunk_size") or 0)
    if not file_hash or total_chunks <= 0:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "file_hash and total_chunks required"}},
        )
    job_id = str(uuid.uuid4())
    merge_jobs[job_id] = {
        "status": "pending",
        "file_hash": file_hash,
        "file_name": file_name,
        "total_chunks": total_chunks,
        "chunk_size": chunk_size,
    }
    asyncio.create_task(_do_merge(job_id))
    return {"job_id": job_id}


async def _do_merge(job_id: str):
    """
    异步合并：按序读 chunk 写成一个文件，再交给百炼 file-extract，更新 job 状态；合并失败则回滚标记，清理可后续做。
    """
    job = merge_jobs.get(job_id)
    if not job or job.get("status") != "pending":
        return
    try:
        job["status"] = "merging"
        file_hash = job["file_hash"]
        file_name = job["file_name"]
        total_chunks = job["total_chunks"]
        chunk_dir = _chunk_dir(file_hash)
        MERGED_DIR.mkdir(parents=True, exist_ok=True)
        merged_path = MERGED_DIR / f"{file_hash}_{_safe_filename(file_name)}"
        with open(merged_path, "wb") as out:
            for i in range(total_chunks):
                chunk_path = chunk_dir / str(i)
                if not chunk_path.exists():
                    raise FileNotFoundError(f"chunk {i} missing")
                out.write(chunk_path.read_bytes())
        # 上传到百炼 file-extract，拿到 file_id
        if ALI_API_KEY:
            client = get_dashscope_client()
            with open(merged_path, "rb") as f:
                file_object = client.files.create(file=f, purpose="file-extract")
            job["status"] = "success"
            job["file_id"] = file_object.id
            # 持久化 file_hash -> file_id，重启后可识别已合并文件
            reg = {}
            if MERGED_REGISTRY.exists():
                try:
                    reg = json.loads(MERGED_REGISTRY.read_text(encoding="utf-8"))
                except Exception:
                    pass
            reg[file_hash] = file_object.id
            MERGED_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
            MERGED_REGISTRY.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        else:
            job["status"] = "success"
            job["file_id"] = None
            job["merged_path"] = str(merged_path)
        # 合并成功，删除 chunk 目录，避免重复使用
        if chunk_dir.exists():
            shutil.rmtree(chunk_dir, ignore_errors=True)
        merged_path.unlink(missing_ok=True)
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)


@app.get("/api/upload/status")
async def upload_status(job_id: Optional[str] = None):
    """轮询合并状态：pending | merging | success | failed。"""
    if not job_id:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "job_id required"}},
        )
    job = merge_jobs.get(job_id)
    if not job:
        return {"status": "failed", "error": "job not found"}
    return {
        "status": job.get("status", "pending"),
        "file_id": job.get("file_id"),
        "error": job.get("error"),
    }


def _cleanup_stale_chunks():
    """定时清理超时未合并的 chunk 目录，避免垃圾数据。"""
    if not CHUNKS_DIR.exists():
        return
    import time
    now = time.time()
    for path in list(CHUNKS_DIR.iterdir()):
        if not path.is_dir():
            continue
        try:
            mtime = path.stat().st_mtime
            if now - mtime > CHUNK_EXPIRE_HOURS * 3600:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


@app.on_event("startup")
async def startup_cleanup():
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    MERGED_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_chunks()


async def call_qwen_with_langchain(
    messages: List[dict],
    model: Optional[str] = None,
) -> str:
    """
    使用 LangChain + ChatOpenAI 调用阿里云千问（OpenAI 兼容模式）
    """
    if not ALI_API_KEY:
        raise RuntimeError("Missing ALI_API_KEY")

    llm = ChatOpenAI(
        model=model or ALI_QWEN_MODEL,
        api_key=ALI_API_KEY,
        base_url=ALI_API_BASE_URL,
        temperature=0.7,
    )

    lc_messages = []
    for m in messages:
        if m["role"] == "system":
            lc_messages.append(SystemMessage(content=m["content"]))
        elif m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        else:
            # assistant 的历史可按需加
            lc_messages.append(HumanMessage(content=m["content"]))

    response = await llm.ainvoke(lc_messages)

    return response.content


async def call_qwen_stream_langchain(
    messages: List[dict],
    model: Optional[str] = None,
) -> AsyncIterator[bytes]:
    """LangChain 千问流式：按 OpenAI SSE 格式 yield。"""
    if not ALI_API_KEY:
        yield _sse_data({"error": {"message": "Missing ALI_API_KEY"}})
        return
    llm = ChatOpenAI(
        model=model or ALI_QWEN_MODEL,
        api_key=ALI_API_KEY,
        base_url=ALI_API_BASE_URL,
        temperature=0.7,
    )
    lc_messages = []
    for m in messages:
        if m["role"] == "system":
            lc_messages.append(SystemMessage(content=m["content"]))
        elif m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        else:
            lc_messages.append(HumanMessage(content=m["content"]))
    try:
        async for chunk in llm.astream(lc_messages):
            content = (chunk.content or "") if hasattr(chunk, "content") else ""
            if content:
                yield _sse_data({"choices": [{"delta": {"content": content, "reasoning_content": ""}}]})
        yield _sse_data("[DONE]")
    except Exception as e:
        yield _sse_data({"error": {"message": str(e)}})


def _sse_data(obj) -> bytes:
    """将对象序列化为 SSE 行：data: {...}\n\n。"""
    if isinstance(obj, str):
        payload = obj
    else:
        payload = json.dumps(obj, ensure_ascii=False)
    return f"data: {payload}\n\n".encode("utf-8")


@app.post("/api/chat/qwen")
async def chat_qwen(request: Request):
    """
    使用 LangChain + 阿里云千问的聊天接口。
    支持 stream=true 时返回 SSE 流式输出；支持 qwen-long + file_id。
    """
    body = await request.json()
    messages = body.get("messages", [])
    model = _normalize_qwen_model(body.get("model"), ALI_QWEN_MODEL)
    file_id = (body.get("file_id") or body.get("fileId") or "").strip()
    stream = body.get("stream", True)

    # 若带了 file_id，用百炼 OpenAI 兼容接口 + qwen-long
    if file_id:
        model = ALI_QWEN_LONG_MODEL
        system_content = f"fileid://{file_id}"
        new_messages = []
        has_system = False
        for m in messages:
            if m.get("role") == "system":
                has_system = True
                new_messages.append({
                    "role": "system",
                    "content": system_content + "\n\n" + (m.get("content") or ""),
                })
            else:
                new_messages.append(m)
        if not has_system:
            new_messages.insert(0, {"role": "system", "content": system_content})

        if stream:
            def _qwen_long_stream():
                try:
                    client = get_dashscope_client()
                    stream_resp = client.chat.completions.create(
                        model=model,
                        messages=new_messages,
                        stream=True,
                    )
                    for chunk in stream_resp:
                        if chunk.choices and len(chunk.choices) > 0:
                            delta = chunk.choices[0].delta
                            if delta and getattr(delta, "content", None):
                                yield _sse_data({
                                    "choices": [{"delta": {"content": delta.content, "reasoning_content": ""}}],
                                })
                    yield _sse_data("[DONE]")
                except Exception as e:
                    yield _sse_data({"error": {"message": str(e)}})

            return StreamingResponse(
                _qwen_long_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

        # 非流式
        start_time = datetime.utcnow()
        try:
            client = get_dashscope_client()
            completion = client.chat.completions.create(
                model=model,
                messages=new_messages,
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": {"message": str(e)}},
            )
        content = completion.choices[0].message.content or ""
        usage = getattr(completion, "usage", None)
        completion_tokens = usage.completion_tokens if usage else len(content)
        duration = max((datetime.utcnow() - start_time).total_seconds(), 1e-6)
        speed = completion_tokens / duration
        return {
            "choices": [{"message": {"content": content, "reasoning_content": ""}}],
            "usage": {"completion_tokens": completion_tokens},
            "speed": float(f"{speed:.2f}"),
        }

    # 无 file_id：LangChain 千问
    if stream:
        return StreamingResponse(
            call_qwen_stream_langchain(messages, model=model),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    start_time = datetime.utcnow()
    try:
        content = await call_qwen_with_langchain(messages, model=model)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": {"message": str(e)}},
        )

    content = (content or "").strip() if content is not None else ""
    duration = max((datetime.utcnow() - start_time).total_seconds(), 1e-6)
    completion_tokens = len(content) or 1
    speed = completion_tokens / duration

    return {
        "choices": [{"message": {"content": content, "reasoning_content": ""}}],
        "usage": {"completion_tokens": completion_tokens},
        "speed": float(f"{speed:.2f}"),
    }


if __name__ == "__main__":
    # 允许直接运行：python main.py
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)

