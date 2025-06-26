import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.agent import rag_agent


async def get_rag_tools(course_id: str = None):
    """
    获取 RAG 工具
    """
    logging.info(f"Retrieving RAG tools for user_id: {course_id}")

    rag_client = MultiServerMCPClient(
        {
            "rag": {
                "command": "uv",
                "args": [
                    "run",
                    "src/agent/mcp/rag_tools.py",
                    "--course-id",
                    f"{course_id}",
                ],
                "transport": "stdio",
            }
        }
    )

    return await rag_client.get_tools()


@tool
async def count_words(text: str) -> int:
    """
    计算文本中的字数
    :param text: 输入文本
    :return: 字数
    """
    if not text:
        return 0
    return len(text.split())


@tool
async def calculate_time(word_count: int, words_per_minute: int = 200) -> int:
    """
    根据字数计算所需时间（分钟）
    :param word_count: 字数
    :param words_per_minute: 每分钟阅读的字数，默认为200
    :return: 所需时间（分钟）
    """
    if word_count <= 0 or words_per_minute <= 0:
        return 0
    return max(1, word_count // words_per_minute)


@tool
async def rag_tool(question: str, config: RunnableConfig) -> str:
    """
    RAG 工具，用于回答问题
    :param question: 用户提问
    :param config: 配置参数
    :return: 回答内容
    """
    rag_graph = await rag_agent.make_graph()
    response = await rag_graph.ainvoke(
        {
            "messages": [{"role": "user", "content": question}],
            "max_rewrite": 3,
            "rewrite_count": 0,
        },
        config,
    )
    return response["messages"][-1].content
