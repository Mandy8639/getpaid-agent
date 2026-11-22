"use client";

import { useState } from "react";

import type { AskResult } from "@/lib/api";

const NOTE: Record<AskResult["source"], string> = {
  model: "Every number checked against your invoices.",
  fallback: "Plain summary: the written answer didn't pass the number check.",
  refused: "",
};

export function AskBox({
  onAsk,
}: {
  onAsk: (q: string) => Promise<AskResult>;
}) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await onAsk(q.trim()));
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      aria-label="Questions"
      className="mt-6 rounded-lg border border-gray-200 p-4"
    >
      <form onSubmit={submit} className="flex gap-2">
        <label htmlFor="ask" className="sr-only">
          Ask about your invoices
        </label>
        <input
          id="ask"
          value={q}
          maxLength={300}
          onChange={(e) => setQ(e.target.value)}
          placeholder="e.g. Who's more than 60 days late?"
          className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={busy || !q.trim()}
          className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-40"
        >
          Ask
        </button>
      </form>
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {error}
        </p>
      )}
      {result && (
        <div className="mt-3 text-sm" aria-live="polite">
          <p>{result.answer}</p>
          {NOTE[result.source] && (
            <p className="mt-1 text-xs text-gray-500">{NOTE[result.source]}</p>
          )}
        </div>
      )}
    </section>
  );
}
