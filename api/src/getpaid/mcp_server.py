"""getpaid's own read-only MCP server: ask about overdue invoices from Claude Desktop.

    uv run python -m getpaid.mcp_server          # stdio; SOURCE=fixture|mcp as for the API

Three read tools, all backed by the same deterministic queries as the dashboard's Q&A
(agent/qa.py execute), so the numbers a client sees come from code, not a model. Customer
names that carry links or contacts are hidden. Nothing here can draft, approve, send or
change anything.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from getpaid.agent.qa import QueryPlan, execute
from getpaid.data.source import DataSource, FixtureSource

TOOLS = ("overdue_invoices", "customer_balance", "invoice_lookup")
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)


def _today(src: DataSource) -> date:
    return getattr(src, "as_of", None) or date.today()


def _run(src: DataSource, plan: QueryPlan) -> dict[str, Any]:
    r = execute(plan, src.cases(_today(src)))
    return {"rows": r.rows, "summary": r.summary}


def overdue_invoices(
    src: DataSource, min_days_overdue: int | None = None, max_days_overdue: int | None = None
) -> dict[str, Any]:
    for v in (min_days_overdue, max_days_overdue):
        if v is not None and not 0 <= v <= 3650:
            return {"error": "days must be between 0 and 3650"}
    return _run(
        src,
        QueryPlan(
            intent="overdue_list",
            min_days_overdue=min_days_overdue,
            max_days_overdue=max_days_overdue,
        ),
    )


def customer_balance(src: DataSource, customer: str) -> dict[str, Any]:
    if not 1 <= len(customer.strip()) <= 80:
        return {"error": "customer must be 1 to 80 characters"}
    return _run(src, QueryPlan(intent="customer_balance", customer=customer.strip()))


def invoice_lookup(src: DataSource, invoice_number: str) -> dict[str, Any]:
    if not 1 <= len(invoice_number.strip()) <= 20:
        return {"error": "invoice_number must be 1 to 20 characters"}
    return _run(src, QueryPlan(intent="invoice_lookup", invoice_number=invoice_number))


def build_server(src: DataSource) -> MCPServer:
    server = MCPServer("getpaid", instructions="Read-only questions about overdue invoices.")

    @server.tool(
        name="overdue_invoices",
        annotations=READ_ONLY,
        description="Overdue invoices, largest first. Optional day range.",
    )
    def _overdue(
        min_days_overdue: int | None = None, max_days_overdue: int | None = None
    ) -> dict[str, Any]:
        return overdue_invoices(src, min_days_overdue, max_days_overdue)

    @server.tool(
        name="customer_balance",
        annotations=READ_ONLY,
        description="What one customer owes (match on part of the name).",
    )
    def _balance(customer: str) -> dict[str, Any]:
        return customer_balance(src, customer)

    @server.tool(
        name="invoice_lookup",
        annotations=READ_ONLY,
        description="Status and balance of one invoice by number.",
    )
    def _lookup(invoice_number: str) -> dict[str, Any]:
        return invoice_lookup(src, invoice_number)

    return server


def main() -> None:  # pragma: no cover - stdio entry point
    from getpaid.config import get_settings

    s = get_settings()
    if s.source == "mcp":
        from getpaid.data.mcp_source import McpSource

        src: DataSource = McpSource()
    else:
        src = FixtureSource()
    build_server(src).run()


if __name__ == "__main__":  # pragma: no cover
    main()
