# getpaid

An approval-gated agent that drafts follow-ups for overdue invoices. It reads invoices
through an accounting MCP server, drafts a reminder for each overdue one, checks every
amount, date and invoice number against the record, and sends nothing without the owner's
approval.

Status: under construction. Slices 1–2 of 8: works end to end on synthetic invoices, from
saved sample files or live from a QuickBooks Online sandbox through Intuit's MCP server:
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

## Ask about your invoices

`POST /ask` (and the box on the drafts page) answers questions like "Who's more than 60 days
late?" without letting the model invent numbers:

1. The model maps the question to one structured query (overdue list, customer balance,
   invoice lookup, totals) or marks it unsupported. Requests to send, change, waive or
   promise anything are refused.
2. Plain code runs the query. No model.
3. The model writes a short answer from that result only.
4. A check requires every amount, invoice number, date and count/day figure in the answer to
   come from the result (or the question), and blocks links and contact details. If it fails,
   the owner gets a plain summary built by code instead.

Live smoke test (6 questions on the seeded sandbox, Claude Haiku 5.5 via OpenRouter,
`data_collection: "deny"`): 4 of 4 answerable questions answered by the model and passing
the check, 2 of 2 adversarial requests refused, $0.0015 ([report](reports/smoke-qa-2026-11-22.md)).
This is a smoke test, not an evaluation; slice 7 runs the frozen eval set. Known limits: the
check is value-level (a day count that belongs to another invoice would pass), and `/ask`
has no login or rate limit yet (planned before any public deployment).

## Live sandbox mode (optional)

The app can read a QuickBooks Online **sandbox** through Intuit's MCP server instead of the
sample files:

```bash
make mcp                                  # install Intuit's server (pinned commit)
cp .qbo-tokens.example .qbo-tokens        # then add your sandbox app's client ID/secret
chmod 600 .qbo-tokens
cd mcp/node_modules/@qboapi/qbo-mcp-server && \
  QUICKBOOKS_TOKEN_STORE_PATH=$PWD/../../../../.qbo-tokens node dist/auth-server.js   # one-time OAuth
cd api && uv run python -m getpaid.seed          # dry run: shows what would be created
cd api && uv run python -m getpaid.seed --apply  # 40 synthetic customers, 150 invoices
SOURCE=mcp                                # in .env, then run the API as usual
RUN_LIVE=1 uv run pytest tests/test_live_contract.py   # contract tests against the sandbox
```

Safeguards:

- **Read-only by default.** The server is started with its write, update and delete tools
  switched off, and every call is also checked against an allowlist. The seed script can
  create customers, invoices and payments, but never update or delete them.
- **Sandbox only.** The token file may hold only `QUICKBOOKS_*` keys and must say
  `QUICKBOOKS_ENVIRONMENT=sandbox`, or nothing starts. The server never sees the model key.
- **Only our synthetic records.** A customer is used only if it carries the seed tag *and* is
  listed in `.seed/manifest.json`. Intuit's pre-loaded sample company is never sent to a
  model. Without a manifest, the live source returns nothing.

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
