import { test, expect } from "@playwright/test";
import {
  ensureAppMode,
  isDmsOnboarded,
  logStep,
  waitForDmsOnboarded,
} from "./helpers";

test.describe("Dashboard offboard/onboard toggle", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAppMode(page, "simple");
  });

  test("toggles offboard and onboard regardless of initial state", async ({ page }) => {
    test.setTimeout(600_000);

    const onboarded = await isDmsOnboarded(true);
    test.skip(!onboarded, "Not joined; skipping offboard/onboard toggle");

    logStep(`Opening dashboard. Initial state: ${onboarded ? 'Onboarded' : 'Not Onboarded'}`);
    await page.goto("/#/");

    if (onboarded) {
      // If the API reports that the resource is already onboarded, we expect the Offboard button to appear.
      // We allow up to 30 seconds for the frontend to fetch the data and render the correct screen.
      await expect(page.getByTestId("offboard-button")).toBeVisible({ timeout: 30_000 });
    }

    const offboardBtn = page.getByTestId("offboard-button");
    await expect(offboardBtn).toBeVisible({ timeout: 30_000 });

    logStep("Clicking offboard (DMS offboard may take minutes on a real node)");
    await offboardBtn.click();
    await page.getByTestId("offboard-confirm-button").click({ timeout: 60_000 });

    logStep("Waiting for DMS to report not onboarded (API poll, refresh=true)");
    const offboarded = await waitForDmsOnboarded(false, {
      maxMs: 120_000,
      intervalMs: 15_000,
    });
    expect(offboarded, "DMS did not reach NOT ONBOARDED within 5 minutes").toBeTruthy();
    await expect(page.getByTestId("onboard-button")).toBeVisible({ timeout: 30_000 });

    logStep("Clicking onboard");
    const onboardBtn = page.getByTestId("onboard-button");
    await expect(onboardBtn).toBeVisible({ timeout: 30_000 });
    await onboardBtn.click();

    logStep("Waiting for DMS to report onboarded again (API poll)");
    const reOnboarded = await waitForDmsOnboarded(true, {
      maxMs: 120_000,
      intervalMs: 15_000,
    });
    expect(reOnboarded, "DMS did not reach ONBOARDED within 5 minutes").toBeTruthy();
    await expect(page.getByTestId("offboard-button")).toBeVisible({ timeout: 30_000 });
  });
});
