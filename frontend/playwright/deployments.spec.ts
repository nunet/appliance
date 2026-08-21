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

  test("configure step resolves schema for Load More ensemble", async ({ page }) => {
    test.skip(skipDeployments, "DEPLOYMENTS_SKIP is set");
    test.setTimeout(180_000);
    await page.goto("/#/deploy/new", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("deployment-template-card").first()).toBeVisible({
      timeout: 60_000,
    });

    const loadMore = page.getByTestId("deployment-template-load-more");
    test.skip(!(await loadMore.isVisible()), "Fewer than one page of templates");

    const firstPageCount = await page.getByTestId("deployment-template-card").count();
    await loadMore.click();
    await expect
      .poll(async () => page.getByTestId("deployment-template-card").count(), {
        timeout: 30_000,
      })
      .toBeGreaterThan(firstPageCount);

    const cards = page.getByTestId("deployment-template-card");
    await cards.nth(firstPageCount).click();
    await page.getByTestId("deployment-next-button").click();
    await expect(page.getByTestId("deployment-step2")).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("deployment-target-non-targeted").click();
    await page.getByTestId("deployment-next-button").click();

    await expect(page.getByTestId("deployment-step3")).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/No template found for path:/i)).toHaveCount(0);
    logStep("Configure step loaded schema for Load More ensemble");
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
