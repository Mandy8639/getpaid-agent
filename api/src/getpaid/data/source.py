"""Data sources. FixtureSource reads saved MCP tool output; McpSource (slice 2) calls the server."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from getpaid.data.mcp_content import parse_entities
from getpaid.domain import Case, Customer, Invoice

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


class DataSource(Protocol):
    def cases(self, as_of: date) -> list[Case]: ...


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _invoice(raw: dict[str, Any]) -> Invoice:
    return Invoice(
        id=str(raw["Id"]),
        doc_number=str(raw.get("DocNumber") or raw["Id"]),
        customer_id=str(raw["CustomerRef"]["value"]),
        txn_date=date.fromisoformat(raw["TxnDate"]),
        due_date=date.fromisoformat(raw.get("DueDate") or raw["TxnDate"]),
        total=_money(raw["TotalAmt"]),
        balance=_money(raw["Balance"]),
        currency=str((raw.get("CurrencyRef") or {}).get("value", "USD")),
    )


MAX_NAME = 80


def clean_name(value: object) -> str:
    """Untrusted display names: drop control/format characters, collapse spaces, cap length."""
    text = unicodedata.normalize("NFKC", str(value))
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("C") or ch == " ")
    return re.sub(r"\s+", " ", text).strip()[:MAX_NAME]


def _customer(raw: dict[str, Any]) -> Customer:
    return Customer(
        id=str(raw["Id"]),
        display_name=clean_name(raw["DisplayName"]),
        email=(raw.get("PrimaryEmailAddr") or {}).get("Address"),
    )


def _notes(raw: dict[str, Any]) -> str:
    memo = (raw.get("CustomerMemo") or {}).get("value") or ""
    return "\n".join(p for p in (memo, raw.get("PrivateNote") or "") if p)


class FixtureSource:
    def __init__(self, root: Path = FIXTURES) -> None:
        self.root = root
        self.as_of = date.fromisoformat(json.loads((root / "app_state.json").read_text())["as_of"])

    def _load(self, name: str) -> list[dict[str, Any]]:
        data = json.loads((self.root / "mcp" / f"{name}.json").read_text())
        return parse_entities(data["content"])

    def cases(self, as_of: date) -> list[Case]:
        state = json.loads((self.root / "app_state.json").read_text())
        customers = {c.id: c for c in map(_customer, self._load("search_customers"))}
        paid: dict[str, Decimal] = defaultdict(Decimal)
        paid_on: dict[str, list[date]] = defaultdict(list)
        for p in self._load("search_payments"):
            for line in p.get("Line", []):
                for linked in line.get("LinkedTxn", []):
                    if linked.get("TxnType") == "Invoice":
                        paid[str(linked["TxnId"])] += _money(line["Amount"])
                        paid_on[str(linked["TxnId"])].append(date.fromisoformat(p["TxnDate"]))
        late = state.get("late_history", {})
        disputed = set(state.get("disputed_invoice_ids", []))
        out: list[Case] = []
        for raw in self._load("search_invoices"):
            inv = _invoice(raw)
            out.append(
                Case(
                    invoice=inv,
                    customer=customers[inv.customer_id],
                    as_of=as_of,
                    paid_so_far=paid.get(inv.id, Decimal("0.00")),
                    prior_late_payments=len(late.get(inv.customer_id, [])),
                    disputed=inv.id in disputed,
                    untrusted_notes=_notes(raw),
                    payment_dates=tuple(sorted(paid_on.get(inv.id, []))),
                )
            )
        return out
