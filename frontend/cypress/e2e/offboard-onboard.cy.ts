describe("Dashboard offboard/onboard toggle", () => {
  const backendBaseUrl = (Cypress.env("BACKEND_BASE_URL") as string) || "http://localhost:8080";
  const TEST_PASSWORD = (Cypress.env("ADMIN_PASSWORD") as string) || "nunettest";
  const OFFBOARD_WAIT_MS = Number(Cypress.env("OFFBOARD_WAIT_MS") ?? 180000);
  const OFFBOARD_WAIT_INTERVAL_MS = Number(Cypress.env("OFFBOARD_WAIT_INTERVAL_MS") ?? 5000);

  const waitForOffboardButton = (
    timeoutMs = OFFBOARD_WAIT_MS,
    intervalMs = OFFBOARD_WAIT_INTERVAL_MS
  ): Cypress.Chainable<JQuery<HTMLElement> | null> => {
    const started = Date.now();
    const poll = (): Cypress.Chainable<JQuery<HTMLElement> | null> => {
      return cy.get("body", { log: false }).then(($body) => {
        const button = $body.find('[data-testid="offboard-button"]');
        if (button.length > 0) {
          cy.logStep("Offboard button is visible");
          return cy.wrap(button.first());
        }
        const elapsed = Date.now() - started;
        if (elapsed >= timeoutMs) {
          cy.logStep(`Offboard button not found after ${Math.round(elapsed / 1000)}s`);
          return null;
        }
        cy.logStep(`Waiting for offboard button (${Math.round(elapsed / 1000)}s)...`);
        return cy.wait(intervalMs).then(() => poll());
      });
    };
    return poll();
  };

  beforeEach(() => {
    cy.loginOrInitialize({ password: TEST_PASSWORD, backendBaseUrl });
    cy.ensureAppMode("simple");
  });

  it("offboards and re-onboards when already joined", function () {
    cy.logStep("Opening dashboard");
    cy.visit("/#/");
    cy.logStep("Waiting for offboard button on dashboard");
    waitForOffboardButton().then((offboardBtn) => {
      if (!offboardBtn) {
        cy.logStep("Not joined; skipping offboard/onboard toggle");
        this.skip();
        return;
      }

      cy.logStep("Clicking offboard button");
      cy.wrap(offboardBtn).click();
      cy.logStep("Confirming offboard");
      cy.get('[data-testid="offboard-confirm-button"]', { timeout: 60000 }).click();
      cy.logStep("Waiting for onboard button");
      cy.get('[data-testid="onboard-button"]', { timeout: 240000 }).should("be.visible");

      cy.logStep("Clicking onboard button");
      cy.get('[data-testid="onboard-button"]').click();
      cy.logStep("Waiting for offboard button to return");
      cy.get('[data-testid="offboard-button"]', { timeout: 240000 }).should("be.visible");
    });
  });
});
