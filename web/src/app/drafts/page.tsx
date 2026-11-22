"use client";

import { useCallback, useEffect, useState } from "react";

import { ActivityLog } from "@/components/ActivityLog";
import { AskBox } from "@/components/AskBox";
import { DraftReview } from "@/components/DraftReview";
import { HeldList } from "@/components/HeldList";
import { Queue } from "@/components/Queue";
import {
  AccessRequired,
  EditRejected,
  setAccessCode,
  askQuestion,
  decide,
  experimentArm,
  listActivity,
  listDrafts,
  runAgent,
  type Activity,
  type Decision,
  type Draft,
  type Violation,
} from "@/lib/api";

export default function DraftsPage() {
  const [pending, setPending] = useState<Draft[]>([]);
  const [held, setHeld] = useState<Draft[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [rejected, setRejected] = useState<Violation[]>([]);
  // null until the arm is known, so "hide" owners never see a flash of the history panel.
  // On failure the page shows the control version; events still log the assigned arm (ITT).
  const [arm, setArm] = useState<string | null>(null);
  const [shownAt, setShownAt] = useState<number>(() => Date.now());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needCode, setNeedCode] = useState(false);
  const [code, setCode] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, h, a] = await Promise.all([
        listDrafts("pending"),
        listDrafts("held"),
        listActivity(),
      ]);
      setPending(p);
      setHeld(h);
      setActivity(a);
      setSelectedId((id) =>
        p.some((d) => d.id === id) ? id : (p[0]?.id ?? null),
      );
    } catch (e) {
      if (e instanceof AccessRequired) setNeedCode(true);
      else setError("Couldn't reach the API.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    experimentArm("EXP-001")
      .then(setArm)
      .catch(() => setArm("show"));
  }, [load]);

  useEffect(() => {
    setShownAt(Date.now());
  }, [selectedId]);

  const selected = pending.find((d) => d.id === selectedId) ?? null;

  async function onDecide(
    d: Decision,
    edits?: { subject: string; body: string },
  ) {
    if (!selected) return;
    setBusy(true);
    setRejected([]);
    try {
      await decide(selected.id, d, edits, (Date.now() - shownAt) / 1000);
      setMessage(
        d === "approve"
          ? `Approved — ready to send: invoice #${selected.invoice_number}.`
          : `Skipped invoice #${selected.invoice_number}.`,
      );
      await load();
    } catch (e) {
      if (e instanceof EditRejected) setRejected(e.violations);
      else setError("That decision didn't save. Try again.");
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

  if (needCode) {
    return (
      <main className="mx-auto max-w-sm p-8">
        <h1 className="text-xl font-semibold">Access code</h1>
        <p className="mt-1 text-sm text-gray-600">
          This preview is protected. Enter the code you were given.
        </p>
        <form
          className="mt-4 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setAccessCode(code);
            setNeedCode(false);
            void load();
          }}
        >
          <label htmlFor="code" className="sr-only">
            Access code
          </label>
          <input
            id="code"
            type="password"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            className="rounded bg-black px-4 py-2 text-sm text-white"
          >
            Continue
          </button>
        </form>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl p-4 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
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
        Nothing is sent without your approval, and this demo never sends. Sample
        data only.
      </p>
      <AskBox onAsk={askQuestion} />
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
      {loading ? (
        <p className="mt-6 text-gray-500">Loading…</p>
      ) : (
        <div className="mt-6 grid gap-6 md:grid-cols-[18rem_1fr]">
          <Queue
            drafts={pending}
            selectedId={selected?.id ?? null}
            onSelect={(id) => {
              setRejected([]);
              setSelectedId(id);
            }}
          />
          {selected && (
            <DraftReview
              draft={selected}
              onDecide={onDecide}
              busy={busy}
              rejected={rejected}
              showHistory={arm === "show"}
            />
          )}
        </div>
      )}
      <ActivityLog items={activity} />
      <HeldList held={held} />
    </main>
  );
}
