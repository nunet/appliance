import { test, expect } from "@playwright/test";
import { authedRequest, ensureAppMode } from "./helpers";

test.describe.skip("Payments page (live API)", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAppMode(page, "simple");
    const request = await authedRequest();
    const config = await request.get("/payments/config");
    expect(config.ok()).toBeTruthy();
    const list = await request.get("/payments/list_payments");
    expect(list.ok()).toBeTruthy();
    await request.dispose();
    await page.goto("/#/payments");
    await expect(page.getByRole("heading", { name: "Payments" })).toBeVisible();
  });

  test("loads payments config and list from the real backend", async () => {
    const request = await authedRequest();
    const config = await request.get("/payments/config");
    const body = await config.json();
    expect(body.ethereum?.token_symbol).toBeTruthy();
    expect(body.cardano?.token_symbol).toBeTruthy();

    const list = await request.get("/payments/list_payments");
    const payments = await list.json();
    expect(typeof payments.total_count).toBe("number");
    expect(Array.isArray(payments.items)).toBeTruthy();
    await request.dispose();
  });

  test("renders payment cards when unpaid items exist", async ({ page }) => {
    const request = await authedRequest();
    const list = await request.get("/payments/list_payments");
    await request.dispose();
    const payments = await list.json();
    const items = (payments.items ?? []) as Array<{ unique_id: string }>;
    test.skip(items.length === 0, "No payment items on this appliance");

    const first = items[0]!;
    await expect(page.getByTestId(`payment-card-${first.unique_id}`)).toBeVisible({
      timeout: 30_000,
    });
  });
});
