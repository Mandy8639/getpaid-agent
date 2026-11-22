"""Domain types. Money is Decimal end to end; record fields are facts, notes are untrusted."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


@dataclass(frozen=True)
class Customer:
    id: str
    display_name: str
    email: str | None


@dataclass(frozen=True)
class Invoice:
    id: str
    doc_number: str
    customer_id: str
    txn_date: date
    due_date: date
    total: Decimal
    balance: Decimal
    currency: str


@dataclass(frozen=True)
class Case:
    """Everything the agent may know about one invoice. Only `untrusted_notes` is free text."""

    invoice: Invoice
    customer: Customer
    as_of: date
    paid_so_far: Decimal
    prior_late_payments: int
    disputed: bool
    untrusted_notes: str = ""
    payment_dates: tuple[date, ...] = ()

    @property
    def days_overdue(self) -> int:
        return (self.as_of - self.invoice.due_date).days


class Action(StrEnum):
    DRAFT = "draft"
    HOLD = "hold"


class Tone(StrEnum):
    FRIENDLY_NUDGE = "friendly_nudge"
    FIRM_REMINDER = "firm_reminder"
    FINAL_NOTICE = "final_notice"


class HoldReason(StrEnum):
    PAID = "paid"
    DISPUTED = "disputed"
    NOT_OVERDUE = "not_overdue"
    DRAFTER_FAILED = "drafter_failed"
    GUARDRAIL_BLOCKED = "guardrail_blocked"
    SPEND_CAP = "spend_cap"


@dataclass(frozen=True)
class Decision:
    action: Action
    tone: Tone | None = None
    hold_reason: HoldReason | None = None


@dataclass(frozen=True)
class Policy:
    """What the business has authorised the agent to offer. Defaults offer nothing extra."""

    business_name: str = "Northwind Studio"
    sender_name: str = "Sam"
    reply_email: str = "billing@northwind.example"
    allow_payment_plan: bool = False
