import os
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from src.agent.tools import search


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
        prompt="你是一个代码专家，擅长解决各种编程问题。",
        tools=[search],
    )
    return graph


def build_code_generator():
    """
    Build a code generator agent using LangGraph.
    """
    agent = create_react_agent(
        model=code_llm,
        name="code_generator",
        prompt="你是一个代码生成专家，擅长根据用户需求编写高质量代码。请根据用户的描述生成完整、可运行的代码，并只返回代码本身，不需要解释。",
        tools=[search],
    )
    return agent


def build_code_validator():
    """
    Build a code validator agent using LangGraph.
    """
    agent = create_react_agent(
        model=code_llm,
        name="code_validator",
        prompt="你是一个代码验证专家，擅长检查和验证代码的正确性。请根据用户提供的代码，判断其是否有错误，并指出具体问题或改进建议，只返回验证结果。",
        tools=[search],
    )
    return agent
