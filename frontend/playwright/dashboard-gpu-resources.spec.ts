import { test, expect } from "@playwright/test";
import { ensureAppMode } from "./helpers";

test.describe.skip("Dashboard onboarded GPU resources", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAppMode(page, "simple");
    await page.goto("/#/");
  });

  test("shows GPU summary when onboarded resources include a GPU", async ({ page }) => {
    const card = page.getByTestId("onboarded-resources-card");
    test.skip((await card.count()) === 0, "Onboarded resources card not shown on this node");

    const text = await card.textContent();
    test.skip(!text?.includes("GPU"), "No GPU in onboarded resources on this node");

    await expect(card.getByText(/GPU:\s*\d+/)).toBeVisible({ timeout: 30_000 });
    await card.getByTestId("onboarded-resources-toggle").click();
    await expect(card.getByTestId("onboarded-resources-details")).toBeVisible();
    await expect(card.getByText("GPU Count")).toBeVisible();
  });
});
