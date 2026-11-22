"""Our own read-only MCP server ("front door" for Claude Desktop)."""

import asyncio

from getpaid.data.source import FixtureSource
from getpaid.mcp_server import (
    TOOLS,
    build_server,
    customer_balance,
    invoice_lookup,
    overdue_invoices,
)

SRC = FixtureSource()


def test_only_read_tools_are_exposed_and_marked_read_only() -> None:
    tools = asyncio.run(build_server(SRC).list_tools())
    assert {t.name for t in tools} == set(TOOLS)
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)


def test_overdue_invoices_uses_the_deterministic_query() -> None:
    out = overdue_invoices(SRC, min_days_overdue=60)
    assert out["summary"]["count"] == 1 and out["rows"][0]["invoice_number"] == "1045"


def test_customer_balance_and_lookup() -> None:
    assert customer_balance(SRC, "acme")["summary"]["total_balance"] == "1840.00"
    assert invoice_lookup(SRC, "#1047")["rows"][0]["status"] == "disputed"


def test_inputs_are_bounded() -> None:
    assert customer_balance(SRC, "x" * 500)["error"]
    assert overdue_invoices(SRC, min_days_overdue=-5)["error"]
    assert invoice_lookup(SRC, "")["error"]


def test_tool_call_through_the_server() -> None:
    result = asyncio.run(build_server(SRC).call_tool("invoice_lookup", {"invoice_number": "1045"}))
    assert "1045" in str(result)
