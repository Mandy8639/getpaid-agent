import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import Home from "./page";

test("home states the approval rule", () => {
  render(<Home />);
  expect(screen.getByText(/Nothing is sent without your approval/)).toBeTruthy();
});
