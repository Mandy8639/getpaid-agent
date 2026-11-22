import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { AskBox } from "./AskBox";

test("asks the question and shows a checked answer", async () => {
  const onAsk = vi.fn().mockResolvedValue({
    answer: "Delta Freight, invoice #1045, $9,875.25, 74 days overdue.",
    source: "model",
    rows: [],
    summary: {},
  });
  render(<AskBox onAsk={onAsk} />);
  fireEvent.change(screen.getByLabelText("Ask about your invoices"), {
    target: { value: "Who's 60+ days late?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() =>
    expect(screen.getByText(/Delta Freight, invoice #1045/)).toBeTruthy(),
  );
  expect(onAsk).toHaveBeenCalledWith("Who's 60+ days late?");
  expect(
    screen.getByText("Every number checked against your invoices."),
  ).toBeTruthy();
});

test("labels a fallback answer and shows errors", async () => {
  const onAsk = vi
    .fn()
    .mockResolvedValueOnce({
      answer: "No invoices match that.",
      source: "fallback",
      rows: [],
      summary: {},
    })
    .mockRejectedValueOnce(
      new Error("the model spending limit has been reached"),
    );
  render(<AskBox onAsk={onAsk} />);
  const input = screen.getByLabelText("Ask about your invoices");
  fireEvent.change(input, { target: { value: "x" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() =>
    expect(screen.getByText(/didn't pass the number check/)).toBeTruthy(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toMatch(/spending limit/),
  );
});
