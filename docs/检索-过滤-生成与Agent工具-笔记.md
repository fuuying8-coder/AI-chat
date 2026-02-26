# 检索 - 过滤 - 生成 与 Agent 工具 笔记

整理「检索-过滤-生成」三阶段 RAG 推理流程（限制模型仅基于向量库检索到的权威文献作答），以及既有生物信息预测模型与分析算法封装为 Tool 接口、Agent 调度的实现与可扩展集成方式。

---

## 一、三阶段推理：检索 - 过滤 - 生成

### 1.1 目标

- **检索**：根据用户问题从向量数据库中召回相关段落。
- **过滤**：按相似度得分（或元数据）过滤，只保留“权威/相关”段落，避免低质量或无关片段进入生成。
- **生成**：大模型**仅基于**上述检索并过滤后的参考段落作答，不编造；若参考中无答案则如实说明。

### 1.2 代码结构

```
server_python/
├── rag_config.py      # K、得分阈值、模型名等
├── vector_stores.py   # 向量检索 + 检索-过滤（retrieve_and_filter）
├── rag.py             # RAG 服务：三阶段链（retrieve → filter → format → generate）
├── knowledge_base.py  # 知识库入库：分片、向量化、MD5 去重
└── main.py            # /api/rag/upload, /api/rag/documents, /api/chat/rag
```

### 1.3 三阶段在代码中的对应

| 阶段   | 实现位置 | 说明 |
|--------|----------|------|
| 检索   | `VectorStoreService.retrieve_and_filter` 内 `similarity_search_with_score(query, k)` | 向量库 Top-K 召回 |
| 过滤   | 同上，`score <= retrieval_score_threshold` | 仅保留得分优于阈值的段落；阈值为 0 或 None 时不过滤 |
| 生成   | `RagService._get_chain`：`context` → prompt → 千问 → StrOutputParser | 系统提示中明确“严格根据参考段落回答，不要编造” |

### 1.4 配置项（rag_config.py）

```python
# 检索 Top-K
similarity_threshold = 4

# 过滤：仅保留 score <= 此值的段落（Chroma 为距离，越小越相似）
# 0 或 None = 不过滤，仅做 Top-K
retrieval_score_threshold = float(os.getenv("RAG_SCORE_THRESHOLD", "0")) or None
```

环境变量 `RAG_SCORE_THRESHOLD` 可设为正数（如 `1.5`），则只把距离 ≤ 1.5 的段落作为“权威文献”送入生成。

### 1.5 核心代码片段

**vector_stores.py：检索 + 过滤**

```python
def retrieve_and_filter(self, query: str, k: int = None, score_threshold: float = None) -> list:
    k = k or similarity_threshold
    threshold = score_threshold if score_threshold is not None else retrieval_score_threshold
    try:
        pairs = self.vector_store.similarity_search_with_score(query, k=k)
    except Exception:
        pairs = []
    if not threshold:
        return [doc for doc, _ in pairs]
    return [doc for doc, score in pairs if score <= threshold]
```

**rag.py：链式三阶段（检索-过滤 → 格式化 → 生成）**

```python
def retrieve_filter_format(question: str) -> str:
    docs = self.vector_service.retrieve_and_filter(question)
    return _format_document(docs)

chain = (
    {
        "context": itemgetter("input") | retrieve_filter_format,
        "input": itemgetter("input"),
        "history": itemgetter("history"),
    }
    | self.prompt_template
    | self.chat_model
    | StrOutputParser()
)
```

**系统提示（限制仅基于参考作答）**

```text
你是一个基于知识库的问答助手。请严格根据以下「参考段落」回答用户问题；若参考段落中未包含答案，请如实说明。不要编造内容。

参考段落：
{context}
```

---

## 二、生物信息预测模型与分析算法：Tool 接口与 Agent 调度

### 2.1 目标

- 将既有生物信息预测模型（如 MGCNA 药物-miRNA 关联预测）与分析算法封装为 **Tool** 接口。
- 通过 **Agent 调度**：用户自然语言 → 意图解析（drug、top_n）→ 调用 Tool → 结果格式化 → LLM 推理与润色，实现模型能力的工具化与可扩展集成。

### 2.2 代码结构

```
server_python/
├── main.py                    # Agent 入口：/api/chat/case-study、/api/case-study/drug-top-mirnas
└── tools/
    ├── DESIGN.md              # Case Study 设计：流程、接口、扩展
    ├── drug_mirna_mappings.py # 药物/miRNA ID↔名称映射
    ├── case_study_service.py  # Tool 实现：query_drug_top_mirnas
    ├── data_preprocess5fold.py
    ├── layer3.py              # MGCNA 模型
    ├── parms_setting.py
    └── best_model_global.pth  # 模型权重
```

### 2.3 Tool 接口设计

**Case Study Tool**：查询某药物的 Top-N 关联 miRNA（MGCNA 预测）。

- **输入**：`drug`（名称或 ID）、`top_n`（默认 25）。
- **输出**：`{ success, drug_id, drug_name, drugbank_id, top_mirnas: [{ rank, mirna_id, mirna_name, score }] }`。

**HTTP API（直接调用 Tool）**

```http
POST /api/case-study/drug-top-mirnas
Body: { "drug": "Docetaxel", "top_n": 20 }
```

**case_study_service.py 核心接口**

```python
def query_drug_top_mirnas(drug: str | int, top_n: int = 25) -> Dict[str, Any]:
    """
    查询某药物的 Top-N 关联 miRNA。
    返回: success, error, drug_id, drug_name, drugbank_id, top_mirnas
    """
    predictor, err = _load_case_study_predictor()
    if predictor is None:
        return query_drug_top_mirnas_standalone(drug, top_n)
    # 解析 drug_id → 运行 MGCNA 预测 → 映射 mirna_id → miRNA 名称 → 返回结构化结果
    ...
```

### 2.4 Agent 调度流程（main.py）

1. **入口**：`POST /api/chat/case-study`，从 `messages` 取最后一条用户问题。
2. **意图解析**：当前为规则（正则）提取 `drug`、`top_n`；可后续改为 LLM 意图识别或 Function Calling。
3. **调用 Tool**：`query_drug_top_mirnas(drug=drug, top_n=top_n)`。
4. **结果格式化**：`_build_tool_result_text(result)` 转为供 LLM 阅读的文本。
5. **生成**：将「工具结果 + 固定说明」作为 user 消息，调用千问进行推理与润色，流式或非流式返回。

```python
# 规则提取 drug / top_n（可替换为 LLM）
top_match = re.search(r"(?:top|前)\s*(\d+)", question, re.I)
drug_match = re.search(r"(?:查询|查找|搜索|的药物|的\s*关联)\s*([^\s，,。]+)", question)
# ...
result = await asyncio.to_thread(query_drug_top_mirnas, drug=drug, top_n=top_n)
user_prompt = f"{tool_result_text}\n\n请结合以上工具查询结果与你的推理能力，写一段回复：..."
messages = [
    {"role": "system", "content": _SYSTEM_PROMPT_CASE_STUDY},
    {"role": "user", "content": user_prompt},
]
# 流式 / 非流式调用千问
```

### 2.5 前端与模式切换

- **ChatView.vue**：根据 `useCaseStudyMode` / `useRagMode` 选择接口：
  - Case Study 模式 → `createCaseStudyChatCompletion(messages, { stream, signal })`
  - RAG 模式 → `createRagChatCompletion(messages, { stream, signal, sessionId })`
  - 默认 → `createChatCompletion(messages, { fileId, stream, signal })`
- **api.js**：`createCaseStudyChatCompletion` 请求 `POST /api/chat/case-study`；`createRagChatCompletion` 请求 `POST /api/chat/rag`。

### 2.6 可扩展集成方式

- **新增 Tool**：在 `tools/` 下实现新的 `query_xxx(args) -> dict`，在 `main.py` 中注册路由（如 `/api/xxx/yyy`）和 Agent 分支（如解析意图后调用该工具再拼 prompt）。
- **统一 Tool 注册**：可抽象为「工具名 → 调用函数 + 参数 schema」，Agent 用 LLM Function Calling 选择工具与参数，再执行并汇总结果。
- **DESIGN.md** 中扩展建议：反向查询（miRNA → 药物）、批量查询、阈值过滤、缓存、异步任务等。

---

## 三、相关文件索引

| 文件 | 职责 |
|------|------|
| `server_python/rag_config.py` | RAG 与知识库配置（K、得分阈值、模型名） |
| `server_python/vector_stores.py` | 向量检索、retrieve_and_filter（检索+过滤） |
| `server_python/rag.py` | 三阶段 RAG 链、仅基于参考段落生成的 prompt |
| `server_python/knowledge_base.py` | 知识库上传、分片、向量化、MD5 去重 |
| `server_python/main.py` | /api/rag/*、/api/chat/rag；/api/case-study/*、/api/chat/case-study |
| `server_python/tools/case_study_service.py` | Tool：query_drug_top_mirnas |
| `server_python/tools/DESIGN.md` | Case Study 设计与扩展 |
| `src/utils/api.js` | createRagChatCompletion、createCaseStudyChatCompletion |
| `src/views/ChatView.vue` | 模式切换与发送时选择 RAG / Case Study / 普通聊天 |

---

## 四、小结

- **检索-过滤-生成**：在 `vector_stores` 中通过 `retrieve_and_filter` 完成检索与按得分过滤，在 `rag.py` 中仅将过滤后的段落作为 `context` 送入千问，并通过系统提示限制“严格根据参考段落作答”，实现仅基于向量库权威文献的生成。
- **Tool 与 Agent**：生物信息预测（MGCNA）封装为 `query_drug_top_mirnas` Tool；Agent 在 `main.py` 中完成意图解析 → 调用 Tool → 结果格式化 → LLM 润色，前端通过模式开关选择 RAG / Case Study / 普通聊天，便于后续增加更多工具与统一调度。

---

## 五、涉及代码文件与逐行注释说明

以下文件已在**源码中逐行或逐段添加中文注释**，便于阅读与维护。此处仅列出路径与职责；完整带注释代码请直接查看对应源文件。

| 文件 | 职责 | 注释要点 |
|------|------|----------|
| `server_python/rag_config.py` | RAG 与知识库配置 | 每项配置含义、环境变量、K/阈值/模型名 |
| `server_python/vector_stores.py` | 向量检索 + 检索-过滤 | 类与方法的用途、Chroma 得分含义、过滤逻辑 |
| `server_python/rag.py` | 三阶段 RAG 链、仅基于参考生成 | 链结构、prompt 约束、历史会话 |
| `server_python/knowledge_base.py` | 知识库上传、分片、MD5 去重 | 分片策略、去重流程、Chroma 写入 |
| `server_python/tools/case_study_service.py` | Tool：query_drug_top_mirnas | 药物解析、MGCNA 加载、预测与结果结构、standalone 降级 |
| `server_python/main.py` | RAG/Case Study 路由与 Agent | `/api/rag/*`、`/api/chat/rag`、`/api/case-study/*`、`/api/chat/case-study` 及意图解析、Tool 调用、LLM 润色 |

---

## 六、附录：核心代码全文（已含逐行注释）

以下代码与当前仓库源码一致，**逐行/逐段注释已写入各源文件**；此处摘录便于在笔记中直接查阅。

### 6.1 `server_python/rag_config.py`

```python
# RAG 配置：知识库存储路径、Chroma 集合名、分片与检索参数
import os
from pathlib import Path

# DashScope API Key（RAG 嵌入与千问共用）
dashscope_api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALI_API_KEY") or ""

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
persist_directory = str(DATA_DIR / "chroma_db")   # Chroma 持久化目录
md5_file = DATA_DIR / "md5.txt"                   # MD5 去重记录
uploaded_list_file = DATA_DIR / "uploaded_files.json"

collection_name = "rag_knowledge"
chunk_size = 500
chunk_overlap = 50
max_split_char_number = 800
similarity_threshold = 4   # 检索 Top-K
retrieval_score_threshold = float(os.getenv("RAG_SCORE_THRESHOLD", "0")) or None  # 过滤阈值

chat_model_name = os.getenv("ALI_QWEN_MODEL", "qwen-turbo")
embedding_model = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-v3")
```

### 6.2 `server_python/vector_stores.py`

```python
# 向量存储服务：封装 Chroma，提供检索器与「检索+过滤」
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import Chroma
from rag_config import (
    collection_name, dashscope_api_key, embedding_model,
    persist_directory, retrieval_score_threshold, similarity_threshold,
)

class VectorStoreService:
    def __init__(self, embedding=None):
        self.embedding = embedding or DashScopeEmbeddings(model=embedding_model, dashscope_api_key=dashscope_api_key)
        self.vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=self.embedding,
            persist_directory=persist_directory,
        )

    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k": similarity_threshold})

    def retrieve_and_filter(self, query: str, k: int = None, score_threshold: float = None) -> list:
        """检索 Top-K → 按 score <= threshold 过滤，仅保留权威段落。Chroma 的 score 为距离，越小越相似。"""
        k = k or similarity_threshold
        threshold = score_threshold if score_threshold is not None else retrieval_score_threshold
        try:
            pairs = self.vector_store.similarity_search_with_score(query, k=k)
        except Exception:
            pairs = []
        if not threshold:
            return [doc for doc, _ in pairs]
        return [doc for doc, score in pairs if score <= threshold]
```

### 6.3 `server_python/rag.py`（三阶段链）

```python
# RAG 服务：检索 - 过滤 - 生成 三阶段，限制模型仅基于向量库检索到的权威文献作答
from operator import itemgetter
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.history import RunnableWithMessageHistory
from file_history_store import get_rag_history
from rag_config import chat_model_name, dashscope_api_key, embedding_model
from vector_stores import VectorStoreService

def _format_document(docs: list) -> str:
    """将检索到的文档格式化为供 LLM 阅读的字符串（序号+内容+来源）。"""
    if not docs:
        return "（暂无相关参考段落）"
    parts = []
    for i, doc in enumerate(docs, 1):
        content = doc.page_content if isinstance(doc, Document) else str(doc)
        source = getattr(doc, "metadata", {}) or {}
        source_name = source.get("source", "未知")
        parts.append(f"[{i}] {content}\n（来源：{source_name}）")
    return "\n\n".join(parts)

class RagService:
    def __init__(self):
        self.vector_service = VectorStoreService(
            embedding=DashScopeEmbeddings(model=embedding_model, dashscope_api_key=dashscope_api_key),
        )
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", "你是一个基于知识库的问答助手。请严格根据以下「参考段落」回答用户问题；若参考段落中未包含答案，请如实说明。不要编造内容。\n\n参考段落：\n{context}"),
            ("human", "{input}"),
            MessagesPlaceholder("history"),
        ])
        self.chat_model = ChatTongyi(model=chat_model_name, streaming=True, dashscope_api_key=dashscope_api_key)
        self.chain = self._get_chain()

    def _get_chain(self):
        def retrieve_filter_format(question: str) -> str:
            docs = self.vector_service.retrieve_and_filter(question)  # 阶段一检索 + 阶段二过滤
            return _format_document(docs)                             # 阶段三前：格式化
        chain = (
            {
                "context": itemgetter("input") | retrieve_filter_format,
                "input": itemgetter("input"),
                "history": itemgetter("history"),
            }
            | self.prompt_template
            | self.chat_model
            | StrOutputParser()
        )
        return RunnableWithMessageHistory(
            chain, get_rag_history,
            input_messages_key="input", history_messages_key="history",
        )

    def invoke(self, question: str, session_id: str, config=None):
        cfg = config or {}
        if "configurable" not in cfg: cfg["configurable"] = {}
        cfg["configurable"]["session_id"] = session_id
        return self.chain.invoke({"input": question}, config=cfg)

    def stream(self, question: str, session_id: str, config=None):
        cfg = config or {}
        if "configurable" not in cfg: cfg["configurable"] = {}
        cfg["configurable"]["session_id"] = session_id
        return self.chain.stream({"input": question}, config=cfg)
```

### 6.4 `server_python/knowledge_base.py`（入库与去重）

```python
# 知识库服务：上传文本、MD5 去重、分片、写入向量库
import hashlib, os
from datetime import datetime
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rag_config import chunk_overlap, chunk_size, collection_name, dashscope_api_key, embedding_model, max_split_char_number, persist_directory, md5_file

def get_string_md5(data: str) -> str:
    return hashlib.md5(data.encode("utf-8")).hexdigest()

def save_md5(md5_hex: str) -> None:
    md5_file.parent.mkdir(parents=True, exist_ok=True)
    with open(md5_file, "a", encoding="utf-8") as f:
        f.write(md5_hex + "\n")

def check_md5(md5_hex: str) -> bool:
    if not md5_file.exists(): return False
    with open(md5_file, "r", encoding="utf-8") as f:
        existing = {line.strip() for line in f if line.strip()}
    return md5_hex in existing

class KnowledgeBaseService:
    def __init__(self):
        os.makedirs(persist_directory, exist_ok=True)
        self._embedding = DashScopeEmbeddings(model=embedding_model, dashscope_api_key=dashscope_api_key)
        self.chroma = Chroma(collection_name=collection_name, embedding_function=self._embedding, persist_directory=persist_directory)
        self.spliter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""], length_function=len)

    def upload_by_str(self, data: str, filename: str) -> str:
        md5hex = get_string_md5(data)
        if check_md5(md5hex):
            return "[跳过]内容已存在（MD5 重复），未重复写入"
        if len(data) > max_split_char_number:
            knowledge_chunks = self.spliter.split_text(data)
        else:
            knowledge_chunks = [data]
        metadata = {"source": filename, "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "operator": "fy"}
        meta_list = [metadata for _ in knowledge_chunks]
        self.chroma.add_texts(knowledge_chunks, metadatas=meta_list)
        save_md5(md5hex)
        return "[成功]内容已加载到向量库中"
```

### 6.5 `server_python/tools/case_study_service.py`（Tool 接口）

- **职责**：`query_drug_top_mirnas(drug, top_n)` 查询某药物 Top-N 关联 miRNA；内部 `_load_case_study_predictor` 加载 MGCNA，`_run_predict_all_pairs` 做预测并排序；若依赖不可用则走 `query_drug_top_mirnas_standalone` 返回未就绪提示。
- **逐行注释**：已写入源文件 `server_python/tools/case_study_service.py`（含 `_resolve_drug_id`、`_load_case_study_predictor`、`_run_predict_all_pairs`、`query_drug_top_mirnas`、`query_drug_top_mirnas_standalone`）。

### 6.6 `server_python/main.py`（RAG 与 Case Study 路由）

- **RAG**：`get_kb_service` / `get_rag_service` 单例；`POST /api/rag/upload` 上传并入库；`POST /api/chat/rag` 取最后一条 user 消息 → `rag.stream`/`invoke`（三阶段），流式或非流式返回。注释已写在对应函数与关键行。
- **Case Study**：`POST /api/case-study/drug-top-mirnas` 直接调用 `query_drug_top_mirnas` 返回 JSON；`POST /api/chat/case-study` 规则提取 drug/top_n → 调用 Tool → `_build_tool_result_text` 格式化 → 千问系统提示 + user 消息 → 流式/非流式返回。注释已写在对应函数与意图解析、Tool 调用、LLM 润色处。
