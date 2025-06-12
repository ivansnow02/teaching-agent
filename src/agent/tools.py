import logging

from langchain_mcp_adapters.client import MultiServerMCPClient

rag_client = MultiServerMCPClient(
    {
        "rag": {
            "command": "uv",
            "args": ["run", "src/agent/mcp/rag_tools.py"],
            "transport": "stdio"
        }
    }
)

async def get_rag_tools():
    """
    获取 RAG 工具
    """
    logging.info("Fetching RAG tools from MCP client")
    return await rag_client.get_tools()