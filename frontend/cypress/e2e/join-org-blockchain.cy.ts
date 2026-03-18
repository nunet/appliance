const TEST_PASSWORD = (Cypress.env("ADMIN_PASSWORD") as string) || "nunettest";

const ORG_DID = "did:key:z6MkrG7E2e2eMultiChainOrgFixture1234567890";
const ETH_ADDRESS = "0x1111222233334444555566667777888899990000";

const STEP_STATES = [
  { id: "init", label: "Init", virtual: false, state: "done" as const },
  { id: "select_org", label: "Select Organization", virtual: false, state: "active" as const },
  { id: "collect_join_data", label: "Fill Join Form", virtual: false, state: "todo" as const },
  { id: "submit_data", label: "Submit Data", virtual: false, state: "todo" as const },
  { id: "join_data_sent", label: "Data Sent", virtual: false, state: "todo" as const },
  { id: "pending_authorization", label: "Pending Authorization", virtual: false, state: "todo" as const },
  { id: "complete", label: "Complete", virtual: false, state: "todo" as const },
  { id: "rejected", label: "Rejected", virtual: false, state: "todo" as const },
];

const ORG_FIXTURE = {
  name: "Cypress Multi-Blockchain Org",
  roles: ["compute_provider", "orchestrator"],
  join_fields: [
    { name: "email", label: "Email", type: "email", required: true },
    { name: "location", label: "Location", type: "text", required: true },
  ],
  tokenomics: {
    enabled: true,
    blockchains: ["ethereum", "cardano"],
  },
  blockchains: ["ethereum", "cardano"],
};

function installEthereumStub() {
  let isConnected = false;

  cy.on("window:before:load", (win) => {
    type WithEthereum = Window & {
      ethereum?: {
        request: ({ method }: { method: string }) => Promise<unknown>;
        on: () => void;
        removeListener: () => void;
      };
    };

    const ethereum = {
      request: ({ method }: { method: string }) => {
        if (method === "eth_accounts") {
          return Promise.resolve(isConnected ? [ETH_ADDRESS] : []);
        }
        if (method === "eth_requestAccounts") {
          isConnected = true;
          return Promise.resolve([ETH_ADDRESS]);
        }
        if (method === "eth_chainId") {
          return Promise.resolve("0x1");
        }
        return Promise.resolve(null);
      },
      on: () => {},
      removeListener: () => {},
    };

    (win as WithEthereum).ethereum = ethereum;
  });
}

function setupMockedOrganizationApi() {
  let selectedOrgDid: string | null = null;

  cy.intercept("GET", "**/organizations/known", {
    [ORG_DID]: ORG_FIXTURE,
  }).as("knownOrgs");

  cy.intercept("GET", "**/organizations/joined", []).as("joinedOrgs");

  cy.intercept("POST", "**/organizations/select", (req) => {
    selectedOrgDid = req.body?.org_did ?? null;
    req.reply({
      status: "ok",
      selected_org: selectedOrgDid,
    });
  }).as("selectOrg");

  cy.intercept("GET", "**/organizations/status", (req) => {
    if (!selectedOrgDid) {
      req.reply({
        current_step: "select_org",
        current_index: 1,
        progress: 10,
        api_status: null,
        ui_state: "selecting",
        ui_message: "Select an organization to continue.",
        step_states: STEP_STATES,
        raw: {},
      });
      return;
    }

    req.reply({
      current_step: "collect_join_data",
      current_index: 2,
      progress: 30,
      api_status: "collecting",
      ui_state: "collecting",
      ui_message: "Fill the onboarding details.",
      step_states: [
        { ...STEP_STATES[0], state: "done" as const },
        { ...STEP_STATES[1], state: "done" as const },
        { ...STEP_STATES[2], state: "active" as const },
        ...STEP_STATES.slice(3),
      ],
      raw: {
        org_data: {
          did: selectedOrgDid,
          name: ORG_FIXTURE.name,
        },
      },
    });
  }).as("orgStatus");

  cy.intercept("POST", "**/organizations/join/submit", {
    status: "ok",
    api_status: "email_sent",
  }).as("joinSubmit");
}

function openJoinForm() {
  cy.visit("/#/organizations");
  cy.wait("@knownOrgs");
  cy.wait("@joinedOrgs");
  cy.wait("@orgStatus");
  cy.get(`[data-testid="org-join-button"][data-org-did="${ORG_DID}"]`, {
    timeout: 30000,
  })
    .should("be.visible")
    .click({ force: true });
  cy.wait("@selectOrg");
  cy.wait("@orgStatus");
  cy.get('[data-testid="join-name-input"]', { timeout: 30000 }).should("be.visible");
}

describe("Organization join blockchain selection", () => {
  const backendBaseUrl = (Cypress.env("BACKEND_BASE_URL") as string) || "http://localhost:8080";

  beforeEach(() => {
    installEthereumStub();
    setupMockedOrganizationApi();
    cy.loginOrInitialize({ password: TEST_PASSWORD, backendBaseUrl });
    cy.ensureAppMode("simple");
  });

  it("requires blockchain selection and updates wallet connector by selected chain", () => {
    openJoinForm();

    cy.get('[data-testid="join-blockchain-group"]').should("be.visible");
    cy.get('[data-testid="join-blockchain-ethereum"]').should("exist").and("not.be.checked");
    cy.get('[data-testid="join-blockchain-cardano"]').should("exist").and("not.be.checked");
    cy.contains("Select a blockchain to enable wallet connection.").should("be.visible");

    cy.get('[data-testid="join-blockchain-cardano"]').click({ force: true });
    cy.contains("Cardano (Eternl)").should("be.visible");
    cy.contains("button", "Connect Cardano wallet").should("be.visible");

    cy.get('[data-testid="join-blockchain-ethereum"]').click({ force: true });
    cy.contains("Ethereum (MetaMask)").should("be.visible");
    cy.contains("button", "Connect Ethereum wallet").should("be.visible");

    cy.get('[data-testid="join-name-input"]').clear().type("Cypress Tester");
    cy.get('[data-testid="join-field-email"]').clear().type("cypress@example.com");
    cy.get('[data-testid="join-field-location"]').clear().type("Test City");
    cy.get('[data-testid="join-submit-button"]').should("be.disabled");
  });

  it("submits selected blockchain and wallet metadata", () => {
    openJoinForm();

    cy.get('[data-testid="join-blockchain-ethereum"]').click({ force: true });
    cy.get('[data-testid="join-name-input"]').clear().type("Cypress Tester");
    cy.get('[data-testid="join-field-email"]').clear().type("cypress@example.com");
    cy.get('[data-testid="join-field-location"]').clear().type("Test City");

    cy.contains("button", "Connect Ethereum wallet").click({ force: true });
    cy.contains("Select a wallet").should("be.visible");
    cy.contains("p", "MetaMask").should("be.visible");
    cy.get('[role="menu"]').contains("button", "Connect").click({ force: true });
    cy.contains("button", "MetaMask:").should("be.visible");

    cy.get('[data-testid="join-submit-button"]').should("not.be.disabled").click({ force: true });

    cy.wait("@joinSubmit").then(({ request }) => {
      const payload = request.body as Record<string, unknown>;
      expect(payload.blockchain).to.equal("ethereum");
      expect(payload.wallet_chain).to.equal("ethereum");
      expect(payload.wallet_address).to.equal(ETH_ADDRESS);
      expect(payload.roles).to.deep.equal(["compute_provider"]);
      expect(payload.why_join).to.equal("compute_provider");
    });
  });
});

export {};
