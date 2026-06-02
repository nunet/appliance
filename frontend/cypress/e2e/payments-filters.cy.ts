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

function setupCommonInterceptors() {
  cy.intercept("GET", "**/auth/status", {
    statusCode: 200,
    body: { password_set: true, username: "admin" },
  });
  cy.intercept("GET", "**/sys/environment*", {
    statusCode: 200,
    body: {
      environment: "production",
      updates: {
        appliance: { channel: "stable", resolved_channel: "stable", fell_back: false },
        dms: { channel: "stable", resolved_channel: "stable", fell_back: false },
      },
      ethereum: {
        chain_id: 1,
        token_address: "0x" + "0".repeat(40),
        token_symbol: "NTX",
        token_decimals: 18,
      },
    },
  });
  cy.intercept("GET", "**/dms/status", {
    statusCode: 200,
    body: {
      dms_status: "running",
      dms_version: "v0",
      dms_running: true,
      dms_context: "user",
      dms_did: "did:key:e2e",
      dms_peer_id: "peer-e2e",
      dms_is_relayed: false,
    },
  });
  cy.intercept("GET", "**/dms/status/resources", {
    statusCode: 200,
    body: {
      onboarding_status: "ONBOARDED",
      free_resources: "N/A",
      allocated_resources: "N/A",
      onboarded_resources: "N/A",
    },
  });
  cy.intercept("GET", "**/dms/peers/self", {
    statusCode: 200,
    body: {
      dms_status: "running",
      dms_version: "v0",
      dms_running: true,
      dms_context: "user",
      dms_did: "did:key:e2e",
      dms_peer_id: "peer-e2e",
      dms_is_relayed: false,
    },
  });
  cy.intercept("GET", "**/dms/peers/connected", {
    statusCode: 200,
    body: { raw: "" },
  });
  cy.intercept("GET", "**/payments/config", { statusCode: 200, body: PAYMENTS_CONFIG });
}

describe("Payments filters", () => {
  it("applies text filters on Enter and sends full mapped params", () => {
    const pageRequests: Array<Record<string, string | string[]>> = [];
    setupCommonInterceptors();
    cy.intercept("GET", "**/payments/list_payments*", (req) => {
      const q = req.query as Record<string, string | string[]>;
      if (q.limit) {
        pageRequests.push(q);
      }
      req.reply({ statusCode: 200, body: baseListResponse });
    }).as("paymentsList");

    cy.visit("/#/payments", {
      onBeforeLoad(win) {
        win.localStorage.setItem("nunet-admin-token", "e2e-token");
        win.localStorage.setItem("nunet-admin-expiry", String(Date.now() + 60 * 60 * 1000));
      },
    });

    cy.wait("@paymentsList");
    cy.wait("@paymentsList");

    cy.get('input[placeholder="Filter by deployment ID"]').type("did:key:deployment-1");
    cy.get('input[placeholder="Filter by unique ID"]').type("tx-123");
    cy.get('input[placeholder="Filter by contract DID"]').type("did:key:contract-1");
    cy.get('input[placeholder="Filter by destination address"]').type("addr_to");
    cy.get('input[placeholder="Filter by source address"]').type("addr_from");
    cy.get('input[placeholder="Filter by transaction hash"]').type("hash-123{enter}");

    cy.get('[aria-label="Filter blockchain"]').click();
    cy.contains("[role='option']", "Cardano").click();
    cy.get('[aria-label="Filter status"]').click();
    cy.contains("[role='option']", "paid").click();

    cy.wait("@paymentsList");

    cy.then(() => {
      const latest = pageRequests[pageRequests.length - 1];
      expect(latest.sort).to.eq("-created_at");
      expect(latest.deployment_id).to.eq("did:key:deployment-1");
      expect(latest.unique_id).to.eq("tx-123");
      expect(latest.contract_did).to.eq("did:key:contract-1");
      expect(latest.to_address).to.eq("addr_to");
      expect(latest.from_address).to.eq("addr_from");
      expect(latest.tx_hash).to.eq("hash-123");
      expect(latest.blockchain).to.eq("CARDANO");
      expect(latest.status).to.eq("paid");
    });
  });

  it("applies draft text filters when Refresh is clicked (without Enter)", () => {
    const pageRequests: Array<Record<string, string | string[]>> = [];
    setupCommonInterceptors();
    cy.intercept("GET", "**/payments/list_payments*", (req) => {
      const q = req.query as Record<string, string | string[]>;
      if (q.limit) {
        pageRequests.push(q);
      }
      req.reply({ statusCode: 200, body: baseListResponse });
    }).as("paymentsList");

    cy.visit("/#/payments", {
      onBeforeLoad(win) {
        win.localStorage.setItem("nunet-admin-token", "e2e-token");
        win.localStorage.setItem("nunet-admin-expiry", String(Date.now() + 60 * 60 * 1000));
      },
    });

    cy.wait("@paymentsList");
    cy.wait("@paymentsList");

    cy.get('input[placeholder="Filter by contract DID"]').type("did:key:on-refresh");
    cy.contains("button", "Refresh").click();
    cy.wait("@paymentsList");

    cy.then(() => {
      const latest = pageRequests[pageRequests.length - 1];
      expect(latest.contract_did).to.eq("did:key:on-refresh");
    });

    cy.get('input[placeholder="Filter by contract DID"]').clear();
    cy.contains("button", "Refresh").click();
    cy.wait("@paymentsList");

    cy.then(() => {
      const latest = pageRequests[pageRequests.length - 1];
      expect(latest.contract_did).to.be.undefined;
    });
  });

  it("does not call list endpoint on each typed character", () => {
    let listCount = 0;
    setupCommonInterceptors();
    cy.intercept("GET", "**/payments/list_payments*", (req) => {
      listCount += 1;
      req.reply({ statusCode: 200, body: baseListResponse });
    }).as("paymentsList");

    cy.visit("/#/payments", {
      onBeforeLoad(win) {
        win.localStorage.setItem("nunet-admin-token", "e2e-token");
        win.localStorage.setItem("nunet-admin-expiry", String(Date.now() + 60 * 60 * 1000));
      },
    });

    cy.wait("@paymentsList");
    cy.wait("@paymentsList");
    cy.then(() => {
      expect(listCount).to.eq(2);
    });

    cy.get('input[placeholder="Filter by contract DID"]').type("did:key:manyletters");
    cy.wait(300);
    cy.then(() => {
      expect(listCount).to.eq(2);
    });

    cy.get('input[placeholder="Filter by contract DID"]').type("{enter}");
    cy.wait("@paymentsList");
    cy.then(() => {
      expect(listCount).to.eq(3);
    });
  });
});
