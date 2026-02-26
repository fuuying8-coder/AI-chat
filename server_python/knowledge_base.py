# 知识库服务：上传文本、MD5 去重、分片、写入向量库（支撑 RAG 检索-过滤-生成的数据来源）
import hashlib
import os
from datetime import datetime

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_config import (
    chunk_overlap,
    chunk_size,
    collection_name,
    dashscope_api_key,
    embedding_model,
    max_split_char_number,
    persist_directory,
    md5_file,
)


def get_string_md5(data: str) -> str:
    """计算字符串的 MD5 十六进制值，用于内容去重。"""
    return hashlib.md5(data.encode("utf-8")).hexdigest()


def save_md5(md5_hex: str) -> None:
    """将 MD5 追加写入 md5.txt，一行一个，后续 check_md5 可据此判断是否已入库。"""
    md5_file.parent.mkdir(parents=True, exist_ok=True)
    with open(md5_file, "a", encoding="utf-8") as f:
        f.write(md5_hex + "\n")


def check_md5(md5_hex: str) -> bool:
    """检查 md5 是否已存在于 md5.txt 中；存在则视为重复，不再写入向量库。"""
    if not md5_file.exists():
        return False
    with open(md5_file, "r", encoding="utf-8") as f:
        existing = {line.strip() for line in f if line.strip()}
    return md5_hex in existing


class KnowledgeBaseService:
    """知识库入库：分片、向量化、按 MD5 去重，写入 Chroma。"""

    def __init__(self):
        os.makedirs(persist_directory, exist_ok=True)
        self._embedding = DashScopeEmbeddings(model=embedding_model, dashscope_api_key=dashscope_api_key)
        self.chroma = Chroma(
            collection_name=collection_name,
            embedding_function=self._embedding,
            persist_directory=persist_directory,
        )
        # 按字符数分片，优先按段落/句号等切分，减少断句
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
            length_function=len,
        )

    def upload_by_str(self, data: str, filename: str) -> str:
        """将传入的字符串分片向量化，存入向量库；按 MD5 去重，重复则跳过。"""
        md5hex = get_string_md5(data)
        if check_md5(md5hex):
            return "[跳过]内容已存在（MD5 重复），未重复写入"

        # 超过阈值则分片，否则整段作为一块
        if len(data) > max_split_char_number:
            knowledge_chunks = self.spliter.split_text(data)
        else:
            knowledge_chunks = [data]

        metadata = {
            "source": filename,
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator": "fy",
        }
        meta_list = [metadata for _ in knowledge_chunks]

        self.chroma.add_texts(knowledge_chunks, metadatas=meta_list)
        save_md5(md5hex)
        return "[成功]内容已加载到向量库中"
