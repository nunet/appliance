const onboardedWithGpu =
  "Cores: 10.5, RAM: 13.0 GB, Disk: 40.78 GB, GPU Count: 1, GPU 0: NVIDIA GeForce RTX 3060 (9.0 GB VRAM)";

const setupDashboardInterceptors = () => {
  cy.intercept("GET", "**/auth/status", {
    statusCode: 200,
    body: { password_set: true, username: "admin" },
  }).as("authStatus");

  cy.intercept("GET", /\/dms\/status\/?(?:\?.*)?$/, {
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
  }).as("dmsStatus");

  cy.intercept("GET", /\/dms\/status\/full\/?(?:\?.*)?$/, {
    statusCode: 200,
    body: {
      onboarding_status: "ONBOARDED",
      free_resources: "Cores: 10.5, RAM: 13.0 GB, Disk: 40.78 GB",
      allocated_resources: "Cores: 0, RAM: 0.0 GB, Disk: 0.0 GB",
      onboarded_resources: onboardedWithGpu,
    },
  }).as("dmsStatusFull");

  cy.intercept("GET", /\/dms\/peers\/self\/?(?:\?.*)?$/, {
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
  }).as("dmsPeersSelf");

  cy.intercept("GET", "**/dms/peers/connected*", {
    statusCode: 200,
    body: { raw: "" },
  });

  cy.intercept("GET", "**/sys/local-ip*", { statusCode: 200, body: "127.0.0.1" });
  cy.intercept("GET", "**/sys/public-ip*", { statusCode: 200, body: "127.0.0.1" });
  cy.intercept("GET", "**/sys/appliance-version*", { statusCode: 200, body: "0.0.0-e2e" });
  cy.intercept("GET", "**/sys/ssh-status*", {
    statusCode: 200,
    body: { running: true, authorized_keys: 1 },
  });
  cy.intercept("GET", "**/sys/check-updates*", {
    statusCode: 200,
    headers: { "content-type": "text/plain" },
    body: JSON.stringify({ available: false, current: "0.0.0", latest: "0.0.0" }),
  });
  cy.intercept("GET", "**/dms/check-updates*", {
    statusCode: 200,
    headers: { "content-type": "text/plain" },
    body: JSON.stringify({ available: false, current: "0.0.0", latest: "0.0.0" }),
  });
  cy.intercept("GET", "**/sys/docker/containers*", {
    statusCode: 200,
    body: { count: 0, containers: [] },
  });
};

describe("Dashboard onboarded GPU resources", () => {
  it("shows a concise summary and expandable GPU details", () => {
    setupDashboardInterceptors();

    cy.visit("/#/", {
      onBeforeLoad(win) {
        win.localStorage.setItem("nunet-admin-token", "e2e-token");
        win.localStorage.setItem("nunet-admin-expiry", String(Date.now() + 60 * 60 * 1000));
        win.localStorage.setItem(
          "app-mode-storage",
          JSON.stringify({ state: { mode: "simple" }, version: 0 })
        );
      },
    });

    cy.wait("@authStatus");
    cy.wait("@dmsStatus");
    cy.wait("@dmsStatusFull");
    cy.wait("@dmsPeersSelf");

    cy.get('[data-testid="onboarded-resources-card"]', { timeout: 30000 }).within(() => {
      cy.contains("Onboarded Resources").should("be.visible");
      cy.contains("GPU: 1").should("be.visible");
      cy.get('[data-testid="onboarded-resources-toggle"]').click();
      cy.get('[data-testid="onboarded-resources-details"]').should("be.visible");
      cy.contains("GPU Count").should("be.visible");
      cy.contains("GPU 0").should("be.visible");
      cy.contains("NVIDIA GeForce RTX 3060 (9.0 GB VRAM)").should("be.visible");
    });
  });
});
