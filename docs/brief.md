# Product brief: getpaid

**Problem.** Small businesses wait too long to get paid. QuickBooks' own October 2026 release
cited that nearly 3 in 5 small businesses have invoices more than 30 days overdue. Chasing
them is awkward, slow and easy to put off.

**User.** The owner or office manager of a small business that invoices clients through an
accounting system. They want the money in without damaging the relationship.

**What it does.** Ranks overdue invoices, drafts a follow-up that fits each case, and waits
for the owner to approve, edit or skip. Every amount, date and invoice number in a draft
must match the accounting record. Nothing is sent without a click.

**Primary metric.** Share of drafts the owner approves without edits.
**Guardrail metrics.** Unsafe sends (target 0): to paid or disputed invoices, or with a
wrong amount, date or invoice number. Promises the business didn't authorise (target 0).

**Out of scope.** Real businesses or real customer data (sandbox and synthetic data only),
payments processing, collections agencies, legal notices, model training of any kind.

**Status of evidence.** No real users. Experiments run on simulated owners, labelled as such.
