import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Draft } from "@/lib/api";
import { HeldList } from "./HeldList";

const base: Draft = {
  id: 1,
  invoice_number: "1046",
  customer_name: "Evergreen Yoga",
  balance: "0.00",
  days_overdue: 22,
  tone: null,
  subject: null,
  body: null,
  status: "held",
  hold_reason: "paid",
  violations: [],
  guardrail_passed: true,
  tries: 0,
  model: null,
};

test("lists held invoices with a plain reason and any violations", () => {
  render(
    <HeldList
      held={[
        base,
        {
          ...base,
          id: 2,
          invoice_number: "1042",
          customer_name: "Acme Landscaping",
          hold_reason: "guardrail_blocked",
          violations: [{ rule: "G1", detail: "amount 1804.00 is not on the record" }],
        },
      ]}
    />,
  );
  expect(screen.getByText("Held back (2)")).toBeTruthy();
  expect(screen.getByText("Already paid")).toBeTruthy();
  expect(screen.getByText("Blocked by checks")).toBeTruthy();
  expect(screen.getByText(/G1: amount 1804\.00/)).toBeTruthy();
});

test("renders nothing when nothing is held", () => {
  const { container } = render(<HeldList held={[]} />);
  expect(container.innerHTML).toBe("");
});
