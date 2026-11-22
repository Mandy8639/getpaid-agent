# Notes on eval-test-v1 (written by hand, after the run)

These notes were first appended to `eval-test-v1.md` about two minutes after the run was logged
(the code review spotted the timestamp). They are now kept here so the generated report stays
exactly as the run produced it. Nothing in the generated tables was edited; the only change to
that file was this commentary, which has been moved out.

## What this shows, and what it doesn't

- **The deterministic decision step is where the gap comes from.** All 21 baseline failures are
  reminders written for invoices that are paid, disputed or not yet due. The baseline asks the
  model to draft for every invoice, and the model complies.
- **The content checks weren't stressed by this set.** The model resisted all 7 adversarial
  scenarios on its own (7/7 even in the baseline), and the full pipeline needed no repairs. The
  guardrail's value here is as a backstop; it caught real problems in the dev split before
  tuning (6 holds in dev-v1, traced to a guardrail bug on "$0.00 paid", fixed in dev-v2).
- **The template's 2 safe failures are by design.** It copies customer names into the greeting,
  and the two names carrying payment details were blocked and held, not sent.
- **Run-to-run variation:** the full pipeline was run twice on the dev split after tuning
  (dev-v2 and dev-v2-repeat). Both gave 30/30 correct, 0 unsafe, 0 repairs; p95 latency was
  4.2 s and 5.2 s. The test split was run once, as planned.
- **Limits:** 50 synthetic scenarios from one seeded sandbox and one English, US-dollar
  policy. Most first attempts went to Claude Haiku 5.5, with others as failover. No real
  businesses, owners or customers were involved. The scorer is independent of the guardrail's
  code, but both were written by the same author.
