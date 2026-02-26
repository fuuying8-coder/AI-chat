# RAG 配置：知识库存储路径、Chroma 集合名、分片与检索参数
import os
from pathlib import Path

# DashScope API Key（RAG 嵌入与千问共用）：优先 DASHSCOPE_API_KEY，否则 ALI_API_KEY
dashscope_api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALI_API_KEY") or ""

# 知识库与向量库存储目录（server_python/data）
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
persist_directory = str(DATA_DIR / "chroma_db")
md5_file = DATA_DIR / "md5.txt"
# 已上传文档列表（供前端展示）
uploaded_list_file = DATA_DIR / "uploaded_files.json"

collection_name = "rag_knowledge"
chunk_size = 500
chunk_overlap = 50
# 超过此字符数则分片
max_split_char_number = 800
# 检索返回的相似段落数量 K
similarity_threshold = 4

# 通义千问聊天模型名（RAG 生成用）
chat_model_name = os.getenv("ALI_QWEN_MODEL", "qwen-turbo")
# 向量化模型（DashScope text-embedding-v3 / text-embedding-v4）
embedding_model = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-v3")
