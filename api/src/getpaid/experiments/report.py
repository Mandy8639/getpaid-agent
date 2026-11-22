"""Run EXP-001 on SIMULATED owners and write reports/exp-001-simulated.md.

    uv run python -m getpaid.experiments.report

This checks the pipeline (assignment, event shape, analysis, wording), not real behaviour.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any

from getpaid.experiments.analysis import Z95, summarize
from getpaid.experiments.simulate import simulate

OUT = Path(__file__).resolve().parents[4] / "reports" / "exp-001-simulated.md"
OWNERS, DRAFTS_PER_OWNER, SEED, TRUE_EFFECT = 300, 10, 2026, 0.05


def owner_level(events: list[dict[str, Any]]) -> tuple[float, float, float]:
    """Difference (hide − show) in mean per-owner clean-approval rate, Welch 95% CI."""
    per: dict[str, list[bool]] = {}
    arm_of: dict[str, str] = {}
    for e in events:
        if e["type"] == "rejected_edit":
            continue
        per.setdefault(e["owner_id"], []).append(e["type"] == "approved" and not e["edited"])
        arm_of[e["owner_id"]] = e["arm"]
    rates = {
        arm: [sum(v) / len(v) for o, v in per.items() if arm_of[o] == arm]
        for arm in ("show", "hide")
    }
    m_s, m_h = statistics.mean(rates["show"]), statistics.mean(rates["hide"])
    se = math.sqrt(
        statistics.variance(rates["show"]) / len(rates["show"])
        + statistics.variance(rates["hide"]) / len(rates["hide"])
    )
    d = m_h - m_s
    return d, d - Z95 * se, d + Z95 * se


def power(reps: int = 100) -> float:
    """Share of simulated runs (same design) whose per-owner CI excludes zero."""
    hits = 0
    for r in range(reps):
        ev = simulate(
            owners=OWNERS,
            drafts_per_owner=DRAFTS_PER_OWNER,
            seed=10_000 + r,
            true_effect=TRUE_EFFECT,
        )
        _, lo, hi = owner_level(ev)
        hits += hi < 0 or lo > 0
    return hits / reps


def render(events: list[dict[str, Any]], power_line: str = "not estimated") -> str:
    s = summarize(events)
    p = s["primary"]
    d, lo, hi = owner_level(events)
    rej = s["rejected_edits_per_100"]
    ls = s["log_seconds"]
    guard_ok = rej["hide"] <= rej["show"]
    covered = "inside" if lo <= -TRUE_EFFECT <= hi else "outside"
    return f"""# EXP-001 on SIMULATED owners

**SIMULATED DATA.** {s["owners"]} scripted owners, {DRAFTS_PER_OWNER} drafts each, seed {SEED}.
The simulation builds in a true effect of {-TRUE_EFFECT * 100:+.0f} points for `hide` (B) versus
`show` (A) on the primary metric. This report checks that the pipeline recovers a known effect
and words the result honestly. It says nothing about real owners. Pre-registration:
`docs/experiments/EXP-001-history-panel.md`.

| | A `show` | B `hide` |
|---|---|---|
| decisions | {s["decisions"]["show"]} | {s["decisions"]["hide"]} |
| approved without edits | {p.rate_a:.1%} | {p.rate_b:.1%} |
| skip rate | {s["skip_rate"]["show"]:.1%} | {s["skip_rate"]["hide"]:.1%} |
| median seconds to decide | {s["median_seconds"]["show"]:.1f} | {s["median_seconds"]["hide"]:.1f} |
| rejected edits per 100 drafts (guardrail) | {rej["show"]:.1f} | {rej["hide"]:.1f} |

**Primary (per draft):** {p.verdict}; two-sided p = {p.p_value:.3g}.

**Primary (per owner, the unit of assignment):** B − A = {d:+.1%} (95% CI {lo:+.1%} to {hi:+.1%}).
The per-owner interval is wider because decisions by the same owner are correlated; it is the
one to trust. The built-in effect ({-TRUE_EFFECT * 100:+.0f} points) is {covered} it.

**Time to decide (secondary):** B − A in mean log-seconds = {ls["diff"]:+.3f} (95% CI
{ls["ci_low"]:+.3f} to {ls["ci_high"]:+.3f}), i.e. B is about {(math.exp(ls["diff"]) - 1):+.0%} in
typical decision time.

**Power (what this run teaches):** {power_line}
The pre-registered sample size (about 1,500 drafts per arm) assumed independent drafts. Owners
differ from each other, so the effective sample is closer to the number of owners than the
number of drafts. A real run needs more owners (or the power target re-derived with the
owner-level variance) before its result is trusted.

**Decision under the pre-registered rule:** ship `hide` only if B's lower bound is above −2
points *and* the guardrail holds. Lower bound {lo * 100:+.1f} points
({"fails" if lo <= -0.02 else "passes"}); guardrail {"holds" if guard_ok else "fails"}
({rej["hide"]:.1f} vs {rej["show"]:.1f} rejected edits per 100). Result:
{"keep show" if lo <= -0.02 or not guard_ok else "hide may ship"}.

The live dashboard has a single demo owner (arm `{"show"}`) until login exists, so no real
comparison is possible yet.
"""


def main() -> None:  # pragma: no cover - CLI
    events = simulate(
        owners=OWNERS, drafts_per_owner=DRAFTS_PER_OWNER, seed=SEED, true_effect=TRUE_EFFECT
    )
    OUT.parent.mkdir(exist_ok=True)
    pw = power()
    line = (
        f"in 100 repeat simulations of this design ({OWNERS} owners × {DRAFTS_PER_OWNER} drafts, "
        f"true effect {-TRUE_EFFECT * 100:+.0f} points), the per-owner CI excluded zero "
        f"{pw:.0%} of the time."
    )
    OUT.write_text(render(events, line))
    print(OUT.read_text())


if __name__ == "__main__":  # pragma: no cover
    main()
