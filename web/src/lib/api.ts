import type { components } from "./api-types";

// Generated from the API's OpenAPI schema (`make types`); never edit api-types.ts by hand.
export type Draft = components["schemas"]["DraftOut"];
export type Activity = components["schemas"]["ActivityOut"];
export type Violation = { rule: string; detail: string };

export type Decision = "approve" | "skip";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function ok(r: Response): Promise<Response> {
  if (!r.ok) throw new Error(`API ${r.status}`);
  return r;
}

export async function runAgent(): Promise<{ pending: number; held: number }> {
  return (await ok(await fetch(`${API_URL}/runs`, { method: "POST" }))).json();
}

export async function nextDraft(): Promise<Draft | null> {
  const r = await ok(
    await fetch(`${API_URL}/drafts/next`, { cache: "no-store" }),
  );
  return r.status === 204 ? null : r.json();
}

export async function listDrafts(status: Draft["status"]): Promise<Draft[]> {
  const r = await ok(
    await fetch(`${API_URL}/drafts?status=${status}`, { cache: "no-store" }),
  );
  return r.json();
}

export class EditRejected extends Error {
  constructor(public violations: Violation[]) {
    super("The edited reminder didn't pass the checks.");
  }
}

export async function decide(
  id: number,
  decision: Decision,
  edits?: { subject?: string; body?: string },
  secondsToDecide?: number,
): Promise<Draft> {
  const r = await fetch(`${API_URL}/drafts/${id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      decision,
      ...edits,
      seconds_to_decide: secondsToDecide,
    }),
  });
  if (r.status === 422) {
    const body = (await r.json().catch(() => ({}))) as {
      detail?: { violations?: Violation[] };
    };
    if (
      body.detail &&
      typeof body.detail === "object" &&
      body.detail.violations
    ) {
      throw new EditRejected(body.detail.violations);
    }
  }
  return (await ok(r)).json();
}

export async function experimentArm(experimentId: string): Promise<string> {
  const r = await ok(
    await fetch(`${API_URL}/experiments/${experimentId}/assignment`, {
      cache: "no-store",
    }),
  );
  return ((await r.json()) as { arm: string }).arm;
}

export async function listActivity(): Promise<Activity[]> {
  return (
    await ok(await fetch(`${API_URL}/activity`, { cache: "no-store" }))
  ).json();
}

export type AskResult = {
  answer: string;
  source: "model" | "fallback" | "refused";
  rows: {
    invoice_number: string;
    customer: string;
    balance: string;
    days_overdue: number;
  }[];
  summary: { count?: number; total_balance?: string };
};

export async function askQuestion(question: string): Promise<AskResult> {
  const r = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (r.status === 503) {
    const body = (await r.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? "Questions are unavailable right now.");
  }
  return (await ok(r)).json();
}
