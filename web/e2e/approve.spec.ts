import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

test("owner checks invoices, edits the top draft and approves it as ready to send", async ({
  page,
  request,
}) => {
  await page.goto("/drafts");
  await expect(page.getByText("No reminders waiting.")).toBeVisible();

  await page.getByRole("button", { name: "Check invoices" }).click();
  await expect(page.getByRole("status")).toHaveText(
    "5 drafts ready, 3 held back.",
  );

  const heldList = page.getByRole("region", { name: "Held back" });
  await expect(heldList.getByText("Held back (3)")).toBeVisible();
  await expect(heldList.getByText("Already paid")).toBeVisible();

  const queue = page.getByRole("navigation", { name: "Reminder queue" });
  await expect(queue.getByRole("button").first()).toContainText(
    "Delta Freight",
  );

  const review = page.getByRole("article", { name: "Draft review" });
  await expect(
    review.getByRole("heading", { name: "Delta Freight" }),
  ).toBeVisible();
  await expect(
    review.getByText(/Invoice #1045 · \$9,875\.25 · 74 days/),
  ).toBeVisible();
  await expect(review.getByLabel("Payment history")).toContainText("$9,875.25");

  const message = review.getByLabel("Message");
  await message.fill(
    (await message.inputValue()).replace(
      "Hi Delta Freight,",
      "Hello Delta Freight team,",
    ),
  );
  await expect(review.getByText("Edited")).toBeVisible();
  await review.getByRole("button", { name: "Approve — ready to send" }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Approved — ready to send: invoice #1045.",
  );

  const activity = page.getByRole("region", { name: "Activity" });
  await expect(activity).toContainText("Delta Freight");
  await expect(activity).toContainText("Ready to send");
  await expect(activity).toContainText("(edited)");
  await expect(
    review.getByRole("heading", { name: "Acme Landscaping" }),
  ).toBeVisible();

  const approved = await (
    await request.get("http://localhost:8010/drafts?status=approved")
  ).json();
  expect(
    approved.map((d: { invoice_number: string }) => d.invoice_number),
  ).toEqual(["1045"]);
  expect(approved[0].final_body).toContain("Hello Delta Freight team,");
});

test("an edit that changes the amount is blocked and the draft stays pending", async ({
  page,
  request,
}) => {
  await request.post("http://localhost:8010/runs"); // idempotent: lets this test run alone
  await page.goto("/drafts");
  await page
    .getByRole("navigation", { name: "Reminder queue" })
    .getByRole("button", { name: /Acme Landscaping/ })
    .click();
  const review = page.getByRole("article", { name: "Draft review" });
  await expect(
    review.getByRole("heading", { name: "Acme Landscaping" }),
  ).toBeVisible();
  const message = review.getByLabel("Message");
  await message.fill(
    (await message.inputValue()).replace("$1,840.00", "$1,480.00"),
  );
  await review.getByRole("button", { name: "Approve — ready to send" }).click();
  await expect(
    review.getByText("Your edit didn't pass the checks"),
  ).toBeVisible();
  await expect(review.getByRole("alert")).toContainText("G1");
  await expect(
    page.getByRole("navigation", { name: "Reminder queue" }),
  ).toContainText("Acme Landscaping");
});

test("asking without a model configured explains why", async ({ page }) => {
  await page.goto("/drafts");
  await page
    .getByLabel("Ask about your invoices")
    .fill("Who's more than 60 days late?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(
    page.getByRole("region", { name: "Questions" }).getByRole("alert"),
  ).toContainText("Q&A needs a model");
});
