import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import DraftsPage from "./page";

const draft = {
  id: 1,
  invoice_number: "1045",
  customer_name: "Delta Freight",
  balance: "9875.25",
  days_overdue: 74,
  tone: "final_notice",
  subject: "s",
  body: "b",
  status: "pending",
  hold_reason: null,
  violations: [],
  guardrail_passed: true,
  tries: 1,
  model: "template",
  edited: false,
  history: {
    total: "9875.25",
    paid_so_far: "0.00",
    payment_dates: [],
    prior_late_payments: 0,
    txn_date: "2026-08-10",
    due_date: "2026-09-09",
  },
};

function mockApi(arm: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = url.includes("/assignment")
        ? { experiment_id: "EXP-001", owner_id: "demo-owner", arm }
        : url.includes("status=pending")
          ? [draft]
          : [];
      return new Response(JSON.stringify(body), { status: 200 });
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

test("EXP-001 arm 'hide' removes the payment history on the real page", async () => {
  mockApi("hide");
  render(<DraftsPage />);
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Delta Freight" })).toBeTruthy(),
  );
  await waitFor(() =>
    expect(screen.queryByLabelText("Payment history")).toBeNull(),
  );
});

test("EXP-001 arm 'show' shows the payment history on the real page", async () => {
  mockApi("show");
  render(<DraftsPage />);
  await waitFor(() =>
    expect(screen.getByLabelText("Payment history")).toBeTruthy(),
  );
});
