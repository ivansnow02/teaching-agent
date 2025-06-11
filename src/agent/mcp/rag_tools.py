from typing import Literal

import httpx
import asyncio
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, field_validator
from starlette.applications import Starlette
from starlette.routing import Mount

mcp = FastMCP("Light RAG", "0.1.0")

RAG_URL = "http://localhost:9621"

# {"mode":"global","response_type":"Multiple Paragraphs","top_k":10,"max_token_for_text_unit":4000,"max_token_for_global_context":4000,"max_token_for_local_context":4000,"only_need_context":false,"only_need_prompt":false,"stream":true,"history_turns":3,"hl_keywords":[],"ll_keywords":[],"user_prompt":"","query":"大概讲了什么"}
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
            response = await client.post(f"{RAG_URL}/query", json=body)
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
    # Initialize and run the server
    mcp.run(transport='stdio')