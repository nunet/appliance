const TEST_PASSWORD = (Cypress.env("ADMIN_PASSWORD") as string) || "nunettest";
const DEFAULT_ORG_DID = "did:key:z6MksqN98v97yXtaGkuJWeK5yJ9EejZEi6xM19oZa8t4zL5a"; // NuTestNet (e2e)
const DEFAULT_ROLE = "compute_provider"; // TODO: adjust if NuTestNet role ids change
const DEFAULT_CAPABILITIES = [
  "/dms/deployment",
  "/dms/tokenomics/contract",
  "/broadcast",
  "/public",
];

function openOrganizationsPage() {
  cy.visit("/#/");
  cy.get('[data-slot="sidebar"]').contains("span", /^Organizations$/).click({ force: true });
  cy.location("hash", { timeout: 20000 }).should("match", /^#\/organizations\/?$/);
}

describe("Join organization with Mailhog confirmation", () => {
  const backendBaseUrl = (Cypress.env("BACKEND_BASE_URL") as string) || "http://localhost:8080";
  const orgDid = (Cypress.env("NUTEST_ORG_DID") as string) || DEFAULT_ORG_DID;
  const desiredRole = (Cypress.env("NUTEST_ROLE") as string) || DEFAULT_ROLE;
  const expectedCaps = (Cypress.env("NUTEST_CAPABILITIES") as string[] | undefined) || DEFAULT_CAPABILITIES;

  beforeEach(() => {
    cy.loginOrInitialize({ password: TEST_PASSWORD, backendBaseUrl });
    cy.ensureAppMode("simple");
  });

  it("validates join form fields and cancel flow", function () {
    cy.logStep("Opening organizations page for validation checks");
    cy.resetOnboarding(backendBaseUrl);
    openOrganizationsPage();

    const cardSelector = `[data-testid="org-card"][data-org-did="${orgDid}"]`;
    const joinSelector = `[data-testid="org-join-button"][data-org-did="${orgDid}"]`;
    const leaveSelector = `[data-testid="org-leave-button"][data-org-did="${orgDid}"]`;

    cy.get(cardSelector, { timeout: 120000 }).should("be.visible").scrollIntoView();

    cy.get("body").then(($body) => {
      if ($body.find(joinSelector).length === 0 && $body.find(leaveSelector).length > 0) {
        cy.logStep("Org already joined; leaving to validate join form");
        cy.get(leaveSelector).click({ force: true });
        cy.get('[data-testid="org-leave-confirm-button"]').click({ force: true });
        cy.get(joinSelector, { timeout: 120000 }).should("be.visible");
      }
    });

    cy.logStep("Opening join form");
    cy.get(joinSelector, { timeout: 120000 }).should("be.visible").click({ force: true });

    cy.logStep("Validating required fields");
    cy.get('[data-testid="join-submit-button"]').should("be.disabled");
    cy.get('[data-testid="join-name-input"]').type("NuNet Cypress Tester");
    cy.get('[data-testid="join-submit-button"]').should("be.disabled");

    cy.logStep("Validating email format");
    cy.get('[data-testid="join-field-email"]').type("invalid-email");
    cy.get('[data-testid="join-field-email"]').then(($el) => {
      const input = $el[0] as HTMLInputElement;
      expect(input.checkValidity(), "email validity").to.equal(false);
    });
    cy.get('[data-testid="join-submit-button"]').should("be.disabled");

    cy.logStep("Entering valid email and remaining required fields");
    cy.get('[data-testid="join-field-email"]').clear().type("tester@example.com");
    cy.get('[data-testid="join-field-location"]').type("Test City, Test Country");
    cy.get('[data-testid="join-submit-button"]').should("not.be.disabled");

    cy.logStep("Checking cancel join dialog");
    cy.get('[data-testid="join-cancel-button"]').click({ force: true });
    cy.contains("Cancel joining", { timeout: 10000 }).should("be.visible");
    cy.contains("button", "Keep Joining").click({ force: true });
    cy.get('[data-testid="join-submit-button"]').should("be.visible");

    cy.logStep("Cancelling onboarding");
    cy.get('[data-testid="join-cancel-button"]').click({ force: true });
    cy.contains("button", "Cancel Onboarding").click({ force: true });
    cy.get(cardSelector, { timeout: 120000 }).should("be.visible");
    cy.get(joinSelector, { timeout: 120000 }).should("be.visible");
  });

  it("submits a join request and follows the Mailhog verification link", function () {
    // Mailhog requires credentials in most environments; skip unless explicitly configured.
    if (!Cypress.env("MAILHOG_USERNAME")) {
      this.skip();
    }

    const mailbox = `join-${Date.now()}`;
    const inboxDomain = (Cypress.env("MAIL_INBOX_DOMAIN") as string) || "mailhog.nunet.network";
    const email = `${mailbox}@${inboxDomain}`;
    const fullName = "NuNet Cypress Tester";
    const subjectFragment = Cypress.env("MAIL_SUBJECT_FRAGMENT") as string | undefined;

    cy.logStep(`Using Mailhog mailbox: ${mailbox} (${email})`);
    cy.logStep(`Target org DID: ${orgDid}`);
    cy.logStep(`Target role: ${desiredRole}`);

    cy.resetOnboarding(backendBaseUrl);

    openOrganizationsPage();
    cy.logStep("Visiting organizations page");

    const cardSelector = `[data-testid="org-card"][data-org-did="${orgDid}"]`;
    const joinSelector = `[data-testid="org-join-button"][data-org-did="${orgDid}"]`;
    const leaveSelector = `[data-testid="org-leave-button"][data-org-did="${orgDid}"]`;
    const fetchSelector = `[data-testid="org-fetch-button"]`;

    cy.get("body", { timeout: 60000 }).then(($body) => {
      const cards = $body.find('[data-testid="org-card"]');
      cy.logStep(`Org cards rendered (testid): ${cards.length}`);
      const joins = $body.find('[data-testid="org-join-button"]');
      const dids = joins
        .toArray()
        .map((btn) => btn.getAttribute("data-org-did") || "unknown");
      cy.logStep(`Join buttons (testid) for org DIDs: ${dids.join(", ") || "none"}`);
    });

    cy.get("body", { timeout: 60000 }).then(($body) => {
      if ($body.find(cardSelector).length === 0) {
        cy.logStep("Org card missing; fetching known orgs");
        cy.get(fetchSelector).should("be.visible").click({ force: true });
      }
    });

    cy.get(cardSelector, { timeout: 120000 }).should("be.visible").scrollIntoView();

    cy.get("body").then(($body) => {
      const joinBtn = $body.find(joinSelector);
      const leaveBtn = $body.find(leaveSelector);

      if (joinBtn.length > 0) {
        const disabled = joinBtn.is(":disabled");
        cy.logStep(`Join button visible (disabled=${disabled}), submitting join request`);
        cy.get(joinSelector, { timeout: 20000 })
          .should("be.visible")
          .and("not.be.disabled")
          .click({ force: true });
        return;
      }

      if (leaveBtn.length > 0) {
        const disabled = leaveBtn.is(":disabled");
        cy.logStep(`Already joined (leave disabled=${disabled}); leaving then rejoining`);
        cy.get(leaveSelector, { timeout: 20000 }).should("be.visible").click({ force: true });
        cy.get('[data-testid="org-leave-confirm-button"]', { timeout: 60000 })
          .should("be.visible")
          .click({ force: true });
        cy.logStep("Waiting for join button after leave");
        cy.get(joinSelector, { timeout: 120000 })
          .should("be.visible")
          .and("not.be.disabled")
          .click({ force: true });
        return;
      }

      cy.logStep("Join/leave buttons not found; fetching known orgs");
      cy.get(fetchSelector).should("be.visible").click({ force: true });
      cy.get(joinSelector, { timeout: 120000 })
        .should("be.visible")
        .and("not.be.disabled")
        .click({ force: true });
    });

    cy.logStep("Filling join form");
    cy.get('[data-testid="join-name-input"]').should("be.visible").clear().type(fullName);
    cy.get('[data-testid="join-field-email"]').should("be.visible").clear().type(email);
    cy.get('[data-testid="join-field-location"]').should("be.visible").clear().type("Test City, Test Country");
    cy.get('[data-testid="join-field-discord"]').should("be.visible").clear().type("mailhog-user");

    cy.get(`[data-testid="join-role-${desiredRole}"]`).should("exist").click({ force: true });

    cy.logStep("Submitting join form");
    cy.get('[data-testid="join-submit-button"]').should("be.visible").click({ force: true });

    cy.waitForMail(mailbox, subjectFragment).then((message) => {
      const rawBody = message.body || "";
      const body = rawBody.replace(/=\r?\n/g, "").replace(/=3D/g, "=");
      const hrefMatches = [...body.matchAll(/href="([^"]+)"/gi)].map((m) => m[1]);
      const urlMatches = [...body.matchAll(/https?:\/\/[^\s"']+/gi)].map((m) => m[0]);
      const candidates = [...hrefMatches, ...urlMatches];
      cy.logStep(`Mailhog message received. Found ${candidates.length} URL candidates`);

      const filtered = candidates.filter((u) => {
        const lower = u.toLowerCase();
        if (lower.endsWith(".svg")) return false;
        if (lower.includes("logo")) return false;
        return lower.includes("nunet.io") || lower.includes("url");
      });

      const confirmationUrl = (filtered[0] || candidates[0] || "").trim();
      expect(confirmationUrl, "confirmation url string").to.contain("http");
      cy.logStep(`Using confirmation URL: ${confirmationUrl}`);

      const origin = new URL(confirmationUrl).origin;
      cy.origin(
        origin,
        { args: { confirmationUrl } },
        ({ confirmationUrl }) => {
          cy.log("Visiting confirmation URL");
          cy.visit(confirmationUrl);
        }
      );
    });

    openOrganizationsPage();
    cy.logStep("Back to organizations, waiting for status banner and restart prompt");

    cy.logStep("Waiting for status banner / restart prompt");
    cy.get('[data-testid="org-status-banner"]', { timeout: 120000 }).should("exist");

    cy.logStep("Waiting for Restart DMS button");
    cy.get('[data-testid="org-restart-dms-button"]', { timeout: 180000 }).should("be.visible").click({ force: true });
    cy.get('[data-testid="org-restart-confirm-button"]', { timeout: 60000 })
      .should("be.visible")
      .click({ force: true });

    cy.logStep("Waiting for restart to complete and joined state to appear");
    cy.get(cardSelector, { timeout: 180000 }).should("contain.text", "Joined");
    cy.get(cardSelector, { timeout: 60000 }).should("contain.text", "Capabilities");
    cy.get(`[data-testid="org-leave-button"][data-org-did="${orgDid}"]`, { timeout: 60000 }).should("be.visible");
    expectedCaps.forEach((cap) => {
      cy.get(cardSelector).contains(cap);
    });

    cy.logStep("Verifying dashboard status and Offboard button");
    cy.visit("/#/");
    cy.get('[data-testid="offboard-button"]', { timeout: 60000 }).should("be.visible");
  });
});
