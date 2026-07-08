import { test, expect } from "@playwright/test";
import { authedRequest, ensureAppMode, logStep, openSidebar } from "./helpers";

const skipDestructive = ["1", "true", "yes"].includes(
  String(process.env.ENSEMBLE_SKIP_DESTRUCTIVE ?? "").toLowerCase()
);

async function openEnsembles(page: import("@playwright/test").Page) {
  await page.goto("/#/");
  await openSidebar(page, /^Ensembles$/);
  await expect(page).toHaveURL(/#\/ensembles/);
  await expect(page.getByTestId("ensembles-card")).toBeVisible();
}

test.describe.skip("Ensembles CRUD + JSON flows", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAppMode(page, "simple");
    await openEnsembles(page);
  });

  test("shows default ensembles on load", async ({ page }) => {
    await expect(page.getByTestId("ensemble-list")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("ensemble-row")).not.toHaveCount(0);
  });

  test("opens create ensemble dialog", async ({ page }) => {
    test.skip(skipDestructive, "ENSEMBLE_SKIP_DESTRUCTIVE is set");
    await page.getByTestId("ensemble-add-button").first().click();
    await expect(page.getByTestId("ensemble-upload-dialog")).toBeVisible();
    logStep("Create dialog opened");
  });

  test("lists ensembles via API", async () => {
    const request = await authedRequest();
    const resp = await request.get("/ensemble/templates");
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(Array.isArray(body.items)).toBeTruthy();
    await request.dispose();
  });
});
