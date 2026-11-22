"""Deterministic choice of action and tone. No model involved, so holds can't be talked around."""

from getpaid.domain import Action, Case, Decision, HoldReason, Tone


def decide(case: Case) -> Decision:
    if case.invoice.balance <= 0:
        return Decision(Action.HOLD, hold_reason=HoldReason.PAID)
    if case.disputed:
        return Decision(Action.HOLD, hold_reason=HoldReason.DISPUTED)
    if case.days_overdue <= 0:
        return Decision(Action.HOLD, hold_reason=HoldReason.NOT_OVERDUE)
    if case.days_overdue > 60:
        return Decision(Action.DRAFT, tone=Tone.FINAL_NOTICE)
    if case.days_overdue > 30 or case.prior_late_payments >= 2:
        return Decision(Action.DRAFT, tone=Tone.FIRM_REMINDER)
    return Decision(Action.DRAFT, tone=Tone.FRIENDLY_NUDGE)
