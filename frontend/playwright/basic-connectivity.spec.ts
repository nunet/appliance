import { test, expect } from '@playwright/test';

test.describe("load the app page and check if some elements are visible", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("shows the login page", async ({ page }) => {
    await page.goto("/#/login");
    await expect(page.getByText("Welcome back")).toBeVisible();
    await expect(page.getByText("Enter the admin password")).toBeVisible();
    await expect(page.getByTestId("login-form")).toBeVisible();
  });
});
