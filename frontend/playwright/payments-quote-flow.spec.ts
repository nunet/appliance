import { test, expect } from "@playwright/test";
import { ensureAppMode } from "./helpers";

const PAYMENT_ID = "550e8400-e29b-41d4-a716-446655449001";
const QUOTE_ID = "quote-pay-9001";

test.describe.skip("Payments quote conversion flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/payments/config", (route) =>
      route.fulfill({
        json: {
          ethereum: {
            chain_id: 11155111,
            token_symbol: "TSTNTX",
            token_decimals: 16,
          },
          cardano: { chain_id: 1, token_symbol: "tNTX", token_decimals: 16 },
        },
      })
    );
    await page.route("**/payments/list_payments", (route) =>
      route.fulfill({
        json: {
          total_count: 1,
          paid_count: 0,
          unpaid_count: 1,
          ignored_count: 0,
          items: [
            {
              unique_id: PAYMENT_ID,
              payment_validator_did: "did:prism:validator",
              contract_did: "did:prism:contract",
              to_address: "0x" + "a".repeat(40),
              amount: "10.00",
              original_amount: "10.00",
              pricing_currency: "USDT",
              requires_conversion: true,
              status: "unpaid",
              tx_hash: "",
              blockchain: "ETHEREUM",
            },
          ],
        },
      })
    );
    await page.route("**/payments/quote/get", (route) =>
      route.fulfill({
        json: {
          quote_id: QUOTE_ID,
          original_amount: "10.00",
          converted_amount: "123.45670000",
          pricing_currency: "USDT",
          payment_currency: "NTX",
          exchange_rate: "12.34567000",
          expires_at: "2030-01-01T00:00:00Z",
        },
      })
    );
    await page.route("**/payments/quote/validate", (route) =>
      route.fulfill({
        json: {
          valid: true,
          quote_id: QUOTE_ID,
          original_amount: "10.00",
          converted_amount: "123.45670000",
          pricing_currency: "USDT",
          payment_currency: "NTX",
          exchange_rate: "12.34567000",
          expires_at: "2030-01-01T00:00:00Z",
        },
      })
    );
    await page.route("**/payments/quote/cancel", (route) =>
      route.fulfill({ json: { status: "cancelled" } })
    );

    await page.addInitScript(() => {
      const account = "0x" + "d".repeat(40);
      (window as unknown as { ethereum?: unknown }).ethereum = {
        request: ({ method }: { method: string }) => {
          if (method === "eth_accounts" || method === "eth_requestAccounts") {
            return Promise.resolve([account]);
          }
          if (method === "eth_chainId") return Promise.resolve("0xaa36a7");
          return Promise.resolve(null);
        },
        on: () => {},
        removeListener: () => {},
      };
    });

    await ensureAppMode(page, "simple");
    await page.goto("/#/payments");
    await expect(page.getByRole("heading", { name: "Payments" })).toBeVisible();
  });

  test("creates quote, validates it, and cancels from confirmation modal", async ({
    page,
  }) => {
    const card = page.getByTestId(`payment-card-${PAYMENT_ID}`);
    await card.getByRole("button", { name: "Pay Now" }).click();

    await expect(page.getByText("Confirm conversion quote")).toBeVisible();
    await expect(page.getByText("USDT 10.00")).toBeVisible();
    await expect(page.getByText("NTX 123.45670000")).toBeVisible();

    const [cancel] = await Promise.all([
      page.waitForRequest("**/payments/quote/cancel"),
      page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click(),
    ]);
    expect(cancel.postDataJSON()).toMatchObject({
      quote_id: QUOTE_ID,
      dest: "did:prism:validator",
    });
  });
});
