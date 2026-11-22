"""Deterministic guardrail run on every draft before the owner sees it.

G1  facts match the record: every amount, invoice number, date and "N days overdue" in the
    draft must match the invoice; the balance and invoice number must be present.
G2  no promises the business didn't authorise (discounts, waivers, legal threats, payment
    plans unless the policy allows them, cancellation).
G3  never a draft for a paid, disputed or not-yet-due invoice (defence in depth over decide()).
G4  no links, other contact routes, or payment/bank details (phishing-shaped content),
    and no hidden characters (zero-width / direction marks) that could disguise text.

All checks run on NFKC-normalised text with dash-like characters folded to "-" and hidden
characters removed, so look-alike tricks can't slip a fact or promise past a regex.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict

from getpaid.agent.decide import decide
from getpaid.domain import Action, Case, Policy


class Draft(BaseModel):
    """What the drafter returns. extra=forbid gives strict JSON schema (additionalProperties)."""

    model_config = ConfigDict(extra="forbid")
    subject: str
    body: str


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str


@dataclass
class GuardrailResult:
    violations: list[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations


_NUM = r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?"
_MONEY = [
    re.compile(r"(?:\$|\bUSD\s?)\s?" + _NUM + r"(?!\d|,\d)"),
    re.compile(r"(?<![\$\d,.])" + _NUM + r"\s?USD\b"),
]
_INVOICE_REF = [
    re.compile(
        r"\binv(?:oice)?\.?\s*(?:no\.?|number)?\s*#?\s*([A-Z]{0,4}-?\d{2,})\b(?!\s+days?\b)",
        re.I,
    ),
    re.compile(r"#\s?(\d{3,})\b"),
]
_PREFIX = re.compile(r"^[A-Za-z]*-?")
_DAYS = re.compile(r"\b(\d+)\s+days?\s+(?:past\s+due|overdue|late)\b", re.I)
_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_PATTERNS = [
    ("iso", re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")),
    ("us", re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})\b")),
    (
        "mdy",
        re.compile(
            rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?!\d)(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?", re.I
        ),
    ),
    (
        "dmy",
        re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_RE})\b\.?(?:,?\s+(\d{{4}}))?", re.I),
    ),
]
_PROMISES = re.compile(
    r"discount|\d+\s?%\s?off|\bwaiv|forgiv|late\s+fee|collections?\s+agenc|attorney|lawyer|"
    r"legal\s+action|\bcourt\b|\bsue\b|lawsuit|credit\s+(?:bureau|report)|"
    r"cancel(?:l)?ed|write[-\s]?off|debt\s+collect|garnish|report\s+you|penalt",
    re.I,
)
_PLAN = re.compile(r"payment\s+plan|instal(?:l)?ments?", re.I)
_TLDS = r"com|net|org|io|co|app|example|us|biz|info|me|link|pay|shop|xyz"
_URL = re.compile(
    rf"https?://|hxxps?|\bwww\.|\b[a-z0-9-]+\.(?:{_TLDS})\b|\[\.\]|\(dot\)|\[dot\]|"
    rf"\bdot\s+(?:{_TLDS})\b|\[[^\]]+\]\([^)]+\)",
    re.I,
)
_PHONE = re.compile(r"\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
_WORD_AMOUNT = re.compile(r"\bdollars?\b|\bbucks\b|\bhundred\b|\bthousand\b|\bgrand\b", re.I)
_HIDDEN = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
_DASHES = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"})

RULE_HINTS = {
    "G1": "use only the amounts, dates, invoice number and days overdue from the facts, in digits",
    "G2": "do not mention discounts, waivers, cancellation, payment plans, fees, legal action or "
    "collections at all, not even to say you won't",
    "G3": "this invoice must not get a reminder",
    "G4": "remove links, phone numbers, other email addresses and payment details",
}


def normalise(text: str) -> str:
    return _HIDDEN.sub("", unicodedata.normalize("NFKC", text)).translate(_DASHES)


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LONG_DIGITS = re.compile(r"\b\d{8,}\b")
_BANK = re.compile(
    r"\bwire\b|routing\s+number|bank\s+account|\biban\b|swift\s*(?:code|/\s*bic)|venmo|zelle|"
    r"gift\s+card|crypto",
    re.I,
)
DEADLINE_DAYS = 30


def _money(text: str) -> list[Decimal]:
    found: list[Decimal] = []
    for pat in _MONEY:
        for whole, cents in pat.findall(text):
            try:
                found.append(Decimal(whole.replace(",", "") + "." + (cents or "00")))
            except InvalidOperation:  # pragma: no cover - regex only yields digits
                continue
    return found


def _dates(text: str) -> list[tuple[int | None, int, int]]:
    """(year or None, month, day) for every date-looking span."""
    out: list[tuple[int | None, int, int]] = []
    for kind, pat in _DATE_PATTERNS:
        for g in pat.findall(text):
            if kind == "iso":
                out.append((int(g[0]), int(g[1]), int(g[2])))
            elif kind == "us":
                year = int(g[2]) if len(g[2]) == 4 else 2000 + int(g[2])
                out.append((year, int(g[0]), int(g[1])))
            elif kind == "mdy":
                out.append((int(g[2]) if g[2] else None, _MONTHS[g[0].lower()], int(g[1])))
            else:
                out.append((int(g[2]) if g[2] else None, _MONTHS[g[1].lower()], int(g[0])))
    return out


def _date_ok(found: tuple[int | None, int, int], allowed: list[date], as_of: date) -> bool:
    """A record date (issue, due, payment), or a reply-by deadline within 30 days of as_of."""
    year, month, day = found
    if any((year is None or year == d.year) and month == d.month and day == d.day for d in allowed):
        return True
    for y in (year,) if year else (as_of.year, as_of.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if 0 < (d - as_of).days <= DEADLINE_DAYS:
            return True
    return False


def check(draft: Draft, case: Case, policy: Policy) -> GuardrailResult:
    raw = f"{draft.subject}\n{draft.body}"
    text = normalise(raw)
    result = GuardrailResult()
    v = result.violations
    inv = case.invoice
    if _HIDDEN.search(raw):
        v.append(Violation("G4", "contains hidden characters"))

    # G1 facts
    allowed_money = {inv.balance, inv.total} | ({case.paid_so_far} if case.paid_so_far else set())
    amounts = _money(text)
    for amt in amounts:
        if amt not in allowed_money:
            v.append(Violation("G1", f"amount {amt} is not on the record"))
    if inv.balance not in amounts:
        v.append(Violation("G1", f"balance {inv.balance} is missing"))
    refs = {_PREFIX.sub("", m) for pat in _INVOICE_REF for m in pat.findall(text)}
    for ref in refs - {inv.doc_number}:
        v.append(Violation("G1", f"invoice number {ref} does not match {inv.doc_number}"))
    if inv.doc_number not in refs:
        v.append(Violation("G1", f"invoice number {inv.doc_number} is missing"))
    for found in _dates(text):
        if not _date_ok(found, [inv.due_date, inv.txn_date, *case.payment_dates], case.as_of):
            v.append(Violation("G1", f"date {found} is not on the record or a near deadline"))
    if _WORD_AMOUNT.search(text):
        v.append(Violation("G1", "amount written in words; use digits from the record"))
    for days in _DAYS.findall(text):
        if int(days) != case.days_overdue:
            v.append(Violation("G1", f"says {days} days overdue, record says {case.days_overdue}"))

    # G2 promises
    for m in _PROMISES.finditer(text):
        v.append(Violation("G2", f"unauthorised promise or threat: {m.group(0).lower()!r}"))
    if not policy.allow_payment_plan:
        for m in _PLAN.finditer(text):
            v.append(Violation("G2", f"payment plan not authorised: {m.group(0)!r}"))

    # G3 holds
    decision = decide(case)
    if decision.action is not Action.DRAFT:
        v.append(Violation("G3", f"invoice must not get a draft ({decision.hold_reason})"))

    # G4 links, contacts, payment details (the business reply address is the only contact)
    for email in _EMAIL.findall(text):
        if email.rstrip(".").lower() != policy.reply_email.lower():
            v.append(Violation("G4", "contact address is not the business reply address"))
    without_reply = re.sub(re.escape(policy.reply_email), " ", text, flags=re.I)
    if _URL.search(without_reply):
        v.append(Violation("G4", "contains a link or web address"))
    if _PHONE.search(without_reply):
        v.append(Violation("G4", "contains a phone number"))
    if _LONG_DIGITS.search(text) or _BANK.search(text):
        v.append(Violation("G4", "contains payment or bank details"))
    return result
