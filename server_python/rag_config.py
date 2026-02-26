# RAG 配置：知识库存储路径、Chroma 集合名、分片与检索参数
import os
from pathlib import Path

# DashScope API Key（RAG 嵌入与千问共用）：优先 DASHSCOPE_API_KEY，否则 ALI_API_KEY，用于向量化与生成
dashscope_api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALI_API_KEY") or ""

# 知识库与向量库存储目录（server_python/data）
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
# Chroma 持久化目录，向量库落盘路径
persist_directory = str(DATA_DIR / "chroma_db")
# 已上传文档内容的 MD5 记录文件，用于去重（一行一个 MD5）
md5_file = DATA_DIR / "md5.txt"
# 已上传文档列表（供前端展示），JSON 数组，项含 filename、uploaded_at、message
uploaded_list_file = DATA_DIR / "uploaded_files.json"

# Chroma 集合名称，同一项目内与 knowledge_base 共用
collection_name = "rag_knowledge"
# 分片时每块目标字符数（与 chunk_overlap 配合控制重叠）
chunk_size = 500
# 相邻分片重叠字符数，避免句意被截断
chunk_overlap = 50
# 超过此字符数则进行分片，否则整段作为一块
max_split_char_number = 800
# 检索阶段 Top-K：从向量库取相似度最高的 K 个段落
similarity_threshold = 4
# 过滤阶段阈值：仅保留 score <= 此值的段落（Chroma 返回 L2 距离，越小越相似）；0 或 None 表示不过滤，仅做 Top-K
retrieval_score_threshold = float(os.getenv("RAG_SCORE_THRESHOLD", "0")) or None

# 通义千问聊天模型名（RAG 生成阶段使用）
chat_model_name = os.getenv("ALI_QWEN_MODEL", "qwen-turbo")
# 向量化模型（DashScope text-embedding-v3 / text-embedding-v4），用于入库与检索时的 query 嵌入
embedding_model = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-v3")
