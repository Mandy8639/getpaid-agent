export type Draft = {
  id: number;
  invoice_number: string;
  customer_name: string;
  balance: string;
  days_overdue: number;
  tone: string | null;
  subject: string | null;
  body: string | null;
  status: "pending" | "held" | "approved" | "skipped";
  hold_reason: string | null;
  violations: { rule: string; detail: string }[];
  guardrail_passed: boolean;
  tries: number;
  model: string | null;
};

export type Decision = "approve" | "skip";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function ok(r: Response): Promise<Response> {
  if (!r.ok) throw new Error(`API ${r.status}`);
  return r;
}

export async function runAgent(): Promise<{ pending: number; held: number }> {
  return (await ok(await fetch(`${API_URL}/runs`, { method: "POST" }))).json();
}

export async function nextDraft(): Promise<Draft | null> {
  const r = await ok(await fetch(`${API_URL}/drafts/next`, { cache: "no-store" }));
  return r.status === 204 ? null : r.json();
}

export async function listDrafts(status: Draft["status"]): Promise<Draft[]> {
  const r = await ok(await fetch(`${API_URL}/drafts?status=${status}`, { cache: "no-store" }));
  return r.json();
}

export async function decide(id: number, decision: Decision): Promise<Draft> {
  const r = await fetch(`${API_URL}/drafts/${id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  return (await ok(r)).json();
}
