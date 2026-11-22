"""FastAPI app: run the agent over invoices, list drafts, record the owner's decision."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from getpaid.agent.decide import decide
from getpaid.agent.drafter import Drafter, LLMDrafter, TemplateDrafter
from getpaid.agent.graph import RunResult, run_case
from getpaid.agent.guardrail import Draft, check
from getpaid.agent.qa import (
    MAX_QUESTION,
    Asker,
    LLMAsker,
    QuestionError,
    ask,
    validate_question,
)
from getpaid.data.mcp_source import McpSource
from getpaid.data.source import DataSource, FixtureSource
from getpaid.db import approvals, drafts, make_engine, migrate
from getpaid.domain import Action, Case, HoldReason, Policy
from getpaid.evalset import case_from_dict, case_to_dict
from getpaid.llm.openrouter import SpendCapReached

log = logging.getLogger("getpaid")

Status = Literal["pending", "held", "approved", "skipped"]


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION)


class AskOut(BaseModel):
    answer: str
    source: Literal["model", "fallback", "refused"]
    rows: list[dict[str, Any]]
    summary: dict[str, Any]


class DecisionIn(BaseModel):
    decision: Literal["approve", "skip"]
    # Optional owner edits; on approve the edited text must pass the guardrail again.
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=4000)

    @field_validator("subject", "body")
    @classmethod
    def not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("must not be blank")
        return v

    @field_validator("subject")
    @classmethod
    def one_line(cls, v: str | None) -> str | None:
        # A future email sender must never get header-like line breaks in the subject.
        if v is not None and ("\r" in v or "\n" in v):
            raise ValueError("subject must be a single line")
        return v


class History(BaseModel):
    total: str
    paid_so_far: str
    payment_dates: list[str]
    prior_late_payments: int
    txn_date: str
    due_date: str


class ActivityOut(BaseModel):
    draft_id: int
    invoice_number: str
    customer_name: str
    decision: Literal["approve", "skip"]
    label: Literal["Ready to send", "Skipped"]
    edited: bool
    final_subject: str | None
    decided_at: str


class DraftOut(BaseModel):
    id: int
    invoice_number: str
    customer_name: str
    balance: str
    days_overdue: int
    tone: str | None
    subject: str | None
    body: str | None
    status: Status
    hold_reason: str | None
    violations: list[dict[str, str]]
    guardrail_passed: bool
    tries: int
    model: str | None
    history: History | None = None
    final_subject: str | None = None
    final_body: str | None = None
    edited: bool = False


def _history(snapshot: dict[str, Any] | None) -> History | None:
    if not snapshot:
        return None
    try:
        return History(
            total=snapshot["invoice"]["total"],
            paid_so_far=snapshot["paid_so_far"],
            payment_dates=snapshot["payment_dates"],
            prior_late_payments=snapshot["prior_late_payments"],
            txn_date=snapshot["invoice"]["txn_date"],
            due_date=snapshot["invoice"]["due_date"],
        )
    except (KeyError, TypeError, ValueError):
        log.warning("draft snapshot has an unexpected shape; history omitted")
        return None


def _out(row: Any) -> DraftOut:
    m = row._mapping
    return DraftOut(
        id=m["id"],
        invoice_number=m["invoice_number"],
        customer_name=m["customer_name"],
        balance=str(m["balance"]),
        days_overdue=m["days_overdue"],
        tone=m["tone"],
        subject=m["subject"],
        body=m["body"],
        status=m["status"],
        hold_reason=m["hold_reason"],
        violations=m["violations"] or [],
        guardrail_passed=not (m["violations"] or []),
        tries=m["tries"],
        model=m["model"],
        history=_history(m.get("case_snapshot")),
        final_subject=m.get("final_subject"),
        final_body=m.get("final_body"),
        edited=bool(m.get("edited") or False),
    )


_WITH_DECISION = drafts.outerjoin(approvals, approvals.c.draft_id == drafts.c.id)
_DRAFT_COLS = [
    *drafts.c,
    approvals.c.final_subject,
    approvals.c.final_body,
    approvals.c.edited,
]


def _safe_run(case: Case, policy: Policy, drafter: Drafter) -> RunResult:
    """Run one case; a failing drafter or the spend cap holds that invoice, not the batch."""
    try:
        return run_case(case, policy, drafter)
    except SpendCapReached:
        reason = HoldReason.SPEND_CAP
    except Exception:  # noqa: BLE001 - any drafter failure becomes a visible hold
        log.exception("drafter failed for invoice %s", case.invoice.id)
        reason = HoldReason.DRAFTER_FAILED
    d = decide(case)
    return RunResult(case, Action.HOLD, d.tone, None, d.hold_reason or reason)


def _row(case: Case, r: RunResult) -> dict[str, Any]:
    return {
        "invoice_id": case.invoice.id,
        "invoice_number": case.invoice.doc_number,
        "customer_name": case.customer.display_name,
        "balance": case.invoice.balance,
        "days_overdue": case.days_overdue,
        "priority": case.invoice.balance * Decimal(max(case.days_overdue, 0)),
        "tone": r.tone.value if r.tone else None,
        "subject": r.draft.subject if r.draft else None,
        "body": r.draft.body if r.draft else None,
        "status": "pending" if r.action is Action.DRAFT else "held",
        "hold_reason": r.hold_reason.value if r.hold_reason else None,
        "violations": [{"rule": v.rule, "detail": v.detail} for v in r.violations],
        "tries": r.tries,
        "model": r.model or None,
        "case_snapshot": case_to_dict(case),
    }


def create_app(
    *,
    engine: Engine,
    source: DataSource,
    drafter: Drafter,
    policy: Policy,
    as_of: date | None = None,
    web_origin: str = "http://localhost:3000",
    asker: Asker | None = None,
) -> FastAPI:
    app = FastAPI(title="getpaid-agent API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[web_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def today() -> date:
        """Fixtures carry their own date; live data uses the real date at each run."""
        return as_of or getattr(source, "as_of", None) or date.today()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/runs")
    def run() -> dict[str, int]:
        with engine.connect() as c:
            seen = {
                (r.invoice_id, r.balance)
                for r in c.execute(select(drafts.c.invoice_id, drafts.c.balance))
            }
        # Draft outside any DB transaction: model calls can be slow or fail.
        rows = []
        for case in source.cases(today()):
            if (case.invoice.id, case.invoice.balance) in seen:
                continue
            rows.append(_row(case, _safe_run(case, policy, drafter)))
        counts = {"pending": 0, "held": 0}
        with engine.begin() as c:
            for row in rows:
                stmt = pg_insert(drafts).values(**row).on_conflict_do_nothing()
                if c.execute(stmt).rowcount:
                    counts[row["status"]] += 1
        return counts

    @app.get("/drafts")
    def list_drafts(status: Annotated[Status | None, Query()] = None) -> list[DraftOut]:
        q = (
            select(*_DRAFT_COLS)
            .select_from(_WITH_DECISION)
            .order_by(drafts.c.priority.desc(), drafts.c.id)
        )
        if status:
            q = q.where(drafts.c.status == status)
        with engine.connect() as c:
            return [_out(r) for r in c.execute(q)]

    @app.get("/drafts/next", response_model=None)
    def next_draft() -> DraftOut | Response:
        q = (
            select(*_DRAFT_COLS)
            .select_from(_WITH_DECISION)
            .where(drafts.c.status == "pending")
            .order_by(drafts.c.priority.desc(), drafts.c.id)
            .limit(1)
        )
        with engine.connect() as c:
            row = c.execute(q).first()
        return _out(row) if row else Response(status_code=204)

    @app.post("/ask")
    def ask_endpoint(body: AskIn) -> AskOut:
        if asker is None:
            raise HTTPException(
                503, "Q&A needs a model: set OPENROUTER_API_KEY and OPENROUTER_MODELS"
            )
        try:
            question = validate_question(body.question)
        except QuestionError as e:
            raise HTTPException(422, str(e)) from e
        try:
            cases = source.cases(today())
        except Exception as e:
            log.exception("data source failed for /ask")
            raise HTTPException(502, "couldn't read invoices from the data source") from e
        try:
            result = ask(question, cases, asker)
        except SpendCapReached as e:
            raise HTTPException(503, "the model spending limit has been reached") from e
        return AskOut(
            answer=result.answer, source=result.source, rows=result.rows, summary=result.summary
        )

    @app.post("/drafts/{draft_id}/decision")
    def decide_draft(draft_id: int, body: DecisionIn) -> DraftOut:
        approve = body.decision == "approve"
        with engine.begin() as c:
            current = c.execute(
                select(drafts).where(drafts.c.id == draft_id).with_for_update()
            ).first()
            if current is None:
                raise HTTPException(404, "draft not found")
            m = current._mapping
            if m["status"] != "pending":
                raise HTTPException(409, "draft is not pending")
            final_subject = final_body = None
            edited = False
            if approve:
                final_subject = body.subject if body.subject is not None else m["subject"]
                final_body = body.body if body.body is not None else m["body"]
                edited = (final_subject, final_body) != (m["subject"], m["body"])
                if edited and not m["case_snapshot"]:
                    # Drafts made before slice 5 have no stored facts to re-check edits against.
                    raise HTTPException(409, "edits aren't available for this older draft")
                if edited:
                    case = case_from_dict(m["case_snapshot"])
                    problems = check(Draft(subject=final_subject, body=final_body), case, policy)
                    if problems.violations:
                        raise HTTPException(
                            422,
                            {
                                "message": "the edited reminder didn't pass the checks",
                                "violations": [
                                    {"rule": v.rule, "detail": v.detail}
                                    for v in problems.violations
                                ],
                            },
                        )
            c.execute(
                update(drafts)
                .where(drafts.c.id == draft_id, drafts.c.status == "pending")
                .values(status="approved" if approve else "skipped", decided_at=func.now())
            )
            c.execute(
                insert(approvals).values(
                    draft_id=draft_id,
                    decision=body.decision,
                    final_subject=final_subject,
                    final_body=final_body,
                    edited=edited,
                )
            )
            row = c.execute(
                select(*_DRAFT_COLS).select_from(_WITH_DECISION).where(drafts.c.id == draft_id)
            ).first()
        return _out(row)

    @app.get("/activity")
    def activity() -> list[ActivityOut]:
        q = (
            select(
                approvals.c.draft_id,
                approvals.c.decision,
                approvals.c.edited,
                approvals.c.final_subject,
                approvals.c.decided_at,
                drafts.c.invoice_number,
                drafts.c.customer_name,
            )
            .select_from(approvals.join(drafts, approvals.c.draft_id == drafts.c.id))
            .order_by(approvals.c.decided_at.desc(), approvals.c.id.desc())
            .limit(50)
        )
        with engine.connect() as c:
            return [
                ActivityOut(
                    draft_id=r.draft_id,
                    invoice_number=r.invoice_number,
                    customer_name=r.customer_name,
                    decision=r.decision,
                    label="Ready to send" if r.decision == "approve" else "Skipped",
                    edited=r.edited,
                    final_subject=r.final_subject,
                    decided_at=r.decided_at.isoformat(),
                )
                for r in c.execute(q)
            ]

    return app


def _app_from_settings() -> FastAPI:
    from getpaid.config import get_settings
    from getpaid.llm.factory import client_from_settings

    s = get_settings()
    migrate(s.database_url)
    engine = make_engine(s.database_url)
    has_key = bool(s.openrouter_api_key.get_secret_value().strip()) and bool(s.model_list())
    client = client_from_settings(s) if has_key else None
    drafter: Drafter = LLMDrafter(client) if (s.drafter == "llm" and client) else TemplateDrafter()
    return create_app(
        engine=engine,
        source=McpSource() if s.source == "mcp" else FixtureSource(),
        drafter=drafter,
        policy=Policy(),
        web_origin=s.web_origin,
        asker=LLMAsker(client) if client else None,
    )
