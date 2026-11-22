# getpaid

An approval-gated agent that drafts follow-ups for overdue invoices. It reads invoices
through an accounting MCP server, drafts a reminder for each overdue one, checks every
amount, date and invoice number against the record, and sends nothing without the owner's
approval.

Status: under construction. Slice 1 of 8 works end to end on synthetic sample invoices:
check invoices → deterministic decision (paid, disputed and not-yet-due invoices are held)
→ draft (template, or an OpenRouter model with `DRAFTER=llm`) → guardrail → owner approves
or skips in the web app → recorded in Postgres. Nothing is sent anywhere yet.

## What the guardrail checks

Every draft, before the owner sees it (`api/src/getpaid/agent/guardrail.py`):

- **G1 facts:** amounts, invoice numbers, dates and "N days overdue" must match the record
  (a reply-by date up to 30 days ahead is allowed); the balance and invoice number must be
  present; amounts in words are rejected.
- **G2 promises:** no discounts, waivers, cancellations, fees, payment plans (unless the
  business allows them), legal or collections language.
- **G3 holds:** never a draft for a paid, disputed or not-yet-due invoice.
- **G4 contact and payment details:** no links or web addresses (including disguised
  ones), phone numbers, other email addresses, bank or payment details, or hidden
  characters. The business reply address is the only contact allowed.

A draft that fails gets one repair attempt with generic hints; if it fails again it is held
with the reasons shown to the owner.

Known limits: the checks are pattern-based and English/US only. They're tested against a
list of known tricks, not proven complete, and model-written drafts haven't been evaluated
on a frozen test set yet (slice 3).

## Run

```bash
cp .env.example .env    # add OPENROUTER_API_KEY and OPENROUTER_MODELS
make install mcp up
make spend-init        # once: creates the $5 spend ledger
make lint test e2e

cd api && uv run uvicorn getpaid.asgi:app --port 8000   # API
cd web && npx next dev                                  # http://localhost:3000/drafts
```

## Model calls

OpenRouter only. Every request sets provider routing `data_collection: "deny"`, so it goes
only to providers that don't store or train on prompts. A cumulative ledger enforces a hard
total spend cap (default $5).

## Data

Sandbox and synthetic data only. The accounting connection uses the QuickBooks Online
sandbox through Intuit's open-source MCP server, installed as a pinned git dependency
(see NOTICE).

---

Independent demo; not affiliated with or endorsed by Intuit. QuickBooks is a trademark of
Intuit Inc.
