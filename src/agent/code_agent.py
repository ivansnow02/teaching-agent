import os
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from src.agent.tools import get_math_tool, search


code_llm = init_chat_model(
    model="qwen2.5-coder-32b-instruct",
    model_provider="openai",
    temperature=0,
    # extra_body={"enable_thinking": False},
    api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
    base_url=os.getenv(
        "DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
)


def build_code_agent():
    """
    Build a code agent using LangGraph.
    """

    graph = create_react_agent(
        model=code_llm,
        name="code_agent",
        prompt="你是一个代码专家，擅长解决各种编程问题。请根据用户的提供的代码生成运行结果。只需要返回代码运行结果，不需要解释或其他内容。",
        tools=[search],
    )
    return graph
