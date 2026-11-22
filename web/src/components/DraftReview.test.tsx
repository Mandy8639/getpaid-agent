import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import type { Draft } from "@/lib/api";
import { DraftReview } from "./DraftReview";

const draft: Draft = {
  id: 7,
  invoice_number: "1044",
  customer_name: "Cobalt Dental",
  balance: "1200.00",
  days_overdue: 8,
  tone: "friendly_nudge",
  subject: "Friendly reminder: invoice #1044",
  body: "Hi Cobalt Dental, invoice #1044 has a balance of $1,200.00.",
  status: "pending",
  hold_reason: null,
  violations: [],
  guardrail_passed: true,
  tries: 1,
  model: "template",
  edited: false,
  history: {
    total: "3200.00",
    paid_so_far: "2000.00",
    payment_dates: ["2026-11-12"],
    prior_late_payments: 0,
    txn_date: "2026-10-15",
    due_date: "2026-11-14",
  },
};

describe("DraftReview", () => {
  test("shows the facts, payment history and the editable draft", () => {
    render(<DraftReview draft={draft} onDecide={() => {}} />);
    expect(
      screen.getByText(/Invoice #1044 · \$1,200\.00 · 8 days/),
    ).toBeTruthy();
    expect(screen.getByText("Friendly nudge")).toBeTruthy();
    expect(screen.getByText(/\$2,000\.00 \(2026-11-12\)/)).toBeTruthy();
    expect(
      (screen.getByLabelText("Message") as HTMLTextAreaElement).value,
    ).toMatch(/\$1,200\.00/);
  });

  test("approve without edits sends no edits; with edits sends them", () => {
    const onDecide = vi.fn();
    render(<DraftReview draft={draft} onDecide={onDecide} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Approve — ready to send" }),
    );
    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "New text $1,200.00 #1044" },
    });
    expect(screen.getByText("Edited")).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: "Approve — ready to send" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onDecide.mock.calls).toEqual([
      ["approve", undefined],
      ["approve", { subject: draft.subject, body: "New text $1,200.00 #1044" }],
      ["skip"],
    ]);
  });

  test("shows why an edit was rejected", () => {
    render(
      <DraftReview
        draft={draft}
        onDecide={() => {}}
        rejected={[
          { rule: "G1", detail: "amount 1500.00 is not on the record" },
        ]}
      />,
    );
    expect(screen.getByText("Your edit didn't pass the checks")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toMatch(
      /G1: amount 1500\.00/,
    );
  });

  test("EXP-001 arm 'hide' leaves out the payment history", () => {
    render(
      <DraftReview draft={draft} onDecide={() => {}} showHistory={false} />,
    );
    expect(screen.queryByLabelText("Payment history")).toBeNull();
  });

  test("decided drafts can't be edited or approved", () => {
    render(
      <DraftReview
        draft={{ ...draft, status: "approved" }}
        onDecide={() => {}}
      />,
    );
    expect(
      (screen.getByLabelText("Message") as HTMLTextAreaElement).disabled,
    ).toBe(true);
    expect(
      (
        screen.getByRole("button", {
          name: "Approve — ready to send",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
});
