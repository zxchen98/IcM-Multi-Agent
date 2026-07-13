"""
hello_mcp.py — a minimal MCP server to learn the moving parts.

Run it:
    pip install "mcp[cli]"
    # inspect it in a browser UI (no LLM needed):
    npx @modelcontextprotocol/inspector python hello_mcp.py
    # or register it in VS Code / Claude Desktop and call it from agent mode.
"""

from mcp.server.fastmcp import FastMCP

# The server's name. Clients show this so users know which server a tool came from.
mcp = FastMCP("hello")


# ---- A TOOL: an action the model (or your code) can call -------------------
# - The function name becomes the tool name: "greet".
# - The docstring becomes the tool DESCRIPTION the model reads to decide when
#   to call it. Write it like instructions to a teammate.
# - The type hints become the INPUT SCHEMA. "name: str" => one required string arg.
# - The return value is sent back to the caller as the tool result.
@mcp.tool()
def greet(name: str) -> str:
    """Return a friendly greeting for the given person's name."""
    return f"Hello, {name}! Your MCP server works."


# A second tool showing multiple typed args + a structured (dict) return.
@mcp.tool()
def add(a: int, b: int) -> dict:
    """Add two integers and return the sum."""
    return {"a": a, "b": b, "sum": a + b}


# ---- A RESOURCE: read-only data addressed by a URI (like a GET) ------------
# The {name} in the URI template becomes a function argument.
@mcp.resource("greeting://{name}")
def greeting_resource(name: str) -> str:
    """Expose a greeting as readable data at greeting://<name>."""
    return f"Hello resource for {name}"


if __name__ == "__main__":
    # Default transport is stdio: the client launches THIS file as a subprocess
    # and talks over stdin/stdout. Switch to "streamable-http" to serve it as a
    # shared web service that many clients connect to.
    mcp.run()
