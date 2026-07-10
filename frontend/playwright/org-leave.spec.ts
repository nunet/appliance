import { test, expect } from "@playwright/test";
import { ensureAppMode, logStep, openSidebar } from "./helpers";

const DEFAULT_ORG_DID =
  process.env.NUTEST_ORG_DID ?? "did:key:z6MksqN98v97yXtaGkuJWeK5yJ9EejZEi6xM19oZa8t4zL5a";

test.describe.skip("Organization leave flow", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAppMode(page, "simple");
    await page.goto("/#/");
    await openSidebar(page, /^Organizations$/);
    await expect(page).toHaveURL(/#\/organizations/, { timeout: 20_000 });
  });

  test("prompts before leaving and can cancel", async ({ page }) => {
    const card = page.locator(`[data-testid="org-card"][data-org-did="${DEFAULT_ORG_DID}"]`);
    const leave = page.locator(`[data-testid="org-leave-button"][data-org-did="${DEFAULT_ORG_DID}"]`);
    const fetch = page.getByTestId("org-fetch-button");

    if ((await card.count()) === 0) {
      logStep("Org card missing; fetching known orgs");
      await fetch.click();
    }
    await expect(card).toBeVisible({ timeout: 120_000 });
    test.skip((await leave.count()) === 0, "Leave button not present");

    await leave.click();
    await expect(page.getByText("Leave organization?")).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(leave).toBeVisible();
  });
});
