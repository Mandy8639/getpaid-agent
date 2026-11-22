"""SIMULATED owners for exercising the experiment pipeline. Not evidence about real people.

Each simulated owner has their own baseline (some edit a lot, some rarely), is assigned an arm
by the real assignment function, and makes decisions on a run of drafts. `true_effect` is how
much more often owners in "show" approve without editing; the analysis should recover it.
"""

from __future__ import annotations

import math
import random
from typing import Any

from getpaid.experiments.assign import EXP_001, assign


def simulate(
    *,
    owners: int,
    drafts_per_owner: int,
    seed: int,
    base_rate: float = 0.60,
    true_effect: float = 0.05,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)  # noqa: S311 - simulation, not security
    events: list[dict[str, Any]] = []
    for i in range(owners):
        owner = f"sim-owner-{i:04d}"
        arm = assign(owner, EXP_001)
        owner_bias = rng.gauss(0, 0.08)
        p_clean = min(
            0.98, max(0.02, base_rate + owner_bias - (0 if arm == "show" else true_effect))
        )
        for k in range(drafts_per_owner):
            if rng.random() < p_clean:
                kind, edited, rejected = "approved", False, False
            else:
                r = rng.random()
                kind = "skipped" if r < 0.3 else "approved"
                edited = kind == "approved"
                rejected = edited and r > 0.9
            seconds = math.exp(rng.gauss(math.log(25 if arm == "show" else 22), 0.5))
            base = {
                "experiment_id": EXP_001.id,
                "owner_id": owner,
                "arm": arm,
                "draft_seq": k,
                "simulated": True,
            }
            if rejected:  # same shape as the live API: a separate event before the decision
                events.append({**base, "type": "rejected_edit", "edited": True, "seconds": None})
            events.append({**base, "type": kind, "edited": edited, "seconds": round(seconds, 2)})
    return events
