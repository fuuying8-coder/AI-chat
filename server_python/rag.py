# RAG 服务：检索 - 过滤 - 生成 三阶段，限制模型仅基于向量库检索到的权威文献作答
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
    """将检索到的文档列表格式化为供 LLM 阅读的字符串：带序号、内容、来源。"""
    if not docs:
        return "（暂无相关参考段落）"
    parts = []
    for i, doc in enumerate(docs, 1):
        # 兼容 LangChain Document 或普通对象
        content = doc.page_content if isinstance(doc, Document) else str(doc)
        source = getattr(doc, "metadata", {}) or {}
        source_name = source.get("source", "未知")
        parts.append(f"[{i}] {content}\n（来源：{source_name}）")
    return "\n\n".join(parts)


class RagService:
    """RAG 服务：三阶段链（检索→过滤→格式化→生成），并带对话历史。"""

    def __init__(self):
        # 向量服务：负责检索与按得分过滤
        self.vector_service = VectorStoreService(
            embedding=DashScopeEmbeddings(model=embedding_model, dashscope_api_key=dashscope_api_key),
        )
        # 系统提示中注入 {context}，约束模型仅根据参考段落作答、不编造
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
        # 通义千问，流式输出
        self.chat_model = ChatTongyi(model=chat_model_name, streaming=True, dashscope_api_key=dashscope_api_key)
        self.chain = self._get_chain()

    def _get_chain(self):
        """构建 RAG 链：input → 检索+过滤+格式化 → context，再与 input、history 一起进 prompt → 千问 → 文本。"""
        def format_docs(docs):
            return _format_document(docs)

        def retrieve_filter_format(question: str) -> str:
            # 阶段一：检索（Top-K）；阶段二：按得分过滤；阶段三：格式化为字符串
            docs = self.vector_service.retrieve_and_filter(question)
            return format_docs(docs)

        # 输入为 dict：input（用户问题）、history（对话历史由 RunnableWithMessageHistory 注入）
        chain = (
            {
                "context": itemgetter("input") | retrieve_filter_format,  # 从 input 得到 question，执行检索-过滤-格式化
                "input": itemgetter("input"),
                "history": itemgetter("history"),
            }
            | self.prompt_template
            | self.chat_model
            | StrOutputParser()
        )
        # 按 session_id 维护多轮对话历史，供 prompt 中的 MessagesPlaceholder 使用
        conversation_chain = RunnableWithMessageHistory(
            chain,
            get_rag_history,
            input_messages_key="input",
            history_messages_key="history",
        )
        return conversation_chain

    def invoke(self, question: str, session_id: str, config=None):
        """同步调用 RAG；config 中需含 configurable.session_id，用于取/存历史。"""
        cfg = config or {}
        if "configurable" not in cfg:
            cfg["configurable"] = {}
        cfg["configurable"]["session_id"] = session_id
        return self.chain.invoke({"input": question}, config=cfg)

    def stream(self, question: str, session_id: str, config=None):
        """流式调用 RAG，逐 chunk 返回生成内容。"""
        cfg = config or {}
        if "configurable" not in cfg:
            cfg["configurable"] = {}
        cfg["configurable"]["session_id"] = session_id
        return self.chain.stream({"input": question}, config=cfg)
