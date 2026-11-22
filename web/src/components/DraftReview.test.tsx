import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import type { Draft } from "@/lib/api";
import { DraftReview } from "./DraftReview";

const draft: Draft = {
  id: 7,
  invoice_number: "1045",
  customer_name: "Delta Freight",
  balance: "9875.25",
  days_overdue: 74,
  tone: "final_notice",
  subject: "Final reminder: invoice #1045",
  body: "Hi Delta Freight, invoice #1045 has a balance of $9,875.25.",
  status: "pending",
  hold_reason: null,
  violations: [],
  guardrail_passed: true,
  tries: 1,
  model: "template",
};

describe("DraftReview", () => {
  test("shows the record facts and the draft", () => {
    render(<DraftReview draft={draft} onDecide={() => {}} />);
    expect(screen.getByText(/Invoice #1045 · \$9,875\.25 · 74 days/)).toBeTruthy();
    expect(screen.getByText("Final reminder")).toBeTruthy();
    expect(screen.getByText("Checked against the invoice record")).toBeTruthy();
    expect(screen.getByText(/balance of \$9,875\.25/)).toBeTruthy();
  });

  test("approve and skip report the decision", () => {
    const onDecide = vi.fn();
    render(<DraftReview draft={draft} onDecide={onDecide} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onDecide.mock.calls).toEqual([["approve"], ["skip"]]);
  });

  test("blocked drafts show why and can't be approved", () => {
    const held: Draft = {
      ...draft,
      status: "held",
      guardrail_passed: false,
      violations: [{ rule: "G2", detail: "unauthorised promise or threat: 'discount'" }],
    };
    render(<DraftReview draft={held} onDecide={() => {}} />);
    expect(screen.getByText("Blocked by checks")).toBeTruthy();
    expect(screen.getByText(/G2: unauthorised promise/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Approve" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});
