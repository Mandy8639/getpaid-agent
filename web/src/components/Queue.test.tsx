import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import type { Activity, Draft } from "@/lib/api";
import { ActivityLog } from "./ActivityLog";
import { Queue } from "./Queue";

const d = (id: number, name: string): Draft => ({
  id,
  invoice_number: String(1000 + id),
  customer_name: name,
  balance: "100.00",
  days_overdue: 5,
  tone: "friendly_nudge",
  subject: "s",
  body: "b",
  status: "pending",
  hold_reason: null,
  violations: [],
  guardrail_passed: true,
  tries: 1,
  model: "template",
  edited: false,
});

test("queue lists drafts in the given order and reports the selection", () => {
  const onSelect = vi.fn();
  render(
    <Queue
      drafts={[d(1, "Delta"), d(2, "Acme")]}
      selectedId={1}
      onSelect={onSelect}
    />,
  );
  const items = screen.getAllByRole("button");
  expect(items.map((b) => b.textContent)).toEqual([
    expect.stringContaining("Delta"),
    expect.stringContaining("Acme"),
  ]);
  expect(items[0].getAttribute("aria-current")).toBe("true");
  fireEvent.click(items[1]);
  expect(onSelect).toHaveBeenCalledWith(2);
});

test("activity log labels approvals as ready to send and marks edits", () => {
  const items: Activity[] = [
    {
      draft_id: 1,
      invoice_number: "1045",
      customer_name: "Delta",
      decision: "approve",
      label: "Ready to send",
      edited: true,
      final_subject: "x",
      decided_at: "2026-11-22T10:00:00",
    },
    {
      draft_id: 2,
      invoice_number: "1042",
      customer_name: "Acme",
      decision: "skip",
      label: "Skipped",
      edited: false,
      final_subject: null,
      decided_at: "2026-11-22T09:00:00",
    },
  ];
  render(<ActivityLog items={items} />);
  expect(screen.getByText("Ready to send")).toBeTruthy();
  expect(screen.getByText("(edited)")).toBeTruthy();
  expect(screen.getByText("Skipped")).toBeTruthy();
});
