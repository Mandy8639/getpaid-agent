"""Deterministic action choice: which invoices get a draft, and in what tone."""

from datetime import date

import pytest

from getpaid.agent.decide import decide
from getpaid.data.source import FixtureSource
from getpaid.domain import Action, HoldReason, Tone

AS_OF = date(2026, 11, 22)
CASES = {c.invoice.doc_number: c for c in FixtureSource().cases(AS_OF)}


@pytest.mark.parametrize(
    ("doc", "reason"),
    [("1046", HoldReason.PAID), ("1047", HoldReason.DISPUTED), ("1048", HoldReason.NOT_OVERDUE)],
)
def test_holds(doc: str, reason: HoldReason) -> None:
    d = decide(CASES[doc])
    assert d.action is Action.HOLD
    assert d.hold_reason is reason


@pytest.mark.parametrize(
    ("doc", "tone"),
    [
        ("1042", Tone.FRIENDLY_NUDGE),  # 21 days, clean history
        ("1044", Tone.FRIENDLY_NUDGE),  # 8 days, partial payment
        ("1043", Tone.FIRM_REMINDER),  # 52 days, repeat late payer
        ("1045", Tone.FINAL_NOTICE),  # 74 days
    ],
)
def test_tones(doc: str, tone: Tone) -> None:
    d = decide(CASES[doc])
    assert d.action is Action.DRAFT
    assert d.tone is tone
