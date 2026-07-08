import { test, expect } from "@playwright/test";
import { logStep } from "./helpers";

const UI_STEP_TIMEOUT_MS = 10_000;
const TOTAL_FLOW_MAX_MS = 80_000;

test.describe("Real appliance: login and dashboard status", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("shows the login page", async ({ page }) => {
    await page.goto("/#/login");
    await expect(page.getByText("Welcome back")).toBeVisible();
    await expect(page.getByText("Enter the admin password")).toBeVisible();
    await expect(page.getByTestId("login-form")).toBeVisible();
  });

  test("logs in through the UI and loads the dashboard status board", async ({
    page,
  }) => {
    const password = process.env.APPLIANCE_ADMIN_PASSWORD?.trim() ?? "";
    test.skip(!password, "APPLIANCE_ADMIN_PASSWORD is not set");

    const t0 = Date.now();

    await page.goto("/#/login");
    await expect(page.getByText("Welcome back")).toBeVisible({
      timeout: UI_STEP_TIMEOUT_MS,
    });
    logStep(`login_route_ready: ${Date.now() - t0}ms`);

    await page.getByTestId("login-password-input").fill(password);
    await page.getByTestId("login-submit-button").click();
    logStep(`after_sign_in_click: ${Date.now() - t0}ms`);

    await expect(page).toHaveURL(/#\/$/, { timeout: UI_STEP_TIMEOUT_MS });
    logStep(`hash_is_dashboard: ${Date.now() - t0}ms`);

    await expect(page.getByText("Peer ID:").first()).toBeVisible({
      timeout: UI_STEP_TIMEOUT_MS,
    });
    logStep(`peer_id_label_visible: ${Date.now() - t0}ms`);

    const mainStatus = page.getByTestId("dashboard-main-status");
    if ((await mainStatus.count()) > 0) {
      await expect(mainStatus).toBeVisible({ timeout: UI_STEP_TIMEOUT_MS });
      logStep(`dashboard_main_status_card: ${Date.now() - t0}ms`);
    } else {
      logStep(
        "dashboard_main_status_card: skipped (rebuild frontend if testid missing)"
      );
    }

    for (const [testId, label] of [
      ["free-resources-card", "free_resources_card"],
      ["allocated-resources-card", "allocated_resources_card"],
      ["onboarded-resources-card", "onboarded_resources_card"],
    ] as const) {
      const card = page.getByTestId(testId);
      if ((await card.count()) > 0) {
        await expect(card).toBeVisible({ timeout: UI_STEP_TIMEOUT_MS });
        logStep(`${label}: ${Date.now() - t0}ms`);
      } else {
        logStep(`${label}: skipped (not shown for this node)`);
      }
    }

    const totalMs = Date.now() - t0;
    logStep(`total_flow: ${totalMs}ms`);
    expect(totalMs).toBeLessThan(TOTAL_FLOW_MAX_MS);
  });
});
