# 向量存储服务：封装 Chroma，提供检索器与「检索+过滤」，支撑三阶段中的检索与过滤
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from rag_config import (
    collection_name,
    dashscope_api_key,
    embedding_model,
    persist_directory,
    retrieval_score_threshold,
    similarity_threshold,
)


class VectorStoreService:
    """向量库服务：初始化 Chroma + 嵌入模型，提供检索与「检索+按得分过滤」接口。"""

    def __init__(self, embedding=None):
        # 未传入则使用 DashScope 默认嵌入模型，用于 query 与文档的向量化
        self.embedding = embedding or DashScopeEmbeddings(model=embedding_model, dashscope_api_key=dashscope_api_key)
        # Chroma 实例：指定集合名、嵌入函数、持久化目录
        self.vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=self.embedding,
            persist_directory=persist_directory,
        )

    def get_retriever(self):
        """返回 LangChain 检索器，供 RAG chain 使用；k 为相似度 Top-K，由 similarity_threshold 决定。"""
        return self.vector_store.as_retriever(search_kwargs={"k": similarity_threshold})

    def retrieve_and_filter(self, query: str, k: int = None, score_threshold: float = None) -> list:
        """
        检索 - 过滤：先按相似度取 Top-K，再按得分阈值过滤，仅保留权威/相关段落。
        Chroma 返回的 score 为距离（越小越相似），保留 score <= score_threshold 的文档；
        score_threshold 为 0 或 None 时不过滤，仅做 Top-K。
        """
        # 未传 k 时使用全局配置的 Top-K
        k = k or similarity_threshold
        # 未传 score_threshold 时使用全局配置；传了则优先用传入值
        threshold = score_threshold if score_threshold is not None else retrieval_score_threshold
        try:
            # 返回 (Document, score) 列表；Chroma 的 score 多为 L2 距离
            pairs = self.vector_store.similarity_search_with_score(query, k=k)
        except Exception:
            pairs = []
        # 未设置阈值时直接返回 Top-K 全部文档，不做过滤
        if not threshold:
            return [doc for doc, _ in pairs]
        # 仅保留距离小于等于阈值的文档，作为「权威文献」送入生成阶段
        return [doc for doc, score in pairs if score <= threshold]
