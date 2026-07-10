import { test, expect, type Page } from "@playwright/test";
import { ensureAppMode } from "./helpers";

type DmsPaymentsListResponse = {
  total_count: number;
  paid_count: number;
  unpaid_count: number;
  ignored_count: number;
  items: Array<Record<string, unknown>>;
};

const PAYMENTS_CONFIG = {
  ethereum: {
    chain_id: 11155111,
    token_address: "0xB37216b70a745129966E553cF8Ee2C51e1cB359A",
    token_symbol: "TSTNTX",
    token_decimals: 16,
    explorer_base_url: "https://sepolia.etherscan.io/",
    network_name: "Ethereum Sepolia",
  },
  cardano: {
    chain_id: 1,
    token_address: "asset1tkxzxjklvs5gdkpuh26ex3re4rl8wjg3wmyxdr",
    token_symbol: "tNTX",
    token_decimals: 16,
    explorer_base_url: "https://preprod.cexplorer.io/",
    network_name: "Cardano Preprod",
    policy_id: "88b60b51a3dcd3a6134bb1c0fdd2837d8cc87abd27dbd0c3a494869f",
    asset_name_hex: "4e754e657450726570726f64",
    asset_name: "NuNetPreprod",
    asset_name_encoded: "4e754e657450726570726f64",
    asset_id: "asset1tkxzxjklvs5gdkpuh26ex3re4rl8wjg3wmyxdr",
  },
};

const baseListResponse: DmsPaymentsListResponse = {
  total_count: 1,
  paid_count: 0,
  unpaid_count: 1,
  ignored_count: 0,
  items: [
    {
      deployment_id: "did:key:deployment",
      unique_id: "550e8400-e29b-41d4-a716-446655440000",
      contract_did: "did:key:contract",
      to_address: "0x" + "a".repeat(40),
      from_address: "0x" + "b".repeat(40),
      amount: "1.0",
      status: "unpaid",
      tx_hash: "",
      blockchain: "ETHEREUM",
      metadata: null,
    },
  ],
};

function queryRecord(url: string): Record<string, string> {
  const params = new URL(url).searchParams;
  const out: Record<string, string> = {};
  params.forEach((value, key) => {
    out[key] = value;
  });
  return out;
}

async function setupPaymentsConfigMock(page: Page) {
  await page.route("**/payments/config", (route) =>
    route.fulfill({ json: PAYMENTS_CONFIG })
  );
}

async function openTextFilters(page: Page) {
  await page.getByRole("button", { name: /^Filters/ }).click();
  await expect(page.getByPlaceholder("Filter by deployment ID")).toBeVisible();
}

function installListPaymentsCapture(page: Page, pageRequests: Array<Record<string, string>>) {
  return page.route("**/payments/list_payments*", async (route) => {
    const q = queryRecord(route.request().url());
    if (q.limit) {
      pageRequests.push(q);
    }
    await route.fulfill({ json: baseListResponse });
  });
}

function isPaginatedListResponse(resp: { url: () => string; ok: () => boolean }) {
  return (
    resp.url().includes("/payments/list_payments") &&
    new URL(resp.url()).searchParams.has("limit") &&
    resp.ok()
  );
}

async function visitPaymentsPage(page: Page) {
  const pageListResponse = page.waitForResponse(isPaginatedListResponse);
  await setupPaymentsConfigMock(page);
  await ensureAppMode(page, "simple");
  await page.goto("/#/payments");
  await pageListResponse;
  await expect(page.getByRole("heading", { name: "Payments" })).toBeVisible();
}

test.describe.skip("Payments filters", () => {
  test("applies text filters on Enter and sends full mapped params", async ({ page }) => {
    const pageRequests: Array<Record<string, string>> = [];
    await installListPaymentsCapture(page, pageRequests);
    await visitPaymentsPage(page);

    await openTextFilters(page);
    await page.getByPlaceholder("Filter by deployment ID").fill("did:key:deployment-1");
    await page.getByPlaceholder("Filter by unique ID").fill("tx-123");
    await page.getByPlaceholder("Filter by contract DID").fill("did:key:contract-1");
    await page.getByPlaceholder("Destination address").fill("addr_to");
    await page.getByPlaceholder("Source address").fill("addr_from");
    await page.getByPlaceholder("On-chain hash").fill("hash-123");
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/payments/list_payments") &&
          new URL(resp.url()).searchParams.get("tx_hash") === "hash-123"
      ),
      page.getByPlaceholder("On-chain hash").press("Enter"),
    ]);

    await page.getByRole("combobox").nth(0).click();
    await page.getByRole("option", { name: "Cardano" }).click();

    await page.waitForResponse(
      (resp) =>
        resp.url().includes("/payments/list_payments") &&
        new URL(resp.url()).searchParams.get("blockchain") === "CARDANO"
    );

    await page.getByRole("combobox").nth(1).click();
    await page.getByRole("option", { name: "paid", exact: true }).click();

    await page.waitForResponse(
      (resp) =>
        resp.url().includes("/payments/list_payments") &&
        new URL(resp.url()).searchParams.get("status") === "paid"
    );

    const latest = pageRequests[pageRequests.length - 1]!;
    expect(latest.sort).toBe("-created_at");
    expect(latest.deployment_id).toBe("did:key:deployment-1");
    expect(latest.unique_id).toBe("tx-123");
    expect(latest.contract_did).toBe("did:key:contract-1");
    expect(latest.to_address).toBe("addr_to");
    expect(latest.from_address).toBe("addr_from");
    expect(latest.tx_hash).toBe("hash-123");
    expect(latest.blockchain).toBe("CARDANO");
    expect(latest.status).toBe("paid");
  });

  test("applies draft text filters when Apply Filters is clicked", async ({ page }) => {
    const pageRequests: Array<Record<string, string>> = [];
    await installListPaymentsCapture(page, pageRequests);
    await visitPaymentsPage(page);

    await openTextFilters(page);
    await page.getByPlaceholder("Filter by contract DID").fill("did:key:on-apply");

    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/payments/list_payments") &&
          new URL(resp.url()).searchParams.get("contract_did") === "did:key:on-apply"
      ),
      page.getByRole("button", { name: "Apply Filters" }).click(),
    ]);

    expect(pageRequests[pageRequests.length - 1]!.contract_did).toBe("did:key:on-apply");

    await openTextFilters(page);
    await page.getByPlaceholder("Filter by contract DID").clear();

    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes("/payments/list_payments") &&
          !new URL(resp.url()).searchParams.has("contract_did")
      ),
      page.getByRole("button", { name: "Clear Fields" }).click(),
    ]);

    expect(pageRequests[pageRequests.length - 1]!.contract_did).toBeUndefined();
  });

  test("does not call list endpoint on each typed character", async ({ page }) => {
    let listCount = 0;
    await page.route("**/payments/list_payments*", async (route) => {
      if (queryRecord(route.request().url()).limit) {
        listCount += 1;
      }
      await route.fulfill({ json: baseListResponse });
    });
    await visitPaymentsPage(page);
    const baselineListCalls = listCount;

    await openTextFilters(page);
    await page.getByPlaceholder("Filter by contract DID").pressSequentially("did:key:manyletters");
    await page.waitForTimeout(300);
    expect(listCount).toBe(baselineListCalls);

    await Promise.all([
      page.waitForResponse((resp) => resp.url().includes("/payments/list_payments")),
      page.getByPlaceholder("Filter by contract DID").press("Enter"),
    ]);
    expect(listCount).toBe(baselineListCalls + 1);
  });
});
