# EXP-001 on SIMULATED owners

**SIMULATED DATA.** 300 scripted owners, 10 drafts each, seed 2026.
The simulation builds in a true effect of -5 points for `hide` (B) versus
`show` (A) on the primary metric. This report checks that the pipeline recovers a known effect
and words the result honestly. It says nothing about real owners. Pre-registration:
`docs/experiments/EXP-001-history-panel.md`.

| | A `show` | B `hide` |
|---|---|---|
| decisions | 1530 | 1470 |
| approved without edits | 60.1% | 58.8% |
| skip rate | 13.3% | 13.2% |
| median seconds to decide | 24.7 | 22.0 |
| rejected edits per 100 drafts (guardrail) | 3.9 | 4.2 |

**Primary (per draft):** no detectable difference: B − A = -1.2% (95% CI -4.7% to +2.3%); two-sided p = 0.496.

**Primary (per owner, the unit of assignment):** B − A = -1.2% (95% CI -5.4% to +2.9%).
The per-owner interval is wider because decisions by the same owner are correlated; it is the
one to trust. The built-in effect (-5 points) is inside it.

**Time to decide (secondary):** B − A in mean log-seconds = -0.125 (95% CI
-0.161 to -0.090), i.e. B is about -12% in
typical decision time.

**Power (what this run teaches):** in 100 repeat simulations of this design (300 owners × 10 drafts, true effect -5 points), the per-owner CI excluded zero 74% of the time.
The pre-registered sample size (about 1,500 drafts per arm) assumed independent drafts. Owners
differ from each other, so the effective sample is closer to the number of owners than the
number of drafts. A real run needs more owners (or the power target re-derived with the
owner-level variance) before its result is trusted.

**Decision under the pre-registered rule:** ship `hide` only if B's lower bound is above −2
points *and* the guardrail holds. Lower bound -5.4 points
(fails); guardrail fails
(4.2 vs 3.9 rejected edits per 100). Result:
keep show.

The live dashboard has a single demo owner (arm `show`) until login exists, so no real
comparison is possible yet.
