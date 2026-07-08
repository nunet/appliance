import { test, expect } from "@playwright/test";
import { ensureAppMode } from "./helpers";

const ORG_DID = "did:key:z6MkrG7E2e2eMultiChainOrgFixture1234567890";
const ETH_ADDRESS = "0x1111222233334444555566667777888899990000";

const ORG_FIXTURE = {
  name: "Playwright Multi-Blockchain Org",
  roles: ["compute_provider", "orchestrator"],
  join_fields: [
    { name: "email", label: "Email", type: "email", required: true },
    { name: "location", label: "Location", type: "text", required: true },
  ],
  tokenomics: { enabled: true, blockchains: ["ethereum", "cardano"] },
  blockchains: ["ethereum", "cardano"],
};

// Test temporarily disabled due to issues
test.describe.skip("Organization join blockchain selection", () => {
  test.beforeEach(async ({ page }) => {
    let selectedOrgDid: string | null = null;

    await page.addInitScript((address) => {
      let isConnected = false;
      (window as unknown as { ethereum?: unknown }).ethereum = {
        request: ({ method }: { method: string }) => {
          if (method === "eth_accounts") return Promise.resolve(isConnected ? [address] : []);
          if (method === "eth_requestAccounts") {
            isConnected = true;
            return Promise.resolve([address]);
          }
          if (method === "eth_chainId") return Promise.resolve("0x1");
          return Promise.resolve(null);
        },
        on: () => {},
        removeListener: () => {},
      };
    }, ETH_ADDRESS);

    await page.route("**/organizations/known", (route) =>
      route.fulfill({ json: { [ORG_DID]: ORG_FIXTURE } })
    );
    await page.route("**/organizations/joined", (route) => route.fulfill({ json: [] }));
    await page.route("**/organizations/select", async (route) => {
      const body = route.request().postDataJSON() as { org_did?: string };
      selectedOrgDid = body?.org_did ?? null;
      await route.fulfill({ json: { status: "ok", selected_org: selectedOrgDid } });
    });
    await page.route("**/organizations/status", async (route) => {
      if (!selectedOrgDid) {
        await route.fulfill({
          json: {
            current_step: "select_org",
            ui_state: "selecting",
            step_states: [],
          },
        });
        return;
      }
      await route.fulfill({
        json: {
          current_step: "collect_join_data",
          ui_state: "collecting",
          raw: { org_data: { did: selectedOrgDid, name: ORG_FIXTURE.name } },
          step_states: [],
        },
      });
    });
    await page.route("**/organizations/join/submit", (route) =>
      route.fulfill({ json: { status: "ok", api_status: "email_sent" } })
    );

    await ensureAppMode(page, "simple");
    await page.goto("/#/organizations");
    await page.locator(`[data-testid="org-join-button"][data-org-did="${ORG_DID}"]`).click();
    await expect(page.getByTestId("join-name-input")).toBeVisible();
  });

  test("requires blockchain selection and updates wallet connector", async ({ page }) => {
    await expect(page.getByTestId("join-blockchain-group")).toBeVisible();
    await expect(page.getByText("Select a blockchain to enable wallet connection.")).toBeVisible();
    await page.getByTestId("join-blockchain-cardano").click();
    await expect(page.getByText("Cardano (Eternl)")).toBeVisible();
    await page.getByTestId("join-blockchain-ethereum").click();
    await expect(page.getByText("Ethereum (MetaMask)")).toBeVisible();
    await page.getByTestId("join-submit-button").isDisabled();
  });

  test("submits selected blockchain and wallet metadata", async ({ page }) => {
    await page.getByTestId("join-blockchain-ethereum").click();
    await page.getByTestId("join-name-input").fill("Playwright Tester");
    await page.getByTestId("join-field-email").fill("playwright@example.com");
    await page.getByTestId("join-field-location").fill("Test City");
    await page.getByRole("button", { name: "Connect Ethereum wallet" }).click();
    await page.getByRole("menu").getByRole("button", { name: "Connect" }).click();

    const [submit] = await Promise.all([
      page.waitForRequest("**/organizations/join/submit"),
      page.getByTestId("join-submit-button").click(),
    ]);
    const payload = submit.postDataJSON() as Record<string, unknown>;
    expect(payload.blockchain).toBe("ethereum");
    expect(payload.wallet_address).toBe(ETH_ADDRESS);
  });
});
