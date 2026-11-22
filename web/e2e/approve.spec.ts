import { expect, test } from "@playwright/test";

test("owner checks invoices, reviews the top draft and approves it", async ({ page, request }) => {
  await page.goto("/drafts");
  await expect(page.getByText("No reminders waiting.")).toBeVisible();

  await page.getByRole("button", { name: "Check invoices" }).click();
  await expect(page.getByRole("status")).toHaveText("5 drafts ready, 3 held back.");

  const heldList = page.getByRole("region", { name: "Held back" });
  await expect(heldList.getByText("Held back (3)")).toBeVisible();
  await expect(heldList.getByText("Already paid")).toBeVisible();
  await expect(heldList.getByText("Disputed")).toBeVisible();
  await expect(heldList.getByText("Not yet due")).toBeVisible();

  const review = page.getByRole("article", { name: "Draft review" });
  await expect(review.getByRole("heading", { name: "Delta Freight" })).toBeVisible();
  await expect(review.getByText(/Invoice #1045 · \$9,875\.25 · 74 days/)).toBeVisible();
  await expect(review.getByText("Checked against the invoice record")).toBeVisible();

  await review.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("status")).toHaveText("Approved the reminder for invoice #1045.");
  await expect(review.getByRole("heading", { name: "Acme Landscaping" })).toBeVisible();

  const approved = await (await request.get("http://localhost:8010/drafts?status=approved")).json();
  expect(approved.map((d: { invoice_number: string }) => d.invoice_number)).toEqual(["1045"]);
});

test("asking without a model configured explains why", async ({ page }) => {
  await page.goto("/drafts");
  await page.getByLabel("Ask about your invoices").fill("Who's more than 60 days late?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByRole("region", { name: "Questions" }).getByRole("alert")).toContainText(
    "Q&A needs a model",
  );
});
