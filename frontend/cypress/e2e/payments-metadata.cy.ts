type DmsPaymentItem = {
  unique_id: string;
  payment_validator_did: string;
  contract_did: string;
  to_address: string;
  from_address?: string;
  amount: string;
  status: "paid" | "unpaid";
  tx_hash: string;
  blockchain?: "ETHEREUM" | "CARDANO";
  metadata?: Record<string, unknown> | null;
};

type DmsPaymentsListResponse = {
  total_count: number;
  paid_count: number;
  unpaid_count: number;
  ignored_count: number;
  ignored?: Array<{ unique_id: string; reason: string }>;
  items: DmsPaymentItem[];
};

const CARDANO_ADDRESS =
  "addr_test1qqm9ehanrh5rkukd0jwrl4j4zhnlzhkutwcukxqjdr3yfwydfmfydwq78revg8sx3wf3aj9gwn5kqyg0l2485zrj3mvsktcw4k";

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

const buildTx = (
  uniqueId: string,
  amount: string,
  metadata: Record<string, unknown> | null,
  options?: { blockchain?: "ETHEREUM" | "CARDANO"; toAddress?: string; fromAddress?: string }
): DmsPaymentItem => ({
  unique_id: uniqueId,
  payment_validator_did: "did:prism:validator",
  contract_did: "did:prism:contract",
  to_address: options?.toAddress ?? ("0x" + "a".repeat(40)),
  from_address: options?.fromAddress,
  amount,
  status: "unpaid",
  tx_hash: "",
  blockchain: options?.blockchain ?? "ETHEREUM",
  metadata,
});

const happyItems: DmsPaymentItem[] = [
  buildTx("550e8400-e29b-41d4-a716-446655440000", "10.500000", {
    deployment_id: "deployment-123",
    total_utilization_sec: 3600.0,
    allocation_count: 2,
    allocations: [
      { allocation_id: "alloc-1", duration_sec: 1800.0 },
      { allocation_id: "alloc-2", duration_sec: 1800.0 },
    ],
  }, { fromAddress: "0x" + "b".repeat(40) }),
  buildTx("550e8400-e29b-41d4-a716-446655440001", "25.750000", {
    deployment_id: "deployment-456",
    total_utilization_sec: 7200.0,
    allocation_count: 1,
    allocations: [
      {
        allocation_id: "alloc-3",
        resources: { cpu_cores: 4, ram_gb: 8, disk_gb: 100, gpu_count: 1 },
      },
    ],
  }),
  buildTx("550e8400-e29b-41d4-a716-446655440002", "50.000000", {
    deployment_id: "deployment-789",
    total_utilization_sec: 86400.0,
    period_start: "2024-01-01T00:00:00Z",
    period_end: "2024-01-31T23:59:59Z",
    periods_invoiced: 1,
    allocation_count: 3,
  }),
  buildTx("550e8400-e29b-41d4-a716-446655440003", "15.000000", {
    deployment_count: 3,
  }),
  buildTx("550e8400-e29b-41d4-a716-446655440004", "30.000000", {
    allocation_count: 5,
  }),
  buildTx("550e8400-e29b-41d4-a716-446655440005", "100.000000", {
    periods_invoiced: 1,
    period_start: "2024-01-01T00:00:00Z",
    period_end: "2024-01-31T23:59:59Z",
    last_invoice_at: "2023-12-31T23:59:59Z",
  }),
];

const happyListResponse: DmsPaymentsListResponse = {
  total_count: happyItems.length,
  paid_count: 0,
  unpaid_count: happyItems.length,
  ignored_count: 0,
  items: happyItems,
};

const sadItems: DmsPaymentItem[] = [
  buildTx("550e8400-e29b-41d4-a716-446655440100", "10.500000", null),
  buildTx("550e8400-e29b-41d4-a716-446655440101", "25.750000", {}, {
    blockchain: "CARDANO",
    toAddress: CARDANO_ADDRESS,
  }),
  buildTx("550e8400-e29b-41d4-a716-446655440102", "50.000000", null),
  buildTx("550e8400-e29b-41d4-a716-446655440103", "15.000000", {}),
  buildTx("550e8400-e29b-41d4-a716-446655440104", "30.000000", null),
  buildTx("550e8400-e29b-41d4-a716-446655440105", "100.000000", {}),
];

const sadListResponse: DmsPaymentsListResponse = {
  total_count: sadItems.length,
  paid_count: 0,
  unpaid_count: sadItems.length,
  ignored_count: 2,
  ignored: [
    { unique_id: "bad-1", reason: "invalid amount" },
    { unique_id: "bad-2", reason: "missing destination address" },
  ],
  items: sadItems,
};

const setupAuthAndShellInterceptors = () => {
  cy.intercept("GET", "**/auth/status", {
    statusCode: 200,
    body: { password_set: true, username: "admin" },
  }).as("authStatus");

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

  cy.intercept("GET", "**/dms/status/full", {
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

  cy.intercept("GET", "**/sys/local-ip", { statusCode: 200, body: "127.0.0.1" });
  cy.intercept("GET", "**/sys/public-ip", { statusCode: 200, body: "127.0.0.1" });
  cy.intercept("GET", "**/sys/appliance-version", { statusCode: 200, body: "0.0.0-e2e" });
  cy.intercept("GET", "**/sys/ssh-status", { statusCode: 200, body: { running: true, authorized_keys: 1 } });
  cy.intercept("GET", "**/sys/check-updates", {
    statusCode: 200,
    body: JSON.stringify({ available: false, current: "0.0.0", latest: "0.0.0" }),
  });
  cy.intercept("GET", "**/dms/check-updates", {
    statusCode: 200,
    body: JSON.stringify({ available: false, current: "0.0.0", latest: "0.0.0" }),
  });
  cy.intercept("GET", "**/sys/docker/containers", {
    statusCode: 200,
    body: { count: 0, containers: [] },
  });
};

const buildEthereumProviderMock = (account: string) => ({
  request: ({ method }: { method: string; params?: unknown[] }) => {
    switch (method) {
      case "eth_accounts":
      case "eth_requestAccounts":
        return Promise.resolve([account]);
      case "eth_chainId":
        return Promise.resolve("0xaa36a7"); // 11155111 Sepolia
      case "wallet_switchEthereumChain":
        return Promise.resolve(null);
      default:
        return Promise.resolve(null);
    }
  },
  on: () => undefined,
  removeListener: () => undefined,
});

const visitPayments = (
  listPayload: DmsPaymentsListResponse,
  options?: { ethereumAccount?: string }
) => {
  setupAuthAndShellInterceptors();

  cy.intercept("GET", "**/payments/config", {
    statusCode: 200,
    body: PAYMENTS_CONFIG,
  }).as("paymentsConfig");

  cy.intercept("GET", "**/payments/list_payments", {
    statusCode: 200,
    body: listPayload,
  }).as("paymentsList");

  cy.visit("/#/payments", {
    onBeforeLoad(win) {
      win.localStorage.setItem("nunet-admin-token", "e2e-token");
      win.localStorage.setItem("nunet-admin-expiry", String(Date.now() + 60 * 60 * 1000));
      if (options?.ethereumAccount) {
        (win as unknown as { ethereum?: unknown }).ethereum = buildEthereumProviderMock(options.ethereumAccount);
      }
    },
  });

  cy.wait("@authStatus");
  cy.wait("@paymentsConfig");
  cy.wait("@paymentsList");
  cy.contains("h2", "Payments").should("be.visible");
};

describe("Payments metadata matrix", () => {
  it("renders metadata details for all six payment types (happy path)", () => {
    visitPayments(happyListResponse);

    const expectedSnippets: Array<{ id: string; snippets: string[] }> = [
      {
        id: "550e8400-e29b-41d4-a716-446655440000",
        snippets: ["deployment deployment-123", "allocations alloc-1, alloc-2", "runtime 1h"],
      },
      {
        id: "550e8400-e29b-41d4-a716-446655440001",
        snippets: ["deployment deployment-456", "allocations alloc-3", "runtime 2h"],
      },
      {
        id: "550e8400-e29b-41d4-a716-446655440002",
        snippets: ["deployment deployment-789", "runtime 1d", "1 period invoiced"],
      },
      {
        id: "550e8400-e29b-41d4-a716-446655440003",
        snippets: ["3 deployments"],
      },
      {
        id: "550e8400-e29b-41d4-a716-446655440004",
        snippets: ["5 allocations"],
      },
      {
        id: "550e8400-e29b-41d4-a716-446655440005",
        snippets: ["1 period invoiced", "last invoice"],
      },
    ];

    expectedSnippets.forEach(({ id, snippets }) => {
      cy.get(`[data-testid="payment-card-${id}"]`).within(() => {
        cy.get('[data-testid="payment-metadata-summary"]').should("be.visible");
        snippets.forEach((snippet) => {
          cy.get('[data-testid="payment-metadata-summary"]').should("contain.text", snippet);
        });
      });
    });

    cy.get('[data-testid="payment-card-550e8400-e29b-41d4-a716-446655440000"]')
      .contains("From:")
      .should("be.visible");

    cy.get('[data-testid="payment-card-550e8400-e29b-41d4-a716-446655440000"]')
      .contains("button", "Details")
      .click();
    cy.get('[data-testid="payment-card-550e8400-e29b-41d4-a716-446655440000"]')
      .contains("Payment Details")
      .should("be.visible");
    cy.get('[data-testid="payment-card-550e8400-e29b-41d4-a716-446655440000"]')
      .contains("From Address")
      .should("be.visible");
    cy.get('[data-testid="payment-card-550e8400-e29b-41d4-a716-446655440000"]')
      .contains("Raw Metadata JSON")
      .should("be.visible");

    cy.get('input[placeholder="Search by id address or status"]').clear().type("deployment-789");
    cy.get('[data-testid^="payment-card-"]').should("have.length", 1);
    cy.get('[data-testid="payment-card-550e8400-e29b-41d4-a716-446655440002"]').should("be.visible");
  });

  it("keeps Pay Now when connected wallet differs from metadata from_address", () => {
    visitPayments(happyListResponse, {
      ethereumAccount: "0x" + "c".repeat(40),
    });

    cy.get('[data-testid="payment-card-550e8400-e29b-41d4-a716-446655440000"]')
      .contains("button", "Pay Now", { timeout: 10000 })
      .should("be.visible")
      .and("be.enabled");

    cy.get('[data-testid="payment-card-550e8400-e29b-41d4-a716-446655440000"]')
      .contains("button", "Switch Account")
      .should("not.exist");
  });

  it("handles missing/empty metadata and wallet restrictions without crashing (sad path)", () => {
    visitPayments(sadListResponse);

    cy.contains("2 transactions skipped due to incomplete DMS data.").should("be.visible");

    sadItems.forEach((item) => {
      cy.get(`[data-testid="payment-card-${item.unique_id}"]`).within(() => {
        cy.get('[data-testid="payment-metadata-summary"]').should("not.exist");
      });
    });

    cy.get('[data-testid="payment-card-550e8400-e29b-41d4-a716-446655440100"]').within(() => {
      cy.contains("button", "Use MetaMask").should("be.disabled");
    });

    cy.get('[data-testid="payment-card-550e8400-e29b-41d4-a716-446655440101"]').within(() => {
      cy.contains("button", "Use Eternl").should("be.disabled");
    });

    cy.get('input[placeholder="Search by id address or status"]').clear().type("deployment-that-does-not-exist");
    cy.contains("Nothing to show").should("be.visible");
  });
});
