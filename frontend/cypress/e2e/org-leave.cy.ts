const TEST_PASSWORD = (Cypress.env("ADMIN_PASSWORD") as string) || "nunettest";
const backendBaseUrl = (Cypress.env("BACKEND_BASE_URL") as string) || "http://localhost:8080";
const DEFAULT_ORG_DID = "did:key:z6MksqN98v97yXtaGkuJWeK5yJ9EejZEi6xM19oZa8t4zL5a"; // NuTestNet (e2e)

function openOrganizationsPage() {
  cy.visit("/#/");
  cy.get('[data-slot="sidebar"]').contains("span", /^Organizations$/).click({ force: true });
  cy.location("hash", { timeout: 20000 }).should("match", /^#\/organizations\/?$/);
}

describe("Organization leave flow (final cleanup)", () => {
  const orgDid = (Cypress.env("NUTEST_ORG_DID") as string) || DEFAULT_ORG_DID;

  beforeEach(() => {
    cy.loginOrInitialize({ password: TEST_PASSWORD, backendBaseUrl });
    cy.ensureAppMode("simple");
  });

  it("prompts before leaving and can cancel", function () {
    cy.logStep("Opening organizations page for leave cancel check");
    openOrganizationsPage();

    const cardSelector = `[data-testid="org-card"][data-org-did="${orgDid}"]`;
    const leaveSelector = `[data-testid="org-leave-button"][data-org-did="${orgDid}"]`;
    const fetchSelector = `[data-testid="org-fetch-button"]`;

    cy.get("body", { timeout: 60000 }).then(($body) => {
      if ($body.find(cardSelector).length === 0) {
        cy.logStep("Org card missing; fetching known orgs");
        cy.get(fetchSelector).should("be.visible").click({ force: true });
      }
    });

    cy.get(cardSelector, { timeout: 120000 }).should("be.visible").scrollIntoView();
    cy.get("body").then(($body) => {
      if ($body.find(leaveSelector).length === 0) {
        cy.logStep("Leave button not present; skipping leave cancel check");
        this.skip();
        return;
      }
      cy.logStep("Opening leave dialog");
      cy.get(leaveSelector).click({ force: true });
      cy.contains("Leave organization?", { timeout: 10000 }).should("be.visible");
      cy.contains("button", "Cancel").click({ force: true });
      cy.get(leaveSelector).should("be.visible");
      cy.get(cardSelector).should("contain.text", "Joined");
    });
  });

  it("leaves organization at the end of the run", function () {
    cy.logStep("Opening organizations page for final leave");
    openOrganizationsPage();

    const cardSelector = `[data-testid="org-card"][data-org-did="${orgDid}"]`;
    const leaveSelector = `[data-testid="org-leave-button"][data-org-did="${orgDid}"]`;
    const joinSelector = `[data-testid="org-join-button"][data-org-did="${orgDid}"]`;
    const fetchSelector = `[data-testid="org-fetch-button"]`;

    cy.get("body", { timeout: 60000 }).then(($body) => {
      if ($body.find(cardSelector).length === 0) {
        cy.logStep("Org card missing; fetching known orgs");
        cy.get(fetchSelector).should("be.visible").click({ force: true });
      }
    });

    cy.get(cardSelector, { timeout: 120000 }).should("be.visible").scrollIntoView();
    cy.get("body").then(($body) => {
      if ($body.find(leaveSelector).length === 0) {
        cy.logStep("Leave button not present; skipping final leave");
        this.skip();
        return;
      }
    });

    cy.logStep("Confirming leave");
    cy.get(leaveSelector).click({ force: true });
    cy.get('[data-testid="org-leave-confirm-button"]').click({ force: true });

    cy.logStep("Waiting for join button to return");
    cy.get(joinSelector, { timeout: 180000 }).should("be.visible");
    cy.get(cardSelector).should("not.contain.text", "Joined");
  });
});
