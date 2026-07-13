"""
MCP integration — the ONLY place that talks to your MCP servers.

Uses langchain-mcp-adapters to turn each MCP server's tools into LangChain
tools that create_react_agent can call. Agents then fetch everything (Kusto,
IcM, containers, ...) purely through these tools.
"""

from langchain_mcp_adapters.client import MultiServerMCPClient
from settings import load_mcp_config

_client: MultiServerMCPClient | None = None


def get_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        _client = MultiServerMCPClient(load_mcp_config())
    return _client 


async def load_tools_by_server() -> dict[str, list]:
    """Return {server_name: [LangChain tools]} for every configured MCP server."""
    client = get_client()
    config = load_mcp_config()
    tools_by_server: dict[str, list] = {}
    for server_name in config:
        try:
            tools_by_server[server_name] = await client.get_tools(server_name=server_name)
            names = [t.name for t in tools_by_server[server_name]]
            print(f"🔌 MCP '{server_name}': loaded {len(names)} tools -> {names}")
        except Exception as e:
            print(f"⚠️  MCP '{server_name}' failed to load: {e}")
            tools_by_server[server_name] = []
    return tools_by_server


_all_tools: list | None = None


async def load_all_tools() -> list:
    """Flat list of every MCP tool across all servers (cached)."""
    global _all_tools
    if _all_tools is None:
        by_server = await load_tools_by_server()
        _all_tools = [t for tools in by_server.values() for t in tools]
    return _all_tools


async def get_tool(name: str):
    """Look up a single MCP tool by name (used by the execute phase)."""
    for t in await load_all_tools():
        if t.name == name:
            return t
    available = [t.name for t in await load_all_tools()]
    raise KeyError(f"MCP tool '{name}' not found. Available: {available}")


async def call_tool(name: str, args: dict):
    """Invoke an MCP tool by name and return its result."""
    tool = await get_tool(name)
    return await tool.ainvoke(args)
