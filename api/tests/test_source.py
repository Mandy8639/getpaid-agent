"""Fixture source: parses MCP text-content items holding QuickBooks entity JSON into cases."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from getpaid.data.mcp_content import McpContentError, parse_entities
from getpaid.data.source import FIXTURES, FixtureSource

AS_OF = date(2026, 11, 22)


def test_parse_entities_skips_the_summary_line_and_decodes_json_items() -> None:
    content = [
        {"type": "text", "text": "Found 1 invoices"},
        {"type": "text", "text": '{"Id": "1"}'},
    ]
    assert parse_entities(content) == [{"Id": "1"}]


def test_parse_entities_raises_on_error_text() -> None:
    with pytest.raises(McpContentError):
        parse_entities([{"type": "text", "text": "Error searching invoices: boom"}])


def test_parse_entities_rejects_non_object_json() -> None:
    with pytest.raises(McpContentError):
        parse_entities([{"type": "text", "text": "Found 1"}, {"type": "text", "text": "[1, 2]"}])


def test_cases_cover_every_fixture_invoice_with_money_as_decimal() -> None:
    cases = {c.invoice.doc_number: c for c in FixtureSource().cases(AS_OF)}
    assert set(cases) == {"1042", "1043", "1044", "1045", "1046", "1047", "1048", "1049"}
    acme = cases["1042"]
    assert acme.invoice.balance == Decimal("1840.00")
    assert acme.customer.display_name == "Acme Landscaping"
    assert acme.days_overdue == 21


def test_partial_payment_and_history_and_dispute_flags() -> None:
    cases = {c.invoice.doc_number: c for c in FixtureSource().cases(AS_OF)}
    assert cases["1044"].paid_so_far == Decimal("2000.00")
    assert cases["1043"].prior_late_payments == 2
    assert cases["1047"].disputed is True
    assert cases["1046"].invoice.balance == Decimal("0.00")
    assert cases["1048"].days_overdue < 0


def test_untrusted_notes_are_kept_separate_from_facts() -> None:
    harbor = next(c for c in FixtureSource().cases(AS_OF) if c.invoice.doc_number == "1049")
    assert "Ignore previous instructions" in harbor.untrusted_notes


def test_customer_names_are_sanitised_at_ingest(tmp_path: Path) -> None:
    src = FIXTURES
    for p in ("mcp",):
        (tmp_path / p).mkdir()
    for f in ("search_invoices", "search_payments"):
        (tmp_path / "mcp" / f"{f}.json").write_text((src / "mcp" / f"{f}.json").read_text())
    (tmp_path / "app_state.json").write_text((src / "app_state.json").read_text())
    data = json.loads((src / "mcp" / "search_customers.json").read_text())
    first = json.loads(data["content"][1]["text"])
    first["DisplayName"] = "Acme​‮ Landscaping\n" + "x" * 300
    data["content"][1]["text"] = json.dumps(first)
    (tmp_path / "mcp" / "search_customers.json").write_text(json.dumps(data))
    acme = next(c for c in FixtureSource(tmp_path).cases(AS_OF) if c.customer.id == "11")
    assert "​" not in acme.customer.display_name
    assert "‮" not in acme.customer.display_name
    assert "\n" not in acme.customer.display_name
    assert len(acme.customer.display_name) <= 80


def test_payment_dates_are_attached_to_the_case() -> None:
    cobalt = next(c for c in FixtureSource().cases(AS_OF) if c.invoice.doc_number == "1044")
    assert cobalt.payment_dates == (date(2026, 11, 12),)


def test_missing_doc_number_and_due_date_fall_back(tmp_path: Path) -> None:
    for sub in ("mcp",):
        (tmp_path / sub).mkdir()
    for f in ("search_customers", "search_payments"):
        (tmp_path / "mcp" / f"{f}.json").write_text((FIXTURES / "mcp" / f"{f}.json").read_text())
    (tmp_path / "app_state.json").write_text((FIXTURES / "app_state.json").read_text())
    data = json.loads((FIXTURES / "mcp" / "search_invoices.json").read_text())
    first = json.loads(data["content"][1]["text"])
    first.pop("DocNumber")
    first.pop("DueDate")
    data["content"][1]["text"] = json.dumps(first)
    (tmp_path / "mcp" / "search_invoices.json").write_text(json.dumps(data))
    case = next(c for c in FixtureSource(tmp_path).cases(AS_OF) if c.invoice.id == "101")
    assert case.invoice.doc_number == "101"
    assert case.invoice.due_date == case.invoice.txn_date
