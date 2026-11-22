import type { Activity } from "@/lib/api";

export function ActivityLog({ items }: { items: Activity[] }) {
  if (items.length === 0) return null;
  return (
    <section aria-label="Activity" className="mt-10">
      <h2 className="text-lg font-semibold">Activity</h2>
      <p className="text-sm text-gray-600">
        Approved reminders are ready to send. Nothing is sent from this demo.
      </p>
      <ul className="mt-3 divide-y divide-gray-200 rounded-lg border border-gray-200">
        {items.map((a) => (
          <li
            key={a.draft_id}
            className="flex flex-wrap justify-between gap-2 p-3 text-sm"
          >
            <span>
              <span className="font-medium">{a.customer_name}</span> · invoice #
              {a.invoice_number}
              {a.edited && (
                <span className="ml-2 text-xs text-gray-500">(edited)</span>
              )}
            </span>
            <span
              className={
                a.label === "Ready to send" ? "text-green-800" : "text-gray-600"
              }
            >
              {a.label}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
