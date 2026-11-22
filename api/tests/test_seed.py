"""Seed plan for the sandbox: deterministic, synthetic, tagged, and create-only."""

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from getpaid.data.mcp_source import SEED_TAG
from getpaid.seed import AlreadySeeded, apply_plan, build_plan, summarize

TODAY = date(2026, 11, 22)


def test_plan_is_deterministic() -> None:
    assert build_plan(TODAY) == build_plan(TODAY)


def test_plan_size_and_mix() -> None:
    p = build_plan(TODAY)
    assert len(p.customers) == 40
    assert 140 <= len(p.invoices) <= 160
    kinds = {i.kind for i in p.invoices}
    assert {
        "history_on_time",
        "history_late",
        "overdue",
        "not_due",
        "partial",
        "paid_recent",
    } <= kinds
    assert len(p.disputed) == 4
    assert sum(1 for i in p.invoices if i.memo and "ignore" in i.memo.lower()) == 3


def test_every_customer_is_tagged_synthetic_with_example_email() -> None:
    for c in build_plan(TODAY).customers:
        assert SEED_TAG in c.notes and "synthetic" in c.notes
        assert c.email.endswith(".example")


def test_payments_are_consistent_with_invoices() -> None:
    p = build_plan(TODAY)
    by_key = {i.key: i for i in p.invoices}
    for pay in p.payments:
        inv = by_key[pay.invoice_key]
        assert 0 < pay.amount <= inv.total
        assert pay.date >= inv.txn_date
        if inv.kind == "partial":
            assert pay.amount < inv.total
        if inv.kind == "history_late":
            assert pay.date > inv.txn_date + timedelta(days=inv.term_days)
        if inv.kind == "history_on_time":
            assert pay.date <= inv.txn_date + timedelta(days=inv.term_days)
    assert all(not pay.date > TODAY for pay in p.payments)


def test_overdue_invoices_are_actually_past_due() -> None:
    for i in build_plan(TODAY).invoices:
        due = i.txn_date + timedelta(days=i.term_days)
        if i.kind == "overdue":
            assert due < TODAY
        if i.kind == "not_due":
            assert due > TODAY


def test_summary_reports_counts() -> None:
    text = summarize(build_plan(TODAY))
    assert "40 customers" in text and "invoices" in text and "payments" in text


class FakeSeedClient:
    def __init__(self, existing: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.existing = existing or []
        self.n = 0

    async def call(self, tool: str, params: dict[str, Any]) -> list[dict[str, str]]:
        self.calls.append((tool, params))
        if tool == "search_customers":
            return [{"type": "text", "text": f"Found {len(self.existing)} customers:"}] + [
                {"type": "text", "text": json.dumps(c)} for c in self.existing
            ]
        if tool == "search_terms":
            return [
                {"type": "text", "text": "Found 2 terms"},
                {
                    "type": "text",
                    "text": json.dumps(
                        [{"Id": "2", "Name": "Net 15"}, {"Id": "3", "Name": "Net 30"}]
                    ),
                },
            ]
        if tool == "search_items":
            return [
                {
                    "type": "text",
                    "text": json.dumps({"Id": "2", "Name": "Hours", "Type": "Service"}),
                }
            ]
        self.n += 1
        return [
            {"type": "text", "text": "created:"},
            {"type": "text", "text": json.dumps({"Id": str(self.n)})},
        ]


async def test_apply_creates_only_customers_invoices_payments_and_writes_manifest(
    tmp_path: Path,
) -> None:
    plan = build_plan(TODAY)
    fake = FakeSeedClient()
    manifest = tmp_path / "manifest.json"
    await apply_plan(plan, fake, manifest)
    tools = [t for t, _ in fake.calls]
    writes = [t for t in tools if t.startswith("create_")]
    assert set(writes) == {"create_customer", "create_invoice", "create_payment"}
    assert writes.count("create_customer") == 40
    assert writes.count("create_invoice") == len(plan.invoices)
    assert writes.count("create_payment") == len(plan.payments)
    first_cust = next(p for t, p in fake.calls if t == "create_customer")
    assert SEED_TAG in first_cust["customer"]["Notes"]
    first_inv = next(p for t, p in fake.calls if t == "create_invoice")
    assert set(first_inv) >= {"customer_ref", "line_items", "txn_date", "sales_term_ref"}
    saved = json.loads(manifest.read_text())
    assert len(saved["disputed_invoice_ids"]) == 4
    assert saved["seed_tag"] == SEED_TAG
    assert len(saved["invoice_ids"]) == len(plan.invoices)


async def test_manifest_is_owner_only_and_records_disputes_before_payments(tmp_path: Path) -> None:
    plan = build_plan(TODAY)

    class FailOnPayment(FakeSeedClient):
        async def call(self, tool: str, params: dict[str, Any]) -> list[dict[str, str]]:
            if tool == "create_payment" and sum(t == "create_payment" for t, _ in self.calls) >= 3:
                raise RuntimeError("sandbox hiccup")
            return await super().call(tool, params)

    manifest = tmp_path / "m.json"
    with pytest.raises(RuntimeError):
        await apply_plan(plan, FailOnPayment(), manifest)
    saved = json.loads(manifest.read_text())
    assert len(saved["disputed_invoice_ids"]) == 4
    assert len(saved["payments_done"]) == 3
    assert oct(manifest.stat().st_mode)[-3:] == "600"


async def test_apply_refuses_when_seeded_customers_already_exist(tmp_path: Path) -> None:
    fake = FakeSeedClient(existing=[{"Id": "9", "DisplayName": "x", "Notes": SEED_TAG}])
    with pytest.raises(AlreadySeeded):
        await apply_plan(build_plan(TODAY), fake, tmp_path / "m.json")
    assert not [t for t, _ in fake.calls if t.startswith("create_")]
