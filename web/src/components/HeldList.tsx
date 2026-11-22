import type { Draft } from "@/lib/api";

const REASON: Record<string, string> = {
  paid: "Already paid",
  disputed: "Disputed",
  not_overdue: "Not yet due",
  drafter_failed: "Couldn't draft",
  guardrail_blocked: "Blocked by checks",
  spend_cap: "Spending limit reached",
};

export function HeldList({ held }: { held: Draft[] }) {
  if (held.length === 0) return null;
  return (
    <section aria-label="Held back" className="mt-10">
      <h2 className="text-lg font-semibold">Held back ({held.length})</h2>
      <p className="text-sm text-gray-600">No reminder will be offered for these.</p>
      <ul className="mt-3 divide-y divide-gray-200 rounded-lg border border-gray-200">
        {held.map((d) => (
          <li key={d.id} className="p-3 text-sm">
            <span className="font-medium">{d.customer_name}</span> · invoice #{d.invoice_number} ·{" "}
            <span>{d.hold_reason ? REASON[d.hold_reason] ?? d.hold_reason : "Held"}</span>
            {d.violations.length > 0 && (
              <ul className="mt-1 list-disc pl-5 text-red-700">
                {d.violations.map((v, i) => (
                  <li key={i}>
                    {v.rule}: {v.detail}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
