"""Environment + MCP-config loading. No business logic here."""

import os
import re
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
MCP_CONFIG_PATH = Path(
    os.getenv("MCP_CONFIG_PATH", BASE_DIR / "config" / "mcp_servers.json")
)

REQUIRED_ENV = [
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
]


def check_env() -> list[str]:
    """Return the list of required env vars that are missing (empty == OK)."""
    return [v for v in REQUIRED_ENV if not os.getenv(v)]


def _expand(obj):
    """Recursively expand ${VAR} placeholders using environment variables."""
    if isinstance(obj, str):
        return re.sub(r"\$\{([^}]+)\}", lambda m: os.getenv(m.group(1), ""), obj)
    if isinstance(obj, list):
        return [_expand(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _expand(v) for k, v in obj.items()}
    return obj


def load_mcp_config() -> dict:
    """
    Load config/mcp_servers.json, drop comment keys (starting with '_'),
    and expand ${VAR} placeholders from the environment.

    Returns a dict shaped like langchain-mcp-adapters expects:
        { "<server_name>": { "transport": "stdio"|"streamable_http", ... }, ... }
    """
    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    cleaned = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _expand(cleaned)
