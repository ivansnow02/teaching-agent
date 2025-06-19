import argparse
import os

import httpx
from mcp.server.fastmcp import FastMCP

# ---
# 全局变量来存储 RAG URL 和 Authorization Token
# 默认值
RAG_URL = "http://localhost:9621"
USER_ID: str = ""
# ---

mcp = FastMCP("Light RAG Graph", "0.1.0")


async def get_graph_labels() -> list[str]:
    """
    获取所有知识图谱标签

    Returns:
        List[str]: 标签列表
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{RAG_URL}/api/graph/label/list/{USER_ID}")
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def graph_label_list() -> list[str]:
    """
    获取知识图谱所有标签
    Returns:
        List[str]: 标签列表
    """
    return await get_graph_labels()


async def get_knowledge_graph(label: str = "", max_depth: int = 3, max_nodes: int = 1000) -> dict:
    """
    获取指定标签的知识子图

    Args:
        label (str): 起始节点标签
        max_depth (int): 最大深度
        max_nodes (int): 最大节点数

    Returns:
        Dict[str, List[str]]: 子图
    """
    params = {
        "label"    : label,
        "max_depth": max_depth,
        "max_nodes": max_nodes
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{RAG_URL}/api/graphs/{USER_ID}", params=params)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def get_graph(label: str = "", max_depth: int = 3, max_nodes: int = 1000) -> dict:
    """
    获取知识图谱子图

    Args:
        label (str): 起始节点标签
        max_depth (int): 最大深度
        max_nodes (int): 最大节点数

    Returns:
        dict: 子图
    """
    return await get_knowledge_graph(USER_ID, label, max_depth, max_nodes)


async def check_entity_exists(name: str = "") -> dict:
    """
    检查实体是否存在

    Args:
        name (str): 实体名

    Returns:
        Dict[str, bool]: {'exists': bool}
    """
    params = {"name": name}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{RAG_URL}/api/graph/entity/exists/{USER_ID}", params=params)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def entity_exists(name: str = "") -> dict:
    """
    检查知识识图谱中实体是否存在

    Args:
        name (str): 实体名

    Returns:
        dict: {'exists': bool}
    """
    return await check_entity_exists(USER_ID, name)


async def update_entity(data: dict = {}) -> dict:
    """
    更新实体属性

    Args:
        data (dict): 实体更新请求体

    Returns:
        dict: 更新后的实体信息
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{RAG_URL}/api/graph/entity/edit/{USER_ID}", json=data)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def entity_edit(request: dict = {}) -> dict:
    """
    更新知识图谱实体属性

    Args:
        request (dict): 实体更新请求体

    Returns:
        dict: 更新后的实体信息
    """
    return await update_entity(USER_ID, request)


async def update_relation(data: dict = {}) -> dict:
    """
    更新关系属性

    Args:
        data (dict): 关系更新请求体

    Returns:
        dict: 更新后的关系信息
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{RAG_URL}/api/graph/relation/edit/{USER_ID}", json=data)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def relation_edit(request: dict = {}) -> dict:
    """
    更新知识图谱关系属性

    Args:
        request (dict): 关系更新请求体

    Returns:
        dict: 更新后的关系信息
    """
    return await update_relation(USER_ID, request)


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
        help="URL of the RAG service. Defaults to http://localhost:9621 if not set. Can also be set via RAG_URL environment variable."
    )

    args = parser.parse_args()

    # ---
    # 在这里设置全局变量
    # 优先使用命令行参数，其次是环境变量，最后是硬编码的默认值
    if args.rag_url:
        RAG_URL = args.rag_url
    else:
        RAG_URL = os.environ.get("RAG_URL", "http://localhost:9621")

    mcp.run(transport='stdio')
