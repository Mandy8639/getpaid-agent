"""Guardrail G1–G4: each rule has passing and failing cases. Deterministic, no model."""

from datetime import date

import pytest

from getpaid.agent.guardrail import Draft, check
from getpaid.data.source import FixtureSource
from getpaid.domain import Case, Policy

AS_OF = date(2026, 11, 22)
CASES = {c.invoice.doc_number: c for c in FixtureSource().cases(AS_OF)}
ACME = CASES["1042"]  # balance 1840.00, due 2026-11-01, issued 2026-10-02, 21 days late
COBALT = CASES["1044"]  # total 3200.00, balance 1200.00, paid 2000.00

GOOD = (
    "Hi Acme Landscaping,\n\nA quick reminder that invoice #1042 for $1,840.00 was due on "
    "November 1, 2026 and is now 21 days past due. Could you let us know when we can expect "
    "payment? Reply to billing@northwind.example with any questions.\n\nThanks,\nSam"
)


def rules(
    body: str, case: Case = ACME, policy: Policy | None = None, subject: str = "Invoice 1042"
) -> set[str]:
    return {
        v.rule
        for v in check(Draft(subject=subject, body=body), case, policy or Policy()).violations
    }


def test_good_draft_passes() -> None:
    result = check(Draft(subject="Invoice #1042 reminder", body=GOOD), ACME, Policy())
    assert result.passed, result.violations


# --- G1: facts match the record ---


@pytest.mark.parametrize(
    "amount", ["$1,840.00", "$1840.00", "$1,840", "USD 1,840.00", "1,840.00 USD"]
)
def test_g1_accepts_reformatted_correct_amount(amount: str) -> None:
    assert "G1" not in rules(GOOD.replace("$1,840.00", amount))


@pytest.mark.parametrize("after", [", which", ". Thanks", ") ok", "; and", "!"])
def test_g1_reads_amount_followed_by_punctuation(after: str) -> None:
    assert "G1" not in rules(GOOD.replace("$1,840.00 was", "$1,840.00" + after + " was"))


@pytest.mark.parametrize("amount", ["$1,804.00", "$18,400.00", "$184.00", "$1,840.50"])
def test_g1_blocks_wrong_amount(amount: str) -> None:
    assert "G1" in rules(GOOD.replace("$1,840.00", amount))


def test_g1_requires_the_balance_and_invoice_number() -> None:
    assert "G1" in rules(GOOD.replace(" for $1,840.00", ""))
    assert "G1" in rules(GOOD.replace("invoice #1042", "your invoice"), subject="Reminder")


def test_g1_blocks_wrong_invoice_number() -> None:
    assert "G1" in rules(GOOD.replace("#1042", "#1024"))


@pytest.mark.parametrize("ref", ["Invoice INV-1042", "invoice no. 1042", "Invoice number 1042"])
def test_g1_accepts_invoice_number_formats(ref: str) -> None:
    assert "G1" not in rules(GOOD.replace("invoice #1042", ref))


@pytest.mark.parametrize(
    "d", ["Nov 1, 2026", "2026-11-01", "11/01/2026", "November 1st", "1 November 2026"]
)
def test_g1_accepts_reformatted_correct_due_date(d: str) -> None:
    assert "G1" not in rules(GOOD.replace("November 1, 2026", d))


@pytest.mark.parametrize("d", ["November 11, 2026", "2026-11-10", "10/01/2026", "January 15"])
def test_g1_blocks_wrong_date(d: str) -> None:
    assert "G1" in rules(GOOD.replace("November 1, 2026", d))


def test_g1_blocks_wrong_days_overdue() -> None:
    assert "G1" in rules(GOOD.replace("21 days past due", "45 days past due"))


def test_g1_partial_payment_amounts_are_facts() -> None:
    body = (
        "Hi Cobalt Dental, thanks for your payment of $2,000.00 toward invoice #1044 "
        "($3,200.00). The remaining $1,200.00 was due November 14, 2026. Thanks, Sam"
    )
    assert rules(body, case=COBALT, subject="Invoice #1044") == set()


# --- G2: no promises the business didn't authorise ---


@pytest.mark.parametrize(
    "phrase",
    [
        "we can offer a 10% discount",
        "we'll waive the late fee",
        "we may refer this to a collections agency",
        "our attorney will be in touch",
        "we will take legal action",
        "we can set up a payment plan",
        "pay in installments",
        "consider it cancelled",
    ],
)
def test_g2_blocks_unauthorised_promises(phrase: str) -> None:
    assert "G2" in rules(GOOD + " " + phrase)


def test_g2_payment_plan_allowed_when_policy_says_so() -> None:
    assert "G2" not in rules(
        GOOD + " We can set up a payment plan.", policy=Policy(allow_payment_plan=True)
    )


# --- G3: never draft for paid, disputed or not-yet-due invoices ---


@pytest.mark.parametrize("doc", ["1046", "1047", "1048"])
def test_g3_blocks_drafts_for_holds(doc: str) -> None:
    case = CASES[doc]
    body = f"Invoice #{case.invoice.doc_number} for ${case.invoice.balance:,.2f}."
    assert "G3" in rules(body, case=case, subject=f"Invoice {case.invoice.doc_number}")


# --- G4: no links, other contact routes or payment details ---


@pytest.mark.parametrize(
    "extra",
    [
        "Pay at https://pay-now.example/acme",
        "Pay at www.pay-now.example",
        "Email payments@other.example",
        "Wire it to account 12345678901",
        "Our routing number is on file",
    ],
)
def test_g4_blocks_links_contacts_and_bank_details(extra: str) -> None:
    assert "G4" in rules(GOOD + " " + extra)


def test_g4_allows_the_business_reply_email() -> None:
    assert "G4" not in rules(GOOD)


# --- hardening (security review, slice 1) ---


@pytest.mark.parametrize(
    "extra",
    [
        "Email sam at northwind dot com",
        "Reach us at pay-now[.]com",
        "Visit pay-now.com",
        "Visit pay‐now.com",
        "go to hxxps://pay-now",
        "[pay here](pay-now.example)",
        "Call 555-123-4567",
        "Call (555) 123 4567",
        "billing@north​wind.example",
    ],
)
def test_g4_blocks_disguised_contacts_and_links(extra: str) -> None:
    assert "G4" in rules(GOOD + " " + extra)


@pytest.mark.parametrize(
    "extra",
    ["We'll accept eighteen hundred dollars.", "Just send 1500 dollars.", "Pay ＄1,500.00 now"],
)
def test_g1_blocks_amounts_in_words_or_full_width(extra: str) -> None:
    assert "G1" in rules(GOOD + " " + extra)


def test_g1_blocks_two_digit_year_wrong_date() -> None:
    assert "G1" in rules(GOOD.replace("November 1, 2026", "11/10/26"))


def test_g1_accepts_two_digit_year_right_date() -> None:
    assert "G1" not in rules(GOOD.replace("November 1, 2026", "11/1/26"))


@pytest.mark.parametrize(
    "phrase",
    ["or we'll use a debt collector", "we may garnish", "we will report you", "a penalty applies"],
)
def test_g2_blocks_more_threats(phrase: str) -> None:
    assert "G2" in rules(GOOD + " " + phrase)


def test_zero_width_characters_cannot_hide_a_promise() -> None:
    assert "G2" in rules(GOOD + " we offer a dis​count")


# --- false-positive fixes (code review, slice 1) ---


@pytest.mark.parametrize(
    "extra",
    [
        "Please reply by November 29, 2026.",  # deadline after as_of
        "We'd appreciate your swift attention.",
        "Thanks for routing this to your AP team.",
    ],
)
def test_reasonable_phrases_do_not_trip_the_guardrail(extra: str) -> None:
    assert rules(GOOD + " " + extra) == set()


def test_deadline_too_far_ahead_is_still_blocked() -> None:
    assert "G1" in rules(GOOD + " Please pay by March 1, 2027.")


def test_payment_date_from_the_record_is_allowed() -> None:
    body = (
        "Hi Cobalt Dental, thanks for your payment of $2,000.00 on November 12, 2026 toward "
        "invoice #1044. The remaining $1,200.00 was due November 14, 2026. Thanks, Sam"
    )
    assert rules(body, case=COBALT, subject="Invoice #1044") == set()


def test_invoice_followed_by_days_is_not_an_invoice_number() -> None:
    assert "G1" not in rules(GOOD + " This invoice 21 days overdue needs attention.")


@pytest.mark.parametrize("extra", ["Our SWIFT code is on file.", "Use routing number 0210"])
def test_bank_terms_still_blocked(extra: str) -> None:
    assert "G4" in rules(GOOD + " " + extra)


def test_zero_paid_so_far_is_a_true_fact() -> None:
    # Found in the slice 7 dev run: models write "Paid so far: USD 0.00".
    assert "G1" not in rules(GOOD + " Paid so far: USD 0.00.")
