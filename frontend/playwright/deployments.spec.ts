import { test, expect } from "@playwright/test";
import { ensureAppMode, logStep, openSidebar } from "./helpers";

const skipDeployments = ["1", "true", "yes"].includes(
  String(process.env.DEPLOYMENTS_SKIP ?? "").toLowerCase()
);

async function openDeploymentsList(page: import("@playwright/test").Page) {
  await page.goto("/#/deploy");
  await expect(page).toHaveURL(/#\/deploy/);
  await expect(page.getByTestId("deployment-search-input")).toBeVisible({
    timeout: 120_000,
  });
}

test.describe.skip("Deployments wizard + details", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAppMode(page, "simple");
  });

  test("opens new deployment wizard with templates", async ({ page }) => {
    test.skip(skipDeployments, "DEPLOYMENTS_SKIP is set");
    test.setTimeout(180_000);
    await page.goto("/#/deploy/new", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/#\/deploy\/new/);
    await expect(page.getByTestId("deployment-wizard")).toBeVisible();
    await expect(page.getByTestId("deployment-template-card").first()).toBeVisible({
      timeout: 60_000,
    });
    logStep("Deployment wizard loaded with templates");
  });

  test("filters deployments list when deployments exist", async ({ page }) => {
    test.skip(skipDeployments, "DEPLOYMENTS_SKIP is set");
    await openDeploymentsList(page);
    const cards = page.getByTestId("deployment-card");
    const count = await cards.count();
    test.skip(count === 0, "No deployments on this appliance");
    const deploymentId = await cards.first().getAttribute("data-deployment-id");
    expect(deploymentId).toBeTruthy();
    await page.getByTestId("deployment-search-input").fill(deploymentId!);
    await expect(page.locator(`[data-deployment-id="${deploymentId}"]`)).toBeVisible();
  });
});
