# RAG 服务：检索 + 基于知识库的生成
from operator import itemgetter

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.output_parsers import StrOutputParser

from file_history_store import get_rag_history
from rag_config import chat_model_name, dashscope_api_key, embedding_model
from vector_stores import VectorStoreService


def _format_document(docs: list) -> str:
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
        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个基于知识库的问答助手。请严格根据以下「参考段落」回答用户问题；若参考段落中未包含答案，请如实说明。不要编造内容。\n\n参考段落：\n{context}",
                ),
                ("human", "{input}"),
                MessagesPlaceholder("history"),
            ]
        )
        self.chat_model = ChatTongyi(model=chat_model_name, streaming=True, dashscope_api_key=dashscope_api_key)
        self.chain = self._get_chain()

    def _get_chain(self):
        retriever = self.vector_service.get_retriever()

        def format_docs(docs):
            return _format_document(docs)

        chain = (
            {
                "context": itemgetter("input") | retriever | format_docs,
                "input": itemgetter("input"),
                "history": itemgetter("history"),
            }
            | self.prompt_template
            | self.chat_model
            | StrOutputParser()
        )
        conversation_chain = RunnableWithMessageHistory(
            chain,
            get_rag_history,
            input_messages_key="input",
            history_messages_key="history",
        )
        return conversation_chain

    def invoke(self, question: str, session_id: str, config=None):
        """同步调用 RAG；config 中需含 configurable.session_id。"""
        cfg = config or {}
        if "configurable" not in cfg:
            cfg["configurable"] = {}
        cfg["configurable"]["session_id"] = session_id
        return self.chain.invoke({"input": question}, config=cfg)

    def stream(self, question: str, session_id: str, config=None):
        """流式调用 RAG。"""
        cfg = config or {}
        if "configurable" not in cfg:
            cfg["configurable"] = {}
        cfg["configurable"]["session_id"] = session_id
        return self.chain.stream({"input": question}, config=cfg)
