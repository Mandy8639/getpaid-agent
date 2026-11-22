"""LangGraph flow: decide → draft → guardrail → queue, or repair once with feedback, or hold."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict, cast

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from getpaid.agent.decide import decide
from getpaid.agent.drafter import Drafter
from getpaid.agent.guardrail import RULE_HINTS, Draft, Violation, check
from getpaid.domain import Action, Case, Decision, HoldReason, Policy, Tone

MAX_TRIES = 2


class State(TypedDict, total=False):
    case: Case
    policy: Policy
    decision: Decision
    draft: Draft | None
    violations: list[Violation]
    tries: int
    model: str
    cost_usd: float
    hold_reason: HoldReason | None


@dataclass
class RunResult:
    case: Case
    action: Action
    tone: Tone | None
    draft: Draft | None
    hold_reason: HoldReason | None
    violations: list[Violation] = field(default_factory=list)
    tries: int = 0
    model: str = ""
    cost_usd: float = 0.0


def build_graph(drafter: Drafter) -> CompiledStateGraph[State, None, State, State]:
    def decide_node(state: State) -> State:
        d = decide(state["case"])
        return {"decision": d, "tries": 0, "cost_usd": 0.0, "hold_reason": d.hold_reason}

    def draft_node(state: State) -> State:
        # Generic hints per broken rule: never echo draft or record text back to the model.
        feedback = [RULE_HINTS[r] for r in sorted({v.rule for v in state.get("violations", [])})]
        out = drafter.draft(state["case"], state["decision"], state["policy"], feedback)
        return {
            "draft": out.draft,
            "tries": state["tries"] + 1,
            "model": out.model,
            "cost_usd": state["cost_usd"] + out.cost_usd,
        }

    def guard_node(state: State) -> State:
        draft = state.get("draft")
        if draft is None:
            return {"hold_reason": HoldReason.DRAFTER_FAILED}
        violations = check(draft, state["case"], state["policy"]).violations
        if violations and state["tries"] >= MAX_TRIES:
            return {"violations": violations, "hold_reason": HoldReason.GUARDRAIL_BLOCKED}
        return {"violations": violations}

    def after_decide(state: State) -> str:
        return "draft" if state["decision"].action is Action.DRAFT else END

    def after_guard(state: State) -> str:
        if state.get("hold_reason") or not state.get("violations"):
            return END
        return "draft"

    g = StateGraph(State)
    g.add_node("decide", decide_node)
    g.add_node("draft", draft_node)
    g.add_node("guard", guard_node)
    g.set_entry_point("decide")
    g.add_conditional_edges("decide", after_decide, {"draft": "draft", END: END})
    g.add_edge("draft", "guard")
    g.add_conditional_edges("guard", after_guard, {"draft": "draft", END: END})
    return g.compile()


def run_case(case: Case, policy: Policy, drafter: Drafter) -> RunResult:
    s = cast(State, build_graph(drafter).invoke({"case": case, "policy": policy}))
    hold = s.get("hold_reason")
    return RunResult(
        case=case,
        action=Action.HOLD if hold else Action.DRAFT,
        tone=s["decision"].tone,
        draft=s.get("draft"),
        hold_reason=hold,
        violations=s.get("violations", []),
        tries=s.get("tries", 0),
        model=s.get("model", ""),
        cost_usd=s.get("cost_usd", 0.0),
    )
