"""Experiments: sticky assignment, analysis with honest CIs, simulated owners (labelled)."""

import random

import pytest

from getpaid.experiments.analysis import compare_proportions, summarize
from getpaid.experiments.assign import EXP_001, Experiment, assign
from getpaid.experiments.simulate import simulate

# --- assignment ---


def test_assignment_is_sticky_and_deterministic() -> None:
    assert all(assign("owner-42", EXP_001) == assign("owner-42", EXP_001) for _ in range(5))


def test_assignment_is_balanced_at_scale() -> None:
    arms = [assign(f"o{i}", EXP_001) for i in range(10_000)]
    share = arms.count("show") / len(arms)
    assert 0.48 < share < 0.52


def test_weights_are_honoured() -> None:
    exp = Experiment("EXP-W", ("a", "b"), (0.9, 0.1))
    arms = [assign(f"o{i}", exp) for i in range(10_000)]
    assert 0.88 < arms.count("a") / len(arms) < 0.92


def test_different_experiments_assign_independently() -> None:
    other = Experiment("EXP-OTHER", ("show", "hide"), (0.5, 0.5))
    same = sum(assign(f"o{i}", EXP_001) == assign(f"o{i}", other) for i in range(10_000))
    assert 0.47 < same / 10_000 < 0.53


def test_bad_experiment_definitions_are_rejected() -> None:
    with pytest.raises(ValueError):
        Experiment("X", ("a", "b"), (0.5,))
    with pytest.raises(ValueError):
        Experiment("X", ("a", "b"), (0.7, 0.7))


# --- analysis ---


def _draws(p: float, n: int, seed: int) -> list[bool]:
    rng = random.Random(seed)
    return [rng.random() < p for _ in range(n)]


def test_recovers_a_known_effect_with_a_ci_that_covers_it() -> None:
    r = compare_proportions(_draws(0.50, 5000, 1), _draws(0.60, 5000, 2))
    assert r.significant
    assert r.ci_low < 0.10 < r.ci_high
    assert r.ci_low > 0


def test_false_positive_rate_is_close_to_five_percent_under_no_effect() -> None:
    hits = sum(
        compare_proportions(_draws(0.6, 1500, s), _draws(0.6, 1500, s + 10_000)).significant
        for s in range(400)
    )
    assert 0.02 <= hits / 400 <= 0.08


def test_no_effect_is_worded_as_no_detectable_difference() -> None:
    r = compare_proportions([True, False] * 750, [True, False] * 750)
    assert not r.significant and r.ci_low < 0 < r.ci_high
    assert r.verdict.startswith("no detectable difference")


def test_small_samples_are_flagged() -> None:
    r = compare_proportions(_draws(0.6, 20, 5), _draws(0.6, 20, 6))
    assert "small sample" in r.verdict


# --- simulated owners ---


def test_simulation_is_deterministic_and_labelled() -> None:
    a = simulate(owners=200, drafts_per_owner=15, seed=7)
    assert a == simulate(owners=200, drafts_per_owner=15, seed=7)
    assert all(e["simulated"] is True for e in a)
    assert {e["arm"] for e in a} == {"show", "hide"}


def test_each_simulated_owner_stays_in_one_arm() -> None:
    events = simulate(owners=100, drafts_per_owner=10, seed=1)
    by_owner: dict[str, set[str]] = {}
    for e in events:
        by_owner.setdefault(e["owner_id"], set()).add(e["arm"])
    assert all(len(v) == 1 for v in by_owner.values())


def test_summary_recovers_the_simulated_effect() -> None:
    events = simulate(owners=300, drafts_per_owner=10, seed=3, true_effect=0.08)
    s = summarize(events)
    assert s["primary"].significant
    assert s["primary"].ci_low < -0.08 < s["primary"].ci_high  # B (hide) minus A (show)
    assert s["owners"] == 300 and s["simulated"] is True


def test_report_is_labelled_simulated_and_reports_owner_level_ci() -> None:
    from getpaid.experiments.report import owner_level, render

    events = simulate(owners=200, drafts_per_owner=10, seed=9, true_effect=0.05)
    text = render(events)
    assert text.startswith("# EXP-001 on SIMULATED owners") and "SIMULATED DATA" in text
    assert "per owner" in text and "says nothing about real owners" in text
    d, lo, hi = owner_level(events)
    assert lo < d < hi


# --- slice 6 review ---


def test_rejected_edit_events_are_not_counted_as_decisions() -> None:
    live = [
        {"owner_id": "o1", "arm": "show", "type": "rejected_edit", "edited": True, "seconds": 5.0},
        {"owner_id": "o1", "arm": "show", "type": "approved", "edited": True, "seconds": 9.0},
        {"owner_id": "o2", "arm": "hide", "type": "approved", "edited": False, "seconds": 7.0},
        {"owner_id": "o2", "arm": "hide", "type": "skipped", "edited": False, "seconds": 3.0},
    ]
    s = summarize(live)
    assert s["decisions"] == {"show": 1, "hide": 2}
    assert s["rejected_edits_per_100"] == {"show": 100.0, "hide": 0.0}


def test_simulation_emits_the_live_event_shape() -> None:
    events = simulate(owners=200, drafts_per_owner=10, seed=4)
    assert {e["type"] for e in events} == {"approved", "skipped", "rejected_edit"}
    assert all("rejected_edit" not in e for e in events)


def test_time_to_decide_has_a_welch_log_seconds_comparison() -> None:
    s = summarize(simulate(owners=300, drafts_per_owner=10, seed=5))
    t = s["log_seconds"]
    assert t["ci_low"] < t["diff"] < t["ci_high"]
    assert t["diff"] < 0  # simulated "hide" owners decide a little faster
