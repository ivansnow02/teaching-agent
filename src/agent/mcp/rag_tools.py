import argparse
import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP

from typing import Literal, Optional
from pydantic import BaseModel

# ---
# 全局变量来存储 RAG URL 和 Authorization Token
# 默认值
RAG_URL = "http://localhost:9621/api"
COURSE_ID: str = ""
# ---

mcp = FastMCP("Light RAG", "0.1.0")


class QueryParams(BaseModel):
    query: str
    mode: Literal["local", "global", "hybrid", "naive", "mix", "bypass"] = "global"
    only_need_context: bool = False
    only_need_prompt: bool = False
    response_type: str = "Multiple Paragraphs"
    top_k: int = 10
    max_token_for_text_unit: int = 4000
    max_token_for_global_context: int = 4000
    max_token_for_local_context: int = 4000


async def query_knowledge_base(params: QueryParams) -> str:
    """
    更灵活的知识库查询工具，支持多种检索模式和自定义参数。
    """
    body = params.model_dump()
    query = body.pop("query")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{RAG_URL}/query/{COURSE_ID}", json=body | {"query": query}
            )
            response.raise_for_status()
            return response.text
    except Exception as e:
        logging.error(f"RAG 查询失败: {e}")
        raise


# 用法示例
# params = QueryParams(query="什么是向量检索？", mode="mix", only_need_context=True)
# await query_knowledge_base(params)
@mcp.tool(
    name="rag_tool",
    description="""
查询知识库的工具，支持多种检索模式和自定义参数。
参数：
- query: 查询内容
- mode: 检索模式，支持 local、global、hybrid、naive、mix 和 bypass，local 模式专注于上下文相关的检索，global模式则关注全局知识的检索，hybrid 模式结合了local和global，naive使用简单的向量检索，mix 混合graph和向量检索。
- only_need_context: 仅返回上下文信息
- only_need_prompt: 仅返回提示词信息
- response_type: 返回的响应类型，支持 Multiple Paragraphs、Single Paragraph、Bullet Points
- top_k: 返回结果的数量
""",
)
async def query_rag_tool(
    query: str,
    mode: Literal["local", "global", "hybrid", "naive", "mix", "bypass"] = "mix",
    only_need_context: bool = False,
    only_need_prompt: bool = False,
    response_type: str = "Multiple Paragraphs",
    top_k: int = 10,
) -> str:
    params = QueryParams(
        query=query,
        mode=mode,
        only_need_context=only_need_context,
        only_need_prompt=only_need_prompt,
        response_type=response_type,
        top_k=top_k,
    )
    return await query_knowledge_base(params)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Light RAG MCP server.")
    parser.add_argument(
        "--course-id", type=str, default=None, help="Course id for the RAG service."
    )
    parser.add_argument(
        "--rag-url",
        type=str,
        default=None,  # 将默认值改为 None，以便优先使用环境变量或命令行参数
        help="URL of the RAG service. Defaults to http://localhost:9621/api if not set. Can also be set via RAG_URL environment variable.",
    )

    args = parser.parse_args()

    # ---
    # 在这里设置全局变量
    # 优先使用命令行参数，其次是环境变量，最后是硬编码的默认值
    if args.rag_url:
        RAG_URL = args.rag_url
    else:
        RAG_URL = os.environ.get("RAG_URL", "http://localhost:9621/api")

    if args.course_id:
        COURSE_ID = args.course_id
    else:
        logging.error(
            "COURSE ID must be provided either as a command line argument or through the COURSE_ID environment variable."
        )

    mcp.run(transport="stdio")
