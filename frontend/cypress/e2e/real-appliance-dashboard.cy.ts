/**
 * Integration: real HTTP to the appliance (no cy.intercept for auth or dashboard).
 * Requires a live service and CYPRESS_ADMIN_PASSWORD (see .env.e2e.example).
 * Same-origin: CYPRESS_BASE_URL === CYPRESS_BACKEND_BASE_URL (e.g. https://host:8443).
 *
 * Core dashboard path: each step (login shell, hash → dashboard, Peer ID label) uses 10s — if slower, treat as a product issue.
 *
 * Optional waits (Cypress `--env` or `cypress.config` `env`): `ONBOARD_WAIT_MS` (default 30000),
 * `RESOURCE_CARDS_WAIT_MS` (default 30000) for the "onboards if needed" spec.
 * DMS may reject onboard when the host is busy (Cypress/Electron/rebuild). Use `SKIP_ONBOARD_E2E=1`
 * to skip that test, or `ONBOARD_COOLDOWN_MS` (ms wait before clicking Onboard) to reduce flakes.
 *
 * Timings: each `[timing] …` line is logged to the Cypress command log and to stdout via `cy.task("log")`.
 * Run `pnpm exec cypress run …` and scroll the terminal output, or open the HTML report if you add a reporter.
 */
describe("Real appliance: login and dashboard status", () => {
  /** Per-step ceiling for login route, post-auth hash, Peer ID, and optional dashboard/cards (responsive UI). */
  const UI_STEP_TIMEOUT_MS = 10000;
  /** Login → last milestone: 3×10s core + optional main-status + up to 3 resource cards at 10s each. */
  const TOTAL_FLOW_MAX_MS = 80000;

  const password = String(Cypress.env("ADMIN_PASSWORD") ?? "").trim();
  /** After clicking Onboard, wait for Offboard button / onboarded UI (raise via ONBOARD_WAIT_MS on slow nodes). */
  const onboardWaitMs = Number(Cypress.env("ONBOARD_WAIT_MS") ?? 30000);
  /** Resource grid after `free_resources` updates (raise via RESOURCE_CARDS_WAIT_MS if needed). */
  const resourceCardsWaitMs = Number(Cypress.env("RESOURCE_CARDS_WAIT_MS") ?? 30000);

  /** Wall-clock ms from `t0` — logs to CLI + Cypress UI. */
  const logTiming = (label: string, t0: number) => {
    const ms = Date.now() - t0;
    const line = `[timing] ${label}: ${ms}ms (from flow start)`;
    cy.log(line);
    cy.task("log", line);
  };

  beforeEach(() => {
    cy.clearAllLocalStorage();
    cy.clearAllSessionStorage();
  });

  it("shows the login page", () => {
    cy.visit("/#/login");
    cy.contains("Welcome back").should("be.visible");
    cy.contains("Enter the admin password").should("be.visible");
    cy.get('[data-testid="login-form"]').should("be.visible");
  });

  it("logs in through the UI and loads the dashboard status board", function () {
    if (!password) {
      cy.log("Skipping: set CYPRESS_ADMIN_PASSWORD or add it to frontend/.env.e2e");
      this.skip();
    }

    const t0 = Date.now();

    cy.visit("/#/login");
    cy.contains("Welcome back", { timeout: UI_STEP_TIMEOUT_MS }).should("be.visible");
    cy.then(() => logTiming("login_route_ready", t0));

    cy.get('[data-testid="login-password-input"]').should("be.visible").type(password, { log: false });
    cy.get('[data-testid="login-submit-button"]').should("be.enabled").click();
    cy.then(() => logTiming("after_sign_in_click", t0));

    cy.location("hash", { timeout: UI_STEP_TIMEOUT_MS }).should("match", /^#\/$/);
    cy.then(() => logTiming("hash_is_dashboard", t0));

    // Main status card: DMS peer + system info (SectionCards top card).
    cy.contains("Peer ID:", { timeout: UI_STEP_TIMEOUT_MS }).should("be.visible");
    cy.then(() => logTiming("peer_id_label_visible", t0));

    // `data-testid="dashboard-main-status"` exists only in bundles built after that attribute was added.
    // If the live service serves an older `frontend/dist`, this optional block skips (dashboard still valid).
    cy.then(() => {
      if (Cypress.$('[data-testid="dashboard-main-status"]').length > 0) {
        cy.get('[data-testid="dashboard-main-status"]', { timeout: UI_STEP_TIMEOUT_MS }).should(
          "be.visible"
        );
        cy.then(() => logTiming("dashboard_main_status_card", t0));
      } else {
        const line =
          "[timing] dashboard_main_status_card: skipped (no data-testid in served bundle — run: ./deploy/scripts/nunet-web-mode.sh rebuild)";
        cy.log(line);
        cy.task("log", line);
      }
    });

    // Resource overview cards are hidden when DMS `free_resources` text includes "not" (see section-cards.tsx).
    const optionalResourceCard = (testId: string, timingLabel: string) => {
      cy.then(() => {
        if (Cypress.$(`[data-testid="${testId}"]`).length > 0) {
          cy.get(`[data-testid="${testId}"]`, { timeout: UI_STEP_TIMEOUT_MS }).should("be.visible");
          cy.then(() => logTiming(timingLabel, t0));
        } else {
          const line = `[timing] ${timingLabel}: skipped (not shown for this node)`;
          cy.log(line);
          cy.task("log", line);
        }
      });
    };
    optionalResourceCard("free-resources-card", "free_resources_card");
    optionalResourceCard("allocated-resources-card", "allocated_resources_card");
    optionalResourceCard("onboarded-resources-card", "onboarded_resources_card");

    cy.then(() => {
      const totalMs = Date.now() - t0;
      const line = `[timing] total_flow: ${totalMs}ms (login page → last milestone)`;
      // eslint-disable-next-line no-console
      console.log(`[e2e] ${line}`);
      cy.log(line);
      cy.task("log", line);
      expect(
        totalMs,
        `dashboard flow should finish within ${TOTAL_FLOW_MAX_MS}ms (responsive UI target)`
      ).to.be.lessThan(TOTAL_FLOW_MAX_MS);
    });
  });

  /**
   * If the node shows Onboard (not yet onboarded): click Onboard → success or DMS error toast →
   * assert refetched status / Offboard / resource cards. Skips when already onboarded.
   * DMS can return success: false (e.g. high CPU) while nunet exits 0 — the UI shows an error toast.
   */
  it("onboards if needed and shows resource overview cards", function () {
    if (!password) {
      cy.log("Skipping: set CYPRESS_ADMIN_PASSWORD or add it to frontend/.env.e2e");
      this.skip();
    }
    if (["1", "true", "yes"].includes(String(Cypress.env("SKIP_ONBOARD_E2E") ?? "").toLowerCase())) {
      cy.log("Skipping onboard spec — SKIP_ONBOARD_E2E (e.g. avoid flake when CPU busy during e2e rebuild)");
      this.skip();
    }

    const onboardCooldownMs = Number(Cypress.env("ONBOARD_COOLDOWN_MS") ?? 0);

    cy.visit("/#/login");
    cy.contains("Welcome back", { timeout: UI_STEP_TIMEOUT_MS }).should("be.visible");
    cy.get('[data-testid="login-password-input"]').should("be.visible").type(password, { log: false });
    cy.get('[data-testid="login-submit-button"]').should("be.enabled").click();

    cy.location("hash", { timeout: UI_STEP_TIMEOUT_MS }).should("match", /^#\/$/);
    cy.contains("Peer ID:", { timeout: UI_STEP_TIMEOUT_MS }).should("be.visible");

    cy.get("body").then(($body) => {
      const needsOnboard = $body.find('[data-testid="onboard-button"]').length > 0;
      if (needsOnboard) {
        if (onboardCooldownMs > 0) {
          cy.log(`Waiting ${onboardCooldownMs}ms before Onboard (ONBOARD_COOLDOWN_MS)`);
          cy.wait(onboardCooldownMs);
        }
        cy.logStep("Appliance not onboarded; clicking Onboard");
        cy.get('[data-testid="onboard-button"]').should("be.visible").click();
        // Success toast OR error toast (DMS may reject when CPU/RAM busy — e.g. during rebuild + Cypress).
        cy.logStep("Expect onboard success or DMS error toast");
        cy.get(
          '[data-testid="dashboard-onboard-compute-success"], [data-testid="dashboard-onboard-compute-error"]',
          { timeout: onboardWaitMs }
        ).should("be.visible");
        cy.then(() => {
          const hasErr = Cypress.$('[data-testid="dashboard-onboard-compute-error"]').length > 0;
          if (hasErr) {
            const msg = Cypress.$('[data-testid="dashboard-onboard-compute-error"]').text().trim();
            cy.task("log", `[e2e] DMS onboard error toast: ${msg}`);
          }
          expect(
            hasErr,
            "DMS rejected onboard (often high CPU/load during e2e). Set SKIP_ONBOARD_E2E=1, increase ONBOARD_COOLDOWN_MS, or run when idle."
          ).to.be.false;
        });
        cy.logStep("Expect dashboard to reflect refetched onboarding status (not cached NOT ONBOARDED)");
        cy.get('[data-testid="dashboard-onboarding-status"]', { timeout: onboardWaitMs })
          .should("be.visible")
          .should(($el) => {
            const t = $el.text().toUpperCase();
            expect(t, "onboarding status should include ONBOARDED").to.include("ONBOARDED");
            expect(t, "onboarding status should not stay NOT ONBOARDED").to.not.include("NOT ONBOARD");
          });
        cy.logStep("Expect Offboard control (onboarded UI)");
        cy.get('[data-testid="offboard-button"]', { timeout: onboardWaitMs }).should("be.visible");
      } else {
        cy.logStep("Onboard button absent; assuming already onboarded");
      }
    });

    cy.logStep("Waiting for resource overview cards (DMS free_resources must not contain 'not')");
    cy.get('[data-testid="free-resources-card"]', { timeout: resourceCardsWaitMs }).should("be.visible");
    cy.get('[data-testid="allocated-resources-card"]').should("be.visible");
    cy.get('[data-testid="onboarded-resources-card"]').should("be.visible");
  });
});
