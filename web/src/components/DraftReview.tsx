"use client";

import { useEffect, useState } from "react";

import type { Decision, Draft, Violation } from "@/lib/api";

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
  rejected = [],
}: {
  draft: Draft;
  onDecide: (d: Decision, edits?: { subject: string; body: string }) => void;
  busy?: boolean;
  rejected?: Violation[];
}) {
  const [subject, setSubject] = useState(draft.subject ?? "");
  const [body, setBody] = useState(draft.body ?? "");
  useEffect(() => {
    setSubject(draft.subject ?? "");
    setBody(draft.body ?? "");
  }, [draft.id, draft.subject, draft.body]);
  const edited =
    subject !== (draft.subject ?? "") || body !== (draft.body ?? "");
  const pending = draft.status === "pending";
  const h = draft.history;
  const violations = rejected.length ? rejected : draft.violations;

  return (
    <article
      className="rounded-lg border border-gray-200 p-6 shadow-sm"
      aria-label="Draft review"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">{draft.customer_name}</h2>
        <span className="text-sm text-gray-600">
          Invoice #{draft.invoice_number} · {money(draft.balance)} ·{" "}
          {draft.days_overdue} days overdue
        </span>
      </header>
      <p className="mt-1 text-xs uppercase tracking-wide text-gray-500">
        {draft.tone ? (TONE[draft.tone] ?? draft.tone) : ""}
      </p>
      {h && (
        <dl
          aria-label="Payment history"
          className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm"
        >
          <dt className="text-gray-500">Invoice total</dt>
          <dd>{money(h.total)}</dd>
          <dt className="text-gray-500">Paid so far</dt>
          <dd>
            {money(h.paid_so_far)}
            {h.payment_dates.length > 0 && ` (${h.payment_dates.join(", ")})`}
          </dd>
          <dt className="text-gray-500">Issued / due</dt>
          <dd>
            {h.txn_date} / {h.due_date}
          </dd>
          <dt className="text-gray-500">Earlier late payments</dt>
          <dd>{h.prior_late_payments}</dd>
        </dl>
      )}
      <p
        className={`mt-3 inline-block rounded px-2 py-0.5 text-xs ${
          violations.length === 0
            ? "bg-green-100 text-green-800"
            : "bg-red-100 text-red-800"
        }`}
      >
        {violations.length === 0
          ? "Checked against the invoice record"
          : rejected.length
            ? "Your edit didn't pass the checks"
            : "Blocked by checks"}
      </p>
      {violations.length > 0 && (
        <ul role="alert" className="mt-2 list-disc pl-5 text-sm text-red-700">
          {violations.map((v, i) => (
            <li key={i}>
              {v.rule}: {v.detail}
            </li>
          ))}
        </ul>
      )}
      <label className="mt-4 block text-sm font-medium" htmlFor="subject">
        Subject
      </label>
      <input
        id="subject"
        value={subject}
        maxLength={200}
        disabled={!pending}
        onChange={(e) => setSubject(e.target.value)}
        className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
      />
      <label className="mt-3 block text-sm font-medium" htmlFor="body">
        Message
      </label>
      <textarea
        id="body"
        value={body}
        rows={9}
        maxLength={4000}
        disabled={!pending}
        onChange={(e) => setBody(e.target.value)}
        className="mt-1 w-full rounded border border-gray-300 px-3 py-2 font-sans text-sm"
      />
      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          disabled={busy || !pending}
          onClick={() =>
            onDecide("approve", edited ? { subject, body } : undefined)
          }
          className="rounded bg-black px-4 py-2 text-white disabled:opacity-40"
        >
          Approve — ready to send
        </button>
        <button
          type="button"
          disabled={busy || !pending}
          onClick={() => onDecide("skip")}
          className="rounded border border-gray-300 px-4 py-2 disabled:opacity-40"
        >
          Skip
        </button>
        {edited && (
          <span className="self-center text-xs text-gray-500">Edited</span>
        )}
      </div>
    </article>
  );
}
