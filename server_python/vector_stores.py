# 向量存储服务：封装 Chroma，提供检索器
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import Chroma

from rag_config import collection_name, dashscope_api_key, embedding_model, persist_directory, similarity_threshold


class VectorStoreService:
    def __init__(self, embedding=None):
        self.embedding = embedding or DashScopeEmbeddings(model=embedding_model, dashscope_api_key=dashscope_api_key)
        self.vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=self.embedding,
            persist_directory=persist_directory,
        )

    def get_retriever(self):
        """返回向量检索器，供 RAG chain 使用；k 为相似度 Top-K。"""
        return self.vector_store.as_retriever(search_kwargs={"k": similarity_threshold})
