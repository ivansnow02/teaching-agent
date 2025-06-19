import logging

from langchain_mcp_adapters.client import MultiServerMCPClient


async def get_rag_tools(user_id: str = None):
    """
    获取 RAG 工具
    """
    logging.info(f"Retrieving RAG tools for user_id: {user_id}")

    rag_client = MultiServerMCPClient(
        {
            "rag": {
                "command"  : "uv",
                "args"     : ["run", "src/agent/mcp/rag_tools.py", "--user-id", f"{user_id}"],
                "transport": "stdio"
            }
        }
    )

    return await rag_client.get_tools()


def count_words(text: str) -> int:
    """
    计算文本中的字数
    :param text: 输入文本
    :return: 字数
    """
    if not text:
        return 0
    return len(text.split())


def calculate_time(word_count: int, words_per_minute: int = 200) -> int:
    """
    根据字数计算所需时间（分钟）
    :param word_count: 字数
    :param words_per_minute: 每分钟阅读的字数，默认为200
    :return: 所需时间（分钟）
    """
    if word_count <= 0 or words_per_minute <= 0:
        return 0
    return max(1, word_count // words_per_minute)
