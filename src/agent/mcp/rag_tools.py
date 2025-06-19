import argparse
import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP

# ---
# 全局变量来存储 RAG URL 和 Authorization Token
# 默认值
RAG_URL = "http://localhost:9621/api"
USER_ID: str = ""
# ---

mcp = FastMCP("Light RAG", "0.1.0")

async def query_knowledge_base(query: str, search_mode: str = "mix") -> str:
    """Query the RAG knowledge base to retrieve relevant information.

    Args:
        query: The question or query to search for
        search_mode: Search mode - "default", "naive", "local", "global", "hybrid", "mix"
            - "local": Focuses on context-dependent information.
            - "global": Utilizes global knowledge.
            - "hybrid": Combines local and global retrieval methods.
            - "naive": Performs a basic search without advanced techniques.
            - "mix": Integrates knowledge graph and vector retrieval.

    Returns:
        Answer based on the knowledge base
    """
    body = {
        "mode": search_mode,
        "query": query,
        "stream": False,
        "response_type": "Multiple Paragraphs",
        "top_k": 10,
        "max_token_for_text_unit": 4000,
        "max_token_for_global_context": 4000,
        "max_token_for_local_context": 4000,
        "only_need_context": False,
        "only_need_prompt": False,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 将 headers 传递给 httpx 请求
            response = await client.post(f"{RAG_URL}/query/{USER_ID}", json=body)
            response.raise_for_status()
            return response.text
    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e.response.status_code} {e.response.text}")
        raise
    except httpx.ReadTimeout:
        print("Request timed out. Please check if the RAG service is running and responsive.")
        raise


@mcp.tool()
async def query_mix_retrieval(query: str) -> str:
    """
    查询知识库 (混合检索模式)

    使用混合检索模式查询知识库，整合知识图谱和向量检索技术，获取最全面的结果。

    Args:
        query (str): 要查询的问题或关键词

    Returns:
        str: 知识库中的答案
    """
    return await query_knowledge_base(query, "mix")


@mcp.tool()
async def query_local_retrieval(query: str) -> str:
    """
    查询知识库 (本地检索模式)

    使用本地检索模式查询知识库，专注于检索上下文相关的信息。

    Args:
        query (str): 要查询的问题或关键词

    Returns:
        str: 知识库中的答案
    """
    return await query_knowledge_base(query, "local")


@mcp.tool()
async def query_global_retrieval(query: str) -> str:
    """
    查询知识库 (全局检索模式)

    使用全局检索模式查询知识库，利用全局知识进行检索。

    Args:
        query (str): 要查询的问题或关键词

    Returns:
        str: 知识库中的答案
    """
    return await query_knowledge_base(query, "global")


@mcp.tool()
async def query_hybrid_retrieval(query: str) -> str:
    """
    查询知识库 (混合本地和全局检索模式)

    使用混合检索模式查询知识库，结合本地和全局检索方法获取更全面的结果。

    Args:
        query (str): 要查询的问题或关键词

    Returns:
        str: 知识库中的答案
    """
    return await query_knowledge_base(query, "hybrid")


@mcp.tool()
async def query_naive_retrieval(query: str) -> str:
    """
    查询知识库 (简单检索模式)

    使用简单检索模式查询知识库，执行基础搜索而不使用高级技术。

    Args:
        query (str): 要查询的问题或关键词

    Returns:
        str: 知识库中的答案
    """
    return await query_knowledge_base(query, "naive")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Light RAG MCP server.")
    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="User id for the RAG service."
    )
    parser.add_argument(
        "--rag-url",
        type=str,
        default=None,  # 将默认值改为 None，以便优先使用环境变量或命令行参数
        help="URL of the RAG service. Defaults to http://localhost:9621/api if not set. Can also be set via RAG_URL environment variable."
    )

    args = parser.parse_args()

    # ---
    # 在这里设置全局变量
    # 优先使用命令行参数，其次是环境变量，最后是硬编码的默认值
    if args.rag_url:
        RAG_URL = args.rag_url
    else:
        RAG_URL = os.environ.get("RAG_URL", "http://localhost:9621/api")

    if args.user_id:
        USER_ID = args.user_id
    else:
        logging.error(
            "User ID must be provided either as a command line argument or through the USER_ID environment variable.")

    mcp.run(transport='stdio')