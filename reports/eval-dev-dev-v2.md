# Eval report: dev split

Run 2026-11-22 22:00 UTC, tag `dev-v2`, 30 scenarios (synthetic, seeded sandbox snapshots), models anthropic/claude-haiku-5.5, openai/gpt-4.1-nano, mistralai/mistral-small-3.2-24b-instruct via OpenRouter with `data_collection: "deny"`. Total model spend this run: $0.0080.

| system | n | correct | correct drafts / expected | correct holds | safe failures | fact errors | **unsafe** | adversarial safe | repairs | p50 ms | p95 ms | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llm-full | 30 | 30 | 21/21 | 9 | 0 | 0 | **0** | 4/4 | 0 | 3058 | 4249 | $0.0080 |

## Every failure

| system | scenario | category | expected | got | result | reason |
|---|---|---|---|---|---|---|
