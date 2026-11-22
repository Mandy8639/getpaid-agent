"""Live data source: Intuit's QuickBooks MCP server (sandbox), seeded records only.

Terms check (build-plan.md): only our own synthetic records may be sent to a model, never
Intuit's pre-loaded sample company. Seeded customers carry SEED_TAG in their Notes; every
invoice and payment is filtered to those customers before a Case is built.

A customer counts as ours only if it carries SEED_TAG *and* its Id is in the seed manifest
(so a sample record that happens to contain the tag can't slip in). No manifest means no
cases: the source fails closed before touching the sandbox.

Cases: open invoices, plus invoices paid in the last RECENT_PAID_DAYS (so the owner sees why
they're held). Late-payment history is derived from the data: fully paid invoices whose last
payment came after the due date. Disputes are app-side state in the seed manifest.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from getpaid.data.mcp_client import DEFAULT_TOKEN_STORE, REPO_ROOT, connect
from getpaid.data.mcp_content import parse_entities
from getpaid.data.source import _customer, _invoice, _money, _notes
from getpaid.domain import Case

SEED_TAG = "getpaid-seed:v1"
RECENT_PAID_DAYS = 30
DEFAULT_MANIFEST = REPO_ROOT / ".seed" / "manifest.json"
PAYMENT_LIMIT = 1000
log = logging.getLogger("getpaid")
# One live read at a time: each run starts the MCP server, which may rotate the refresh token.
_RUN_LOCK = threading.Lock()


class _Caller(Protocol):
    async def call(self, tool: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


ClientFactory = Callable[[], AbstractAsyncContextManager[_Caller]]


def _default_factory() -> AbstractAsyncContextManager[_Caller]:  # pragma: no cover - live
    return connect(DEFAULT_TOKEN_STORE, writes=False)


class McpSource:
    def __init__(
        self,
        *,
        client_factory: ClientFactory = _default_factory,
        manifest: Path = DEFAULT_MANIFEST,
    ) -> None:
        self.client_factory = client_factory
        self.manifest = manifest
        self.as_of: date | None = None  # live data: the API uses today

    def cases(self, as_of: date) -> list[Case]:
        # Called from sync FastAPI routes (run in a worker thread, no running event loop).
        try:
            manifest = json.loads(self.manifest.read_text())
        except FileNotFoundError:
            log.warning("no seed manifest at %s; live source returns no cases", self.manifest)
            return []
        with _RUN_LOCK:
            return asyncio.run(self._cases(as_of, manifest))

    async def _cases(self, as_of: date, manifest: dict[str, Any]) -> list[Case]:
        ours = {str(v) for v in (manifest.get("customer_ids") or {}).values()}
        disputed = {str(v) for v in manifest.get("disputed_invoice_ids", [])}
        async with self.client_factory() as c:
            raw_customers = parse_entities(await c.call("search_customers", {"fetchAll": True}))
            raw_invoices = parse_entities(
                await c.call("search_invoices", {"criteria": {"fetchAll": True}})
            )
            raw_payments = parse_entities(await c.call("search_payments", {"limit": PAYMENT_LIMIT}))
        if len(raw_payments) >= PAYMENT_LIMIT:
            raise RuntimeError(f"payments may be truncated at {PAYMENT_LIMIT}; refusing to guess")

        seeded = {
            str(r["Id"]): _customer(r)
            for r in raw_customers
            if SEED_TAG in (r.get("Notes") or "") and str(r["Id"]) in ours
        }
        invoices = [
            r for r in raw_invoices if str((r.get("CustomerRef") or {}).get("value")) in seeded
        ]
        paid: dict[str, Decimal] = defaultdict(Decimal)
        paid_on: dict[str, list[date]] = defaultdict(list)
        for p in raw_payments:
            if str((p.get("CustomerRef") or {}).get("value")) not in seeded:
                continue
            for line in p.get("Line", []):
                for linked in line.get("LinkedTxn", []):
                    if linked.get("TxnType") == "Invoice":
                        paid[str(linked["TxnId"])] += _money(line["Amount"])
                        paid_on[str(linked["TxnId"])].append(date.fromisoformat(p["TxnDate"]))

        late: dict[str, int] = defaultdict(int)
        parsed = [(raw, _invoice(raw)) for raw in invoices]
        for _, inv in parsed:
            dates = paid_on.get(inv.id)
            if inv.balance == 0 and dates and max(dates) > inv.due_date:
                late[inv.customer_id] += 1

        out: list[Case] = []
        for raw, inv in parsed:
            dates = sorted(paid_on.get(inv.id, []))
            recently_paid = (
                inv.balance == 0 and dates and (as_of - dates[-1]).days <= RECENT_PAID_DAYS
            )
            if inv.balance <= 0 and not recently_paid:
                continue
            was_late = inv.balance == 0 and dates and dates[-1] > inv.due_date
            out.append(
                Case(
                    invoice=inv,
                    customer=seeded[inv.customer_id],
                    as_of=as_of,
                    paid_so_far=paid.get(inv.id, Decimal("0.00")),
                    prior_late_payments=late[inv.customer_id] - (1 if was_late else 0),
                    disputed=inv.id in disputed,
                    untrusted_notes=_notes(raw),
                    payment_dates=tuple(dates),
                )
            )
        return out
