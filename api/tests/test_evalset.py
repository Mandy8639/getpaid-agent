"""Frozen eval set: snapshot round-trip, labels from ground truth, customer-level split, hash."""

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from getpaid.data.source import FixtureSource
from getpaid.domain import Action, HoldReason, Tone
from getpaid.evalset import (
    Scenario,
    case_from_dict,
    case_to_dict,
    expected_for,
    freeze,
    load,
    split_by_customer,
    variants,
    verify_frozen,
)

AS_OF = date(2026, 11, 22)
CASES = FixtureSource().cases(AS_OF)


def test_case_snapshot_round_trips_exactly() -> None:
    for c in CASES:
        assert case_from_dict(json.loads(json.dumps(case_to_dict(c)))) == c


@pytest.mark.parametrize(
    ("kind", "disputed", "action", "reason"),
    [
        ("overdue", False, Action.DRAFT, None),
        ("partial", False, Action.DRAFT, None),
        ("not_due", False, Action.HOLD, HoldReason.NOT_OVERDUE),
        ("paid_recent", False, Action.HOLD, HoldReason.PAID),
        ("overdue", True, Action.HOLD, HoldReason.DISPUTED),
    ],
)
def test_expected_labels_come_from_seed_ground_truth(
    kind: str, disputed: bool, action: Action, reason: HoldReason | None
) -> None:
    case = replace(CASES[0], disputed=disputed)
    exp = expected_for(case, kind)
    assert exp["action"] == action.value
    assert exp["hold_reason"] == (reason.value if reason else None)


def test_expected_tone_and_facts_for_a_draft() -> None:
    acme = next(c for c in CASES if c.invoice.doc_number == "1042")
    exp = expected_for(acme, "overdue")
    assert exp["tone"] == Tone.FRIENDLY_NUDGE.value
    assert exp["must_mention"] == {"invoice_number": "1042", "balance": "1840.00"}


def test_variants_add_injections_name_attacks_and_edge_holds() -> None:
    base = [c for c in CASES if c.days_overdue > 0 and c.invoice.balance > 0 and not c.disputed]
    vs = variants(base, AS_OF)
    cats = [v.category for v in vs]
    assert cats.count("injection") == 5
    assert cats.count("name_attack") == 3
    assert cats.count("edge_hold") == 2
    assert all(v.source == "variant" for v in vs)
    due_today = next(v for v in vs if v.category == "edge_hold" and v.case.days_overdue == 0)
    assert due_today.expect["action"] == "hold"


def _scen(i: int, cust: str, cat: str = "draft_friendly") -> Scenario:
    c = replace(CASES[0], customer=replace(CASES[0].customer, id=cust))
    return Scenario(f"s{i}", "unsplit", cat, "sandbox", c, expected_for(c, "overdue"))


def test_split_keeps_each_customer_on_one_side_and_hits_target_sizes() -> None:
    scen = [_scen(i, f"cust{i // 2}") for i in range(80)]
    dev, test = split_by_customer(scen, dev_size=30, seed=1)
    assert len(dev) + len(test) == 80
    assert 28 <= len(dev) <= 32
    assert not {s.case.customer.id for s in dev} & {s.case.customer.id for s in test}
    assert {s.split for s in dev} == {"dev"} and {s.split for s in test} == {"test"}


def test_freeze_writes_hash_and_detects_tampering(tmp_path: Path) -> None:
    scen = [_scen(i, f"c{i}") for i in range(4)]
    path = tmp_path / "test.jsonl"
    path.write_text("".join(json.dumps(s.to_dict()) + "\n" for s in scen))
    freeze(path, tmp_path / "FROZEN.json")
    verify_frozen(path, tmp_path / "FROZEN.json")
    assert [s.id for s in load(path)] == ["s0", "s1", "s2", "s3"]
    path.write_text(path.read_text().replace("1840.00", "1840.01"))
    with pytest.raises(ValueError, match="changed"):
        verify_frozen(path, tmp_path / "FROZEN.json")


def test_scenario_money_survives_serialisation() -> None:
    s = _scen(0, "c0")
    back = Scenario.from_dict(json.loads(json.dumps(s.to_dict())))
    assert back.case.invoice.balance == Decimal("1840.00")
    assert back == s


# --- the committed, frozen eval set ---

GOLDEN = Path(__file__).resolve().parents[2] / "golden"


def test_committed_test_set_matches_its_frozen_hash() -> None:
    verify_frozen(GOLDEN / "test.jsonl", GOLDEN / "FROZEN.json")


def test_committed_splits_share_no_customers_and_have_expected_sizes() -> None:
    dev, test = load(GOLDEN / "dev.jsonl"), load(GOLDEN / "test.jsonl")
    assert (len(dev), len(test)) == (30, 50)
    assert not {s.case.customer.id for s in dev} & {s.case.customer.id for s in test}
    assert sum(s.category in {"injection", "name_attack"} for s in dev + test) == 11


def test_no_test_scenario_text_leaks_into_prompts_or_dev_set() -> None:
    from getpaid.agent.drafter import SYSTEM, TONE_GUIDE

    prompt_text = SYSTEM + " ".join(TONE_GUIDE.values())
    dev_invoices = {s.case.invoice.doc_number for s in load(GOLDEN / "dev.jsonl")}
    for s in load(GOLDEN / "test.jsonl"):
        assert s.case.invoice.doc_number not in prompt_text
        assert s.case.customer.display_name not in prompt_text
        assert s.case.invoice.doc_number not in dev_invoices
