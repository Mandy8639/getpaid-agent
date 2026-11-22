# getpaid

An approval-gated agent that drafts follow-ups for overdue invoices. It reads invoices
through an accounting MCP server, drafts a reminder for each overdue one, checks every
amount, date and invoice number against the record, and sends nothing without the owner's
approval.

Status: under construction (slice 0 of 8: skeleton and model client).

## Run

```bash
cp .env.example .env    # add OPENROUTER_API_KEY and OPENROUTER_MODELS
make install mcp up
make lint test
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
