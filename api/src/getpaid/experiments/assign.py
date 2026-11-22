"""Sticky, weighted experiment assignment: hash(experiment id, owner id) -> arm."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Experiment:
    id: str
    arms: tuple[str, ...]
    weights: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.arms) != len(self.weights) or len(self.arms) < 2:
            raise ValueError("an experiment needs 2+ arms and one weight per arm")
        if abs(sum(self.weights) - 1.0) > 1e-9 or min(self.weights) <= 0:
            raise ValueError("weights must be positive and sum to 1")


# Pre-registered in docs/experiments/EXP-001-history-panel.md. A ("show") is the control.
EXP_001 = Experiment("EXP-001", ("show", "hide"), (0.5, 0.5))
EXPERIMENTS = {EXP_001.id: EXP_001}


def assign(owner_id: str, exp: Experiment) -> str:
    digest = hashlib.sha256(f"{exp.id}:{owner_id}".encode()).hexdigest()
    u = int(digest[:15], 16) / 16**15  # uniform in [0, 1)
    edge = 0.0
    for arm, w in zip(exp.arms, exp.weights, strict=True):
        edge += w
        if u < edge:
            return arm
    return exp.arms[-1]
