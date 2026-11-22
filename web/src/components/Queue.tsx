import type { Draft } from "@/lib/api";

const money = (s: string) =>
  Number(s).toLocaleString("en-US", { style: "currency", currency: "USD" });

export function Queue({
  drafts,
  selectedId,
  onSelect,
}: {
  drafts: Draft[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  if (drafts.length === 0)
    return <p className="text-gray-600">No reminders waiting.</p>;
  return (
    <nav aria-label="Reminder queue">
      <ol className="divide-y divide-gray-200 rounded-lg border border-gray-200">
        {drafts.map((d) => (
          <li key={d.id}>
            <button
              type="button"
              onClick={() => onSelect(d.id)}
              aria-current={d.id === selectedId ? "true" : undefined}
              className={`w-full p-3 text-left text-sm hover:bg-gray-50 ${
                d.id === selectedId ? "bg-gray-100" : ""
              }`}
            >
              <span className="block font-medium">{d.customer_name}</span>
              <span className="text-gray-600">
                #{d.invoice_number} · {money(d.balance)} · {d.days_overdue} days
              </span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
