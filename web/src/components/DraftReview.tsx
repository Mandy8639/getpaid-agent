"use client";

import type { Decision, Draft } from "@/lib/api";

const money = (s: string) =>
  Number(s).toLocaleString("en-US", { style: "currency", currency: "USD" });

const TONE: Record<string, string> = {
  friendly_nudge: "Friendly nudge",
  firm_reminder: "Firm reminder",
  final_notice: "Final reminder",
};

export function DraftReview({
  draft,
  onDecide,
  busy = false,
}: {
  draft: Draft;
  onDecide: (d: Decision) => void;
  busy?: boolean;
}) {
  return (
    <article className="rounded-lg border border-gray-200 p-6 shadow-sm" aria-label="Draft review">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">{draft.customer_name}</h2>
        <span className="text-sm text-gray-600">
          Invoice #{draft.invoice_number} · {money(draft.balance)} · {draft.days_overdue} days
          overdue
        </span>
      </header>
      <p className="mt-1 text-xs uppercase tracking-wide text-gray-500">
        {draft.tone ? TONE[draft.tone] ?? draft.tone : ""}
      </p>
      <p
        className={`mt-3 inline-block rounded px-2 py-0.5 text-xs ${
          draft.guardrail_passed ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
        }`}
      >
        {draft.guardrail_passed ? "Checked against the invoice record" : "Blocked by checks"}
      </p>
      {draft.violations.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-sm text-red-700">
          {draft.violations.map((v, i) => (
            <li key={i}>
              {v.rule}: {v.detail}
            </li>
          ))}
        </ul>
      )}
      <h3 className="mt-4 font-medium">{draft.subject}</h3>
      <pre className="mt-2 whitespace-pre-wrap font-sans text-sm text-gray-800">{draft.body}</pre>
      <div className="mt-6 flex gap-3">
        <button
          type="button"
          disabled={busy || draft.status !== "pending"}
          onClick={() => onDecide("approve")}
          className="rounded bg-black px-4 py-2 text-white disabled:opacity-40"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy || draft.status !== "pending"}
          onClick={() => onDecide("skip")}
          className="rounded border border-gray-300 px-4 py-2 disabled:opacity-40"
        >
          Skip
        </button>
      </div>
    </article>
  );
}
