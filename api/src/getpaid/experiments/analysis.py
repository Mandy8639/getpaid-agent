"""Difference in proportions with a Newcombe-Wilson 95% CI, reported without overclaiming."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any

Z95 = 1.959963984540054
SMALL_N = 100


def _wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + Z95**2 / n
    centre = (p + Z95**2 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95**2 / (4 * n * n)) / denom
    return (centre - half, centre + half)


@dataclass(frozen=True)
class Comparison:
    n_a: int
    n_b: int
    rate_a: float
    rate_b: float
    diff: float  # rate_b - rate_a
    ci_low: float
    ci_high: float
    p_value: float
    significant: bool
    verdict: str


def compare_proportions(a: list[bool], b: list[bool]) -> Comparison:
    """B minus A. Significant only when the 95% CI excludes zero."""
    n_a, n_b, k_a, k_b = len(a), len(b), sum(a), sum(b)
    if n_a == 0 or n_b == 0:
        raise ValueError("both arms need data")
    p_a, p_b = k_a / n_a, k_b / n_b
    l_a, u_a = _wilson(k_a, n_a)
    l_b, u_b = _wilson(k_b, n_b)
    d = p_b - p_a
    low = d - math.sqrt((p_b - l_b) ** 2 + (u_a - p_a) ** 2)
    high = d + math.sqrt((u_b - p_b) ** 2 + (p_a - l_a) ** 2)
    pooled = (k_a + k_b) / (n_a + n_b)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b)) or 1e-12
    p_value = math.erfc(abs(d) / se / math.sqrt(2))
    significant = low > 0 or high < 0
    if significant:
        verdict = f"B − A = {d:+.1%} (95% CI {low:+.1%} to {high:+.1%})"
    else:
        verdict = f"no detectable difference: B − A = {d:+.1%} (95% CI {low:+.1%} to {high:+.1%})"
    if min(n_a, n_b) < SMALL_N:
        verdict += f"; small sample (n = {n_a} vs {n_b}), treat as indicative only"
    return Comparison(n_a, n_b, p_a, p_b, d, low, high, p_value, significant, verdict)


def _welch_log(a: list[float], b: list[float]) -> dict[str, float]:
    """Difference (B − A) in mean log-seconds with a 95% CI (normal approximation)."""
    la = [math.log(x) for x in a if x and x > 0]
    lb = [math.log(x) for x in b if x and x > 0]
    d = statistics.mean(lb) - statistics.mean(la)
    se = math.sqrt(statistics.variance(la) / len(la) + statistics.variance(lb) / len(lb))
    return {"diff": d, "ci_low": d - Z95 * se, "ci_high": d + Z95 * se}


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Decision metrics use approved/skipped events only; rejected edits feed the guardrail."""
    decided: dict[str, list[dict[str, Any]]] = {"show": [], "hide": []}
    rejected = {"show": 0, "hide": 0}
    for e in events:
        if e["type"] == "rejected_edit":
            rejected[e["arm"]] += 1
        else:
            decided[e["arm"]].append(e)

    def clean(es: list[dict[str, Any]]) -> list[bool]:
        return [e["type"] == "approved" and not e["edited"] for e in es]

    secs = {arm: [e["seconds"] for e in es if e.get("seconds")] for arm, es in decided.items()}
    return {
        "simulated": all(e.get("simulated") for e in events),
        "owners": len({e["owner_id"] for e in events}),
        "decisions": {arm: len(es) for arm, es in decided.items()},
        "primary": compare_proportions(clean(decided["show"]), clean(decided["hide"])),
        "median_seconds": {arm: statistics.median(v) for arm, v in secs.items() if v},
        "log_seconds": _welch_log(secs["show"], secs["hide"])
        if len(secs["show"]) > 1 and len(secs["hide"]) > 1
        else None,
        "skip_rate": {
            arm: sum(e["type"] == "skipped" for e in es) / len(es)
            for arm, es in decided.items()
            if es
        },
        "rejected_edits_per_100": {
            arm: 100 * rejected[arm] / len(es) for arm, es in decided.items() if es
        },
    }
