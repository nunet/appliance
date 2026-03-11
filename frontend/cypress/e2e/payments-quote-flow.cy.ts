type DmsPaymentItem = {
  unique_id: string;
  payment_validator_did: string;
  contract_did: string;
  to_address: string;
  from_address?: string;
  amount: string;
  original_amount?: string;
  pricing_currency?: string;
  requires_conversion?: boolean;
  status: "paid" | "unpaid";
  tx_hash: string;
  blockchain?: string;
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

type StoredPaymentQuote = {
  uniqueId: string;
  quoteId: string;
  originalAmount: string;
  convertedAmount: string;
  pricingCurrency: string;
  paymentCurrency: string;
  exchangeRate: string;
  expiresAt: string;
};

const ACTIVE_QUOTES_STORAGE_KEY = "nunet-payments-active-quotes-v1";

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

const buildEthereumProviderMock = (options?: { account?: string; connected?: boolean }) => {
  const account = options?.account ?? ("0x" + "d".repeat(40));
  const connected = options?.connected ?? true;
  return {
    request: ({ method }: { method: string; params?: unknown[] }) => {
      switch (method) {
        case "eth_accounts":
          return Promise.resolve(connected ? [account] : []);
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
  };
};

const buildConversionItem = (uniqueId: string): DmsPaymentItem => ({
  unique_id: uniqueId,
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
  metadata: null,
});

const buildListPayload = (item: DmsPaymentItem): DmsPaymentsListResponse => ({
  total_count: 1,
  paid_count: 0,
  unpaid_count: 1,
  ignored_count: 0,
  items: [item],
});

const visitPayments = (
  listPayload: DmsPaymentsListResponse,
  options?: {
    ethereumProvider?: { account?: string; connected?: boolean };
    activeQuotes?: Record<string, StoredPaymentQuote>;
  }
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

      if (options?.activeQuotes) {
        win.localStorage.setItem(ACTIVE_QUOTES_STORAGE_KEY, JSON.stringify(options.activeQuotes));
      }

      if (options?.ethereumProvider) {
        (win as unknown as { ethereum?: unknown }).ethereum = buildEthereumProviderMock(options.ethereumProvider);
      }
    },
  });

  cy.wait("@authStatus");
  cy.wait("@paymentsConfig");
  cy.wait("@paymentsList");
  cy.contains("h2", "Payments").should("be.visible");

  if (options?.ethereumProvider?.connected) {
    cy.get("header").contains("MetaMask", { timeout: 10000 }).should("be.visible");
  }
};

const clickVisibleCardButton = (uniqueId: string, label: string) => {
  cy.get(`[data-testid="payment-card-${uniqueId}"] button:visible`)
    .contains(label)
    .click();
};

describe("Payments quote conversion flow", () => {
  it("creates quote, validates it, and cancels from confirmation modal", () => {
    const payment = buildConversionItem("550e8400-e29b-41d4-a716-446655449001");
    const quoteId = "quote-pay-9001";
    let getRequestBody: Record<string, unknown> | undefined;
    let validateRequestBody: Record<string, unknown> | undefined;
    let cancelRequestBody: Record<string, unknown> | undefined;

    cy.intercept("POST", "**/payments/quote/get", (req) => {
      getRequestBody = req.body as Record<string, unknown>;
      req.reply({
        statusCode: 200,
        body: {
          quote_id: quoteId,
          original_amount: "10.00",
          converted_amount: "123.45670000",
          pricing_currency: "USDT",
          payment_currency: "NTX",
          exchange_rate: "12.34567000",
          expires_at: "2030-01-01T00:00:00Z",
        },
      });
    }).as("quoteGet");

    cy.intercept("POST", "**/payments/quote/validate", (req) => {
      validateRequestBody = req.body as Record<string, unknown>;
      req.reply({
        statusCode: 200,
        body: {
          valid: true,
          quote_id: quoteId,
          original_amount: "10.00",
          converted_amount: "123.45670000",
          pricing_currency: "USDT",
          payment_currency: "NTX",
          exchange_rate: "12.34567000",
          expires_at: "2030-01-01T00:00:00Z",
        },
      });
    }).as("quoteValidate");

    cy.intercept("POST", "**/payments/quote/cancel", (req) => {
      cancelRequestBody = req.body as Record<string, unknown>;
      req.reply({ statusCode: 200, body: { status: "cancelled" } });
    }).as("quoteCancel");

    visitPayments(buildListPayload(payment), {
      ethereumProvider: { connected: true },
    });

    clickVisibleCardButton(payment.unique_id, "Pay Now");

    cy.wait("@quoteGet");
    cy.wait("@quoteValidate");
    cy.then(() => {
      expect(getRequestBody).to.deep.equal({ unique_id: payment.unique_id });
      expect(validateRequestBody).to.deep.equal({ quote_id: quoteId });
    });

    cy.contains("Confirm conversion quote").should("be.visible");
    cy.contains("USDT 10.00").should("be.visible");
    cy.contains("NTX 123.45670000").should("be.visible");
    cy.contains("Exchange rate: 12.34567000").should("be.visible");

    cy.get('[role="dialog"] button:visible').contains("Cancel").click();
    cy.wait("@quoteCancel");
    cy.then(() => {
      expect(cancelRequestBody).to.deep.equal({ quote_id: quoteId });
    });

    cy.contains("Confirm conversion quote").should("not.exist");
  });

  it("shows quote validation failure and retries with a fresh quote", () => {
    const payment = buildConversionItem("550e8400-e29b-41d4-a716-446655449002");
    const staleQuoteId = "quote-stale-9002";
    const freshQuoteId = "quote-fresh-9002";
    const getCalls: string[] = [];
    const validateCalls: string[] = [];
    const cancelCalls: string[] = [];

    cy.intercept("POST", "**/payments/quote/get", (req) => {
      const isFirst = getCalls.length === 0;
      const quoteId = isFirst ? staleQuoteId : freshQuoteId;
      getCalls.push(quoteId);
      req.reply({
        statusCode: 200,
        body: {
          quote_id: quoteId,
          original_amount: "10.00",
          converted_amount: isFirst ? "90.00000000" : "91.25000000",
          pricing_currency: "USDT",
          payment_currency: "NTX",
          exchange_rate: isFirst ? "9.00000000" : "9.12500000",
          expires_at: "2030-01-01T00:00:00Z",
        },
      });
    }).as("quoteGet");

    cy.intercept("POST", "**/payments/quote/validate", (req) => {
      const quoteId = String((req.body as { quote_id?: string }).quote_id ?? "");
      validateCalls.push(quoteId);
      if (quoteId === staleQuoteId) {
        req.reply({
          statusCode: 200,
          body: { valid: false, error: "quote expired", quote_id: staleQuoteId },
        });
        return;
      }
      req.reply({
        statusCode: 200,
        body: {
          valid: true,
          quote_id: freshQuoteId,
          original_amount: "10.00",
          converted_amount: "91.25000000",
          pricing_currency: "USDT",
          payment_currency: "NTX",
          exchange_rate: "9.12500000",
          expires_at: "2030-01-01T00:00:00Z",
        },
      });
    }).as("quoteValidate");

    cy.intercept("POST", "**/payments/quote/cancel", (req) => {
      const quoteId = String((req.body as { quote_id?: string }).quote_id ?? "");
      cancelCalls.push(quoteId);
      req.reply({ statusCode: 200, body: { status: "cancelled" } });
    }).as("quoteCancel");

    visitPayments(buildListPayload(payment), {
      ethereumProvider: { connected: true },
    });

    clickVisibleCardButton(payment.unique_id, "Pay Now");
    cy.wait("@quoteGet");
    cy.wait("@quoteValidate");
    cy.wait("@quoteCancel");

    cy.contains("Quote validation failed").should("be.visible");
    cy.contains("quote expired").should("be.visible");

    cy.get('[role="dialog"] button:visible').contains("Try again").click();

    cy.wait("@quoteGet");
    cy.wait("@quoteValidate");

    cy.contains("Confirm conversion quote").should("be.visible");
    cy.contains("NTX 91.25000000").should("be.visible");

    cy.get('[role="dialog"] button:visible').contains("Cancel").click();
    cy.wait("@quoteCancel");

    cy.then(() => {
      expect(getCalls).to.deep.equal([staleQuoteId, freshQuoteId]);
      expect(validateCalls).to.deep.equal([staleQuoteId, freshQuoteId]);
      expect(cancelCalls).to.deep.equal([staleQuoteId, freshQuoteId]);
    });
  });

  it("recovers stored quote and resumes payment without requesting a new quote", () => {
    const payment = buildConversionItem("550e8400-e29b-41d4-a716-446655449003");
    const recoveredQuoteId = "quote-recovered-9003";
    let getQuoteCalls = 0;
    const validateCalls: string[] = [];
    const cancelCalls: string[] = [];

    const storedQuotes: Record<string, StoredPaymentQuote> = {
      [payment.unique_id]: {
        uniqueId: payment.unique_id,
        quoteId: recoveredQuoteId,
        originalAmount: "10.00",
        convertedAmount: "88.00000000",
        pricingCurrency: "USDT",
        paymentCurrency: "NTX",
        exchangeRate: "8.80000000",
        expiresAt: "2030-01-01T00:00:00Z",
      },
    };

    cy.intercept("POST", "**/payments/quote/get", (req) => {
      getQuoteCalls += 1;
      req.reply({
        statusCode: 200,
        body: {
          quote_id: "unexpected-new-quote",
          original_amount: "10.00",
          converted_amount: "99.00000000",
          pricing_currency: "USDT",
          payment_currency: "NTX",
          exchange_rate: "9.90000000",
          expires_at: "2030-01-01T00:00:00Z",
        },
      });
    }).as("quoteGet");

    cy.intercept("POST", "**/payments/quote/validate", (req) => {
      const quoteId = String((req.body as { quote_id?: string }).quote_id ?? "");
      validateCalls.push(quoteId);
      req.reply({
        statusCode: 200,
        body: {
          valid: true,
          quote_id: recoveredQuoteId,
          original_amount: "10.00",
          converted_amount: "88.00000000",
          pricing_currency: "USDT",
          payment_currency: "NTX",
          exchange_rate: "8.80000000",
          expires_at: "2030-01-01T00:00:00Z",
        },
      });
    }).as("quoteValidate");

    cy.intercept("POST", "**/payments/quote/cancel", (req) => {
      const quoteId = String((req.body as { quote_id?: string }).quote_id ?? "");
      cancelCalls.push(quoteId);
      req.reply({ statusCode: 200, body: { status: "cancelled" } });
    }).as("quoteCancel");

    visitPayments(buildListPayload(payment), {
      ethereumProvider: { connected: true },
      activeQuotes: storedQuotes,
    });

    cy.wait("@quoteValidate");
    cy.get(`[data-testid="payment-card-${payment.unique_id}"]`)
      .contains("Recovered quote ready")
      .should("be.visible");
    clickVisibleCardButton(payment.unique_id, "Resume payment");
    cy.wait("@quoteValidate");

    cy.then(() => {
      expect(getQuoteCalls).to.equal(0);
      expect(validateCalls).to.deep.equal([recoveredQuoteId, recoveredQuoteId]);
    });

    cy.contains("Confirm conversion quote").should("be.visible");
    cy.contains("NTX 88.00000000").should("be.visible");
    cy.get('[role="dialog"] button:visible').contains("Cancel").click();
    cy.wait("@quoteCancel");

    cy.then(() => {
      expect(cancelCalls).to.deep.equal([recoveredQuoteId]);
    });
  });
});
