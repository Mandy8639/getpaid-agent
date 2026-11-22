"""Live contract tests: run only with RUN_LIVE=1 (needs node, .env tokens and a seeded sandbox).

They check that the saved fixtures still look like what the MCP server really returns, and
that the whole API works on live sandbox data. Never run in CI.
"""

import json
import os
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from getpaid.agent.drafter import TemplateDrafter
from getpaid.data.mcp_client import DEFAULT_TOKEN_STORE, connect
from getpaid.data.mcp_content import parse_entities
from getpaid.data.mcp_source import SEED_TAG, McpSource
from getpaid.data.source import FIXTURES
from getpaid.db import make_engine, metadata
from getpaid.domain import Policy
from getpaid.main import create_app

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to hit the sandbox"
    ),
    pytest.mark.enable_socket,
]

USED_INVOICE_FIELDS = {
    "Id",
    "DocNumber",
    "TxnDate",
    "DueDate",
    "TotalAmt",
    "Balance",
    "CustomerRef",
}
USED_PAYMENT_FIELDS = {"TxnDate", "CustomerRef", "Line"}


def _fixture(name: str) -> list[dict[str, Any]]:
    return parse_entities(json.loads((FIXTURES / "mcp" / f"{name}.json").read_text())["content"])


async def test_fixture_fields_exist_in_live_output() -> None:
    async with connect(DEFAULT_TOKEN_STORE, writes=False) as c:
        invoices = parse_entities(await c.call("search_invoices", {"criteria": {"limit": 20}}))
        payments = parse_entities(await c.call("search_payments", {"limit": 20}))
        customers = parse_entities(await c.call("search_customers", {"fetchAll": True}))
    assert invoices and payments and customers
    for inv in invoices:
        assert set(inv) >= USED_INVOICE_FIELDS, set(USED_INVOICE_FIELDS - set(inv))
    for p in payments:
        assert set(p) >= USED_PAYMENT_FIELDS
    assert set(_fixture("search_invoices")[0]) >= USED_INVOICE_FIELDS
    assert any(SEED_TAG in (c.get("Notes") or "") for c in customers)


def test_live_source_returns_only_seeded_cases() -> None:
    cases = McpSource().cases(date.today())
    assert cases
    assert all(c.customer.display_name.endswith("(demo)") for c in cases)


def test_live_run_through_the_api() -> None:
    url = "postgresql+psycopg://getpaid:getpaid@127.0.0.1:5434/getpaid"
    admin = make_engine(url, autocommit=True)
    with admin.connect() as conn:
        if not conn.execute(
            text("select 1 from pg_database where datname='getpaid_live_e2e'")
        ).first():
            conn.execute(text("create database getpaid_live_e2e"))
    admin.dispose()
    engine = make_engine(url.rsplit("/", 1)[0] + "/getpaid_live_e2e")
    metadata.drop_all(engine)
    metadata.create_all(engine)
    app = create_app(engine=engine, source=McpSource(), drafter=TemplateDrafter(), policy=Policy())
    with TestClient(app) as client:
        counts = client.post("/runs").json()
        held = client.get("/drafts", params={"status": "held"}).json()
        top = client.get("/drafts/next").json()
    engine.dispose()
    assert counts["pending"] > 0 and counts["held"] > 0
    assert {d["hold_reason"] for d in held} >= {"paid", "disputed", "not_overdue"}
    assert top["guardrail_passed"] is True
    assert top["customer_name"].endswith("(demo)")
