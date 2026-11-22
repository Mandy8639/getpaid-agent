"use client";

import { useCallback, useEffect, useState } from "react";

import { DraftReview } from "@/components/DraftReview";
import { HeldList } from "@/components/HeldList";
import { decide, listDrafts, nextDraft, runAgent, type Decision, type Draft } from "@/lib/api";

export default function DraftsPage() {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [held, setHeld] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [next, heldNow] = await Promise.all([nextDraft(), listDrafts("held")]);
      setDraft(next);
      setHeld(heldNow);
    } catch {
      setError("Couldn't reach the API.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onDecide(d: Decision) {
    if (!draft) return;
    setBusy(true);
    try {
      await decide(draft.id, d);
      setMessage(
        d === "approve"
          ? `Approved the reminder for invoice #${draft.invoice_number}.`
          : `Skipped invoice #${draft.invoice_number}.`,
      );
      await load();
    } catch {
      setError("That decision didn't save. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function onRun() {
    setBusy(true);
    try {
      const r = await runAgent();
      setMessage(`${r.pending} drafts ready, ${r.held} held back.`);
      await load();
    } catch {
      setError("Couldn't run the agent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Overdue reminders</h1>
        <button
          type="button"
          onClick={onRun}
          disabled={busy}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-40"
        >
          Check invoices
        </button>
      </div>
      <p className="mt-1 text-sm text-gray-600">
        Nothing is sent without your approval. Sample data only.
      </p>
      {message && (
        <p role="status" className="mt-4 text-sm text-gray-700">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      )}
      <section className="mt-6">
        {loading ? (
          <p className="text-gray-500">Loading…</p>
        ) : draft ? (
          <DraftReview draft={draft} onDecide={onDecide} busy={busy} />
        ) : (
          <p className="text-gray-600">No reminders waiting.</p>
        )}
      </section>
      <HeldList held={held} />
    </main>
  );
}
