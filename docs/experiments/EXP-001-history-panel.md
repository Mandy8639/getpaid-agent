# EXP-001: Does showing payment history help owners approve reminders as written?

**Status:** pre-registered 2026-11-22, before any data was generated. **No real users.** The only
data for this experiment so far is from *simulated* owners (see the report); it is a test of the
experiment pipeline, not evidence about real behaviour.

## Question
When an owner reviews a drafted reminder, does seeing the invoice's payment history (total,
paid so far, earlier late payments) next to the draft change how often they approve it
without editing?

## Arms
Assigned per owner (sticky: hash of experiment id and owner id), 50/50.
- **A `show`** (control): the review panel shows payment history. This is the current design.
- **B `hide`**: the review panel hides payment history; the draft text is unchanged.

## Metrics
- **Primary:** approve-without-edit rate = drafts approved with no edits ÷ drafts decided.
- **Secondary:** median seconds from draft shown to decision; skip rate.
- **Guardrail:** rejected edits (edits the checks refused) per 100 drafts must not rise in B.

## Hypothesis and decision rule
H1: A has a higher approve-without-edit rate than B (context reduces second-guessing).
Two-sided test of the difference in proportions, α = 0.05, 95% confidence interval reported.
- Ship `hide` only if B is not worse on the primary metric (CI lower bound > −2 points) and the
  guardrail holds. Otherwise keep `show`.
- A CI that includes 0 is reported as "no detectable difference", not as "no effect".

## Sample size
Baseline approve-without-edit ≈ 60%, minimum detectable effect 5 points, power 80%, α 0.05:
about 1,500 decided drafts per arm. No peeking: analyse once at the planned size.

## Analysis plan
Difference in proportions (B − A) with a Newcombe-Wilson 95% CI and a two-proportion z-test;
Welch difference in mean log-seconds for time to decide. Owners are the unit of assignment,
so with few owners the per-draft analysis overstates certainty; the report says so when the
number of owners is small.

## Amendment log
- **2026-11-22, after the first simulated run (not before):** the sample size above assumed
  independent drafts. In simulation (300 owners × 10 drafts, true effect −5 points) the
  per-owner analysis reached only 74% power, and the single run reported "no detectable
  difference" per draft. Before a real run, re-derive the sample size from the owner-level
  variance (design effect) and analyse at the owner level. The hypothesis, arms and metrics
  above are unchanged. The decision rule should then be applied to the owner-level CI (the
  simulated report already shows both and uses the owner-level one).
