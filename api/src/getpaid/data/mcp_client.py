"""Client for Intuit's QuickBooks Online MCP server (stdio, pinned git dependency).

Two layers keep this least-privilege:
1. The server is started with QUICKBOOKS_DISABLE_* flags, so write/update/delete tools are not
   even registered in read mode (and only create tools in seed mode).
2. Every call is checked against an explicit allowlist before it leaves this process.

The server process gets only PATH/HOME and the path of a dedicated token file (.qbo-tokens,
git-ignored, mode 600). Intuit's server loads every variable in that file, so the file may
hold only QUICKBOOKS_* values: never the model API key. check_token_store enforces that, and
that the environment is the sandbox, before the server is started.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parents[4]
SERVER_JS = REPO_ROOT / "mcp/node_modules/@qboapi/qbo-mcp-server/dist/index.js"
DEFAULT_TOKEN_STORE = REPO_ROOT / ".qbo-tokens"

READ_TOOLS = frozenset(
    {"search_invoices", "search_customers", "search_payments", "read_invoice", "get_customer"}
)
SEED_TOOLS = READ_TOOLS | {
    "create_customer",
    "create_invoice",
    "create_payment",
    "search_terms",
    "search_items",
}


class ToolNotAllowed(PermissionError):
    pass


class NotSandbox(PermissionError):
    pass


def check_token_store(path: Path) -> None:
    """Only QUICKBOOKS_* keys, and QUICKBOOKS_ENVIRONMENT must be exactly 'sandbox'."""
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    others = [k for k in values if not k.startswith("QUICKBOOKS_")]
    if others:
        raise ValueError(f"token store may hold only QUICKBOOKS_* keys; found {len(others)} other")
    if values.get("QUICKBOOKS_ENVIRONMENT") != "sandbox":
        raise NotSandbox("QUICKBOOKS_ENVIRONMENT must be 'sandbox'; refusing to connect")


class _Session(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


def server_env(token_store: Path, *, writes: bool) -> dict[str, str]:
    if not token_store.is_absolute():
        raise ValueError("token store path must be absolute")
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "QUICKBOOKS_TOKEN_STORE_PATH": str(token_store),
        "QUICKBOOKS_DISABLE_WRITE": "false" if writes else "true",
        "QUICKBOOKS_DISABLE_UPDATE": "true",
        "QUICKBOOKS_DISABLE_DELETE": "true",
    }


class McpClient:
    def __init__(self, *, allowed: frozenset[str], session: _Session) -> None:
        self.allowed = allowed
        self.session = session

    async def call(self, tool: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if tool not in self.allowed:
            raise ToolNotAllowed(f"tool {tool!r} is not on this client's allowlist")
        result = await self.session.call_tool(tool, {"params": params})
        if getattr(result, "isError", False):
            texts = [getattr(c, "text", "") for c in result.content]
            raise RuntimeError(f"MCP tool {tool} failed: {' '.join(texts)[:200]}")
        return [
            {"type": getattr(c, "type", "text"), "text": getattr(c, "text", "")}
            for c in result.content
        ]


@asynccontextmanager
async def connect(
    token_store: Path, *, writes: bool = False
) -> AsyncIterator[McpClient]:  # pragma: no cover - needs node and live credentials
    check_token_store(token_store)
    params = StdioServerParameters(
        command="node", args=[str(SERVER_JS)], env=server_env(token_store, writes=writes)
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield McpClient(allowed=SEED_TOOLS if writes else READ_TOOLS, session=session)
