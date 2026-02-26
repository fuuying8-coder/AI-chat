# RAG 对话历史存储：供 RunnableWithMessageHistory 使用（按 session_id 存内存）
from typing import Dict, List

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage

# session_id -> 消息列表（内存存储，重启清空；可改为 Redis/数据库）
_store: Dict[str, List[BaseMessage]] = {}


class InMemoryChatHistory(BaseChatMessageHistory):
    def __init__(self, session_id: str):
        self.session_id = session_id
        if session_id not in _store:
            _store[session_id] = []
        self.messages_list = _store[session_id]

    @property
    def messages(self) -> List[BaseMessage]:
        return self.messages_list

    def add_message(self, message: BaseMessage) -> None:
        self.messages_list.append(message)

    def clear(self) -> None:
        self.messages_list.clear()


def get_rag_history(session_id: str) -> BaseChatMessageHistory:
    return InMemoryChatHistory(session_id)
