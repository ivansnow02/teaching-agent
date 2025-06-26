import os
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent

from src.agent.tools import search, get_math_tool

llm = init_chat_model(
    model="qwen3-235b-a22b",
    model_provider="openai",
    temperature=0,
    extra_body={"enable_thinking": False},
    api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
    base_url=os.getenv(
        "DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
)


def build_math_agent():
    """
    Build a math agent using LangGraph.
    """

    math_tool = get_math_tool(
        init_chat_model(
            model="qwen2.5-coder-32b-instruct",
            model_provider="openai",
            temperature=0,
            # extra_body={"enable_thinking": False},
            api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
            base_url=os.getenv(
                "DASH_SCOPE_API_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
        )
    )
    graph = create_react_agent(
        model=llm,
        name="math_agent",
        prompt="你是一个数学专家，擅长解决各种数学问题。请根据用户的提问提供准确的解答。",
        tools=[search, math_tool],
    )
    return graph
