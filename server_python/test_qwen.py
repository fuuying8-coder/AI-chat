from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

llm = ChatOpenAI(
    model="qwen-max",
    api_key="sk-4a33dceeb78a4a98a25f1945010b76c3",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

resp = llm.invoke([
    HumanMessage(content="用一句话解释什么是大模型")
])

print(resp.content)
