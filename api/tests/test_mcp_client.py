"""MCP client: tool allowlists, read-only server flags, and what the server process may see."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from getpaid.data.mcp_client import (
    DEFAULT_TOKEN_STORE,
    READ_TOOLS,
    SEED_TOOLS,
    McpClient,
    NotSandbox,
    ToolNotAllowed,
    check_token_store,
    server_env,
)


@dataclass
class FakeResult:
    content: list[Any]
    isError: bool = False


@dataclass
class FakeText:
    text: str
    type: str = "text"


@dataclass
class FakeSession:
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> FakeResult:
        self.calls.append((name, arguments))
        return FakeResult([FakeText("Found 1 invoices"), FakeText('{"Id": "1"}')])


def test_read_tools_are_read_only() -> None:
    assert all(t.startswith(("search_", "read_", "get_")) for t in READ_TOOLS)


def test_seed_tools_never_include_update_or_delete() -> None:
    assert not [t for t in SEED_TOOLS if t.startswith(("update_", "delete_"))]


async def test_call_wraps_arguments_in_params_and_returns_text_items() -> None:
    session = FakeSession()
    client = McpClient(allowed=READ_TOOLS, session=session)
    content = await client.call("search_invoices", {"criteria": {"fetchAll": True}})
    assert session.calls == [("search_invoices", {"params": {"criteria": {"fetchAll": True}}})]
    assert content == [
        {"type": "text", "text": "Found 1 invoices"},
        {"type": "text", "text": '{"Id": "1"}'},
    ]


@pytest.mark.parametrize(
    "tool", ["create_invoice", "delete_invoice", "update_customer", "send_anything"]
)
async def test_read_client_refuses_anything_outside_its_allowlist(tool: str) -> None:
    session = FakeSession()
    client = McpClient(allowed=READ_TOOLS, session=session)
    with pytest.raises(ToolNotAllowed):
        await client.call(tool, {})
    assert session.calls == []


def test_read_server_env_disables_all_writes_and_passes_no_model_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-should-not-leak")
    env = server_env(Path("/abs/.env"), writes=False)
    assert env["QUICKBOOKS_TOKEN_STORE_PATH"] == "/abs/.env"
    assert env["QUICKBOOKS_DISABLE_WRITE"] == "true"
    assert env["QUICKBOOKS_DISABLE_UPDATE"] == "true"
    assert env["QUICKBOOKS_DISABLE_DELETE"] == "true"
    assert "OPENROUTER_API_KEY" not in env
    assert "sk-should-not-leak" not in env.values()


def test_seed_server_env_allows_create_only() -> None:
    env = server_env(Path("/abs/.env"), writes=True)
    assert env["QUICKBOOKS_DISABLE_WRITE"] == "false"
    assert env["QUICKBOOKS_DISABLE_UPDATE"] == "true"
    assert env["QUICKBOOKS_DISABLE_DELETE"] == "true"


def test_token_store_path_must_be_absolute() -> None:
    with pytest.raises(ValueError):
        server_env(Path("relative/.env"), writes=False)


# --- slice 2 security review ---


def test_token_store_must_be_sandbox(tmp_path: Path) -> None:
    store = tmp_path / "tokens"
    store.write_text("QUICKBOOKS_ENVIRONMENT=production\nQUICKBOOKS_CLIENT_ID=x\n")
    with pytest.raises(NotSandbox):
        check_token_store(store)


def test_token_store_sandbox_passes(tmp_path: Path) -> None:
    store = tmp_path / "tokens"
    store.write_text("QUICKBOOKS_ENVIRONMENT=sandbox\nQUICKBOOKS_CLIENT_ID=x\n")
    check_token_store(store)


def test_token_store_must_not_hold_other_secrets(tmp_path: Path) -> None:
    store = tmp_path / "tokens"
    store.write_text("QUICKBOOKS_ENVIRONMENT=sandbox\nOPENROUTER_API_KEY=sk-x\n")
    with pytest.raises(ValueError, match="only QUICKBOOKS_"):
        check_token_store(store)


def test_default_token_store_is_not_the_shared_env() -> None:
    assert DEFAULT_TOKEN_STORE.name == ".qbo-tokens"
