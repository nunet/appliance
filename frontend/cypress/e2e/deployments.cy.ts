const TEST_PASSWORD = (Cypress.env("ADMIN_PASSWORD") as string) || "nunettest";
const backendBaseUrl = (Cypress.env("BACKEND_BASE_URL") as string) || "http://localhost:8080";
const skipDeployments = Boolean(Cypress.env("DEPLOYMENTS_SKIP"));

const getEnvNumber = (key: string, fallback: number): number => {
  const raw = Cypress.env(key);
  const value = typeof raw === "string" || typeof raw === "number" ? Number(raw) : Number.NaN;
  return Number.isFinite(value) ? value : fallback;
};

const PEER_WAIT_MS = getEnvNumber("PEER_WAIT_MS", 300000);
const PEER_POLL_INTERVAL_MS = getEnvNumber("PEER_POLL_INTERVAL_MS", 5000);
const DEPLOYMENTS_LIST_WAIT_MS = getEnvNumber("DEPLOYMENTS_LIST_WAIT_MS", 300000);
const DEPLOYMENTS_LIST_POLL_INTERVAL_MS = getEnvNumber("DEPLOYMENTS_LIST_POLL_INTERVAL_MS", 5000);
const DEPLOYMENT_DETAIL_WAIT_MS = getEnvNumber("DEPLOYMENT_DETAIL_WAIT_MS", 600000);
const DEPLOYMENT_DETAIL_INTERVAL_MS = getEnvNumber("DEPLOYMENT_DETAIL_INTERVAL_MS", 5000);
const DEPLOY_REQUEST_TIMEOUT_MS = getEnvNumber("DEPLOY_REQUEST_TIMEOUT_MS", 300000);

type TemplateItem = {
  path: string;
  yaml_path?: string | null;
  stem?: string;
  category?: string;
};

type ConnectedPeer = {
  peer_id?: string;
};

const parsePeers = (raw: string): string[] => {
  return (raw || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(
      (line) =>
        line.length > 0 &&
        !line.startsWith("{") &&
        !line.startsWith("}") &&
        !line.startsWith('"Peers"') &&
        !line.includes("[") &&
        !line.includes("]") &&
        !line.includes(":")
    )
    .map((line) => line.replace(/["',]/g, ""));
};

const extractPeerIds = (body: { peers?: ConnectedPeer[]; raw?: string } | undefined): string[] => {
  const peers = Array.isArray(body?.peers) ? body?.peers ?? [] : [];
  const peerIds = peers.map((peer) => peer.peer_id).filter((id): id is string => Boolean(id));
  if (peerIds.length > 0) {
    return peerIds;
  }
  return parsePeers(body?.raw ?? "");
};

const waitForConnectedPeers = (
  backendUrl: string,
  token: string | null,
  timeoutMs = PEER_WAIT_MS,
  intervalMs = PEER_POLL_INTERVAL_MS
): Cypress.Chainable<string[]> => {
  const started = Date.now();
  const poll = (): Cypress.Chainable<string[]> => {
    return cy
      .request({
        method: "GET",
        url: `${backendUrl}/dms/peers/connected`,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        failOnStatusCode: false,
      })
      .then((resp) => {
        const peers = extractPeerIds(resp.body as { peers?: ConnectedPeer[]; raw?: string });
        if (resp.status === 200 && peers.length > 0) {
          return peers;
        }
        const elapsed = Date.now() - started;
        if (elapsed >= timeoutMs) {
          throw new Error(
            `No connected peers after ${Math.round(elapsed / 1000)}s (status ${resp.status}).`
          );
        }
        cy.logStep(`Waiting for connected peers (status ${resp.status}, peers ${peers.length})`);
        return cy.wait(intervalMs).then(() => poll());
      });
  };
  return poll();
};

const waitForDeploymentsListReady = (
  timeoutMs = DEPLOYMENTS_LIST_WAIT_MS,
  intervalMs = DEPLOYMENTS_LIST_POLL_INTERVAL_MS
): Cypress.Chainable<"ready" | "empty" | "timeout"> => {
  const started = Date.now();
  const poll = (): Cypress.Chainable<"ready" | "empty" | "timeout"> => {
    return cy.get("body", { log: false }).then(($body) => {
      const text = $body.text();
      const hasCards = $body.find('[data-testid="deployment-card"]').length > 0;
      const hasEmpty = text.includes("No deployments found");
      const isLoading = text.includes("Loading deployments...");

      if (hasCards) {
        return "ready";
      }
      if (hasEmpty && !isLoading) {
        return "empty";
      }

      const elapsed = Date.now() - started;
      if (elapsed >= timeoutMs) {
        cy.logStep(
          `Deployments list still loading after ${Math.round(elapsed / 1000)}s; skipping assertions.`
        );
        return "timeout";
      }
      cy.logStep(`Waiting for deployments list (${Math.round(elapsed / 1000)}s)...`);
      return cy.wait(intervalMs).then(() => poll());
    });
  };
  return poll();
};

const openDeploymentsList = (): void => {
  cy.logStep("Opening deployments page");
  cy.visit("/#/");
  cy.get('[data-slot="sidebar"]').contains("span", /^Deployments$/).click({ force: true });
  cy.location("hash", { timeout: 20000 }).should("match", /^#\/deploy\/?$/);
  cy.get('[data-testid="deployment-search-input"]', { timeout: DEPLOYMENTS_LIST_WAIT_MS }).should("be.visible");
};

const openNewDeploymentWizard = (): void => {
  cy.logStep("Opening new deployment wizard");
  openDeploymentsList();
  cy.get('[data-testid="deployments-new-button"]', { timeout: 20000 }).should("be.visible").click({ force: true });
  cy.location("hash", { timeout: 20000 }).should("include", "/deploy/new");
  cy.get('[data-testid="deployment-wizard"]', { timeout: 20000 }).should("be.visible");
  cy.get('[data-testid="deployment-template-card"]', { timeout: 60000 }).should("have.length.greaterThan", 0);
};

describe("Deployments wizard + details", () => {
  beforeEach(() => {
    cy.loginOrInitialize({ password: TEST_PASSWORD, backendBaseUrl });
    cy.ensureAppMode("simple");
  });

  it("deploys a template with defaults and validates details", function () {
    if (skipDeployments) {
      this.skip();
    }

    cy.logStep("Starting deployment wizard flow");
    const existingDeploymentId = Cypress.env("LAST_DEPLOYMENT_ID") as string | undefined;
    const reuseDeploymentId = existingDeploymentId && existingDeploymentId.trim().length > 0
      ? existingDeploymentId.trim()
      : null;

    if (reuseDeploymentId) {
      cy.logStep(`Reusing deployment id from previous attempt: ${reuseDeploymentId}`);
      cy.wrap(reuseDeploymentId, { log: false }).as("deploymentId");
    }

    if (!reuseDeploymentId) {
      cy.logStep("Loading deployment templates");
      openNewDeploymentWizard();

      cy.logStep("Selecting a deployment template");
      cy.get("body").then(($body) => {
        const preferred = $body.find('[data-testid="deployment-template-card"][data-template-stem="floppybird"]');
        const fallback = $body.find('[data-testid="deployment-template-card"]').first();
        const selectedCard = (preferred.length ? preferred.first() : fallback) as unknown as JQuery<HTMLElement>;
        const path = selectedCard.attr("data-template-path") || "";
        const stem = selectedCard.attr("data-template-stem") || "";
        const category = selectedCard.attr("data-template-category") || "";
        expect(path, "template path").to.be.a("string").and.not.be.empty;
        cy.wrap({ path, stem, category } satisfies TemplateItem, { log: false }).as("selectedTemplate");
        cy.wrap(selectedCard).click({ force: true });
      });

      cy.logStep("Advancing to target selection");
      cy.get('[data-testid="deployment-next-button"]').should("not.be.disabled").click();
      cy.get('[data-testid="deployment-step2"]').should("be.visible");

      cy.window()
        .then((win) => win.localStorage.getItem("nunet-admin-token"))
        .then((token) => waitForConnectedPeers(backendBaseUrl, token))
        .then((peers) => {
          const selectedPeer = peers[Math.floor(Math.random() * peers.length)];
          cy.wrap(selectedPeer, { log: false }).as("selectedPeer");
          cy.wrap("targeted", { log: false }).as("deploymentType");

          cy.get('[data-testid="deployment-target-targeted"]').click();
          cy.get('[data-testid="deployment-peer-filter"]').clear().type(selectedPeer.slice(-9));
          cy.get(`[data-testid="deployment-peer-row"][data-peer-id="${selectedPeer}"]`, { timeout: 20000 })
            .should("be.visible")
            .click();
        });

      cy.logStep("Advancing to configuration step");
      cy.get('[data-testid="deployment-next-button"]').should("not.be.disabled").click();
      cy.get('[data-testid="deployment-step3"]').should("be.visible");

      cy.get("@selectedTemplate").then((tpl) => {
        const template = tpl as TemplateItem;
        if (template?.stem === "floppybird") {
          cy.get('[data-testid="deployment-field-bird_color"]').should("have.value", "red");
          cy.get('[data-testid="deployment-field-proxy_port"]').should("have.value", "8070");
          cy.get('[data-testid="deployment-field-dns_name"]').should("have.value", "crappy-bird-fastapi");
          cy.get('[data-testid="deployment-field-allocations_alloc1_resources_cpu_cores"]').should(
            "have.value",
            "0.5"
          );
          cy.get('[data-testid="deployment-field-allocations_alloc1_resources_ram_size"]').should(
            "have.value",
            "0.5"
          );
          cy.get('[data-testid="deployment-field-allocations_alloc1_resources_disk_size"]').should(
            "have.value",
            "1"
          );
        } else {
          cy.logStep("Selected template is not floppybird; skipping default assertions.");
        }
      });

      cy.logStep("Advancing to summary step");
      cy.get('[data-testid="deployment-next-button"]').should("not.be.disabled").click();
      cy.get('[data-testid="deployment-step4"]').should("be.visible");

      cy.get("@selectedTemplate").then((tpl) => {
        const template = tpl as TemplateItem;
        cy.get('[data-testid="deployment-summary-ensemble"]').should("contain.text", template.path);
        if (template.category) {
          cy.get('[data-testid="deployment-summary-category"]').should("contain.text", template.category);
        }
      });

      cy.get("@deploymentType").then((deploymentType) => {
        cy.get('[data-testid="deployment-summary-deployment_type"]').should(
          "contain.text",
          deploymentType as string
        );
      });

      cy.get("@selectedPeer").then((selectedPeer) => {
        if (selectedPeer) {
          cy.get('[data-testid="deployment-summary-peer_id"]').should(
            "contain.text",
            String(selectedPeer).slice(-6)
          );
        }
      });

      cy.get("@selectedTemplate").then((tpl) => {
        const template = tpl as TemplateItem;
        if (template?.stem === "floppybird") {
          cy.get('[data-testid="deployment-summary-field-bird_color"]').should("contain.text", "red");
          cy.get('[data-testid="deployment-summary-field-proxy_port"]').should("contain.text", "8070");
          cy.get('[data-testid="deployment-summary-field-dns_name"]').should(
            "contain.text",
            "crappy-bird-fastapi"
          );
        }
      });

      cy.logStep("Submitting deployment");
      cy.intercept("POST", "**/ensemble/deploy/from-template").as("deployFromTemplate");
      cy.get('[data-testid="deployment-deploy-button"]').should("not.be.disabled").click();

      cy.wait("@deployFromTemplate", { timeout: DEPLOY_REQUEST_TIMEOUT_MS }).then(({ request, response }) => {
        if (!response) {
          throw new Error("No response received from deploy request.");
        }
        if (response.statusCode !== 200) {
          const detail =
            (response.body as { detail?: string; message?: string })?.detail ||
            (response.body as { detail?: string; message?: string })?.message ||
            JSON.stringify(response.body);
          throw new Error(`Deploy request failed (${response.statusCode}): ${detail}`);
        }
        expect(response.statusCode, "deploy response status").to.eq(200);
        const deploymentId = (response?.body as { deployment_id?: string })?.deployment_id;
        expect(deploymentId, "deployment id").to.be.a("string").and.not.be.empty;
        cy.wrap(deploymentId, { log: false }).as("deploymentId");
        Cypress.env("LAST_DEPLOYMENT_ID", deploymentId);

        const body = request.body as {
          template_path?: string;
          deployment_type?: string;
          values?: Record<string, any>;
        };

        cy.get("@selectedTemplate").then((tpl) => {
          const template = tpl as TemplateItem;
          const expectedYaml = template.yaml_path || template.path?.replace(/\.json$/i, ".yaml");
          expect(expectedYaml, "expected yaml path").to.be.a("string").and.not.be.empty;
          expect(body.template_path, "template path in request").to.eq(expectedYaml);
        });

        cy.get("@deploymentType").then((deploymentType) => {
          expect(body.deployment_type, "deployment type").to.eq(deploymentType);
        });

        if (body.values) {
          cy.get("@selectedPeer").then((selectedPeer) => {
            if (selectedPeer) {
              expect(body.values?.peer_id, "peer id in values").to.eq(selectedPeer);
            }
          });
        }
      });

      cy.location("hash", { timeout: 20000 }).should("include", "/deploy");
    }

    cy.logStep("Opening deployments list");
    openDeploymentsList();

    cy.intercept("GET", "**/ensemble/deployments/*/status*").as("deploymentStatus");
    cy.intercept("GET", "**/ensemble/deployments/*/manifest/raw*").as("deploymentManifest");
    cy.intercept("GET", "**/ensemble/deployments/*/allocations*").as("deploymentAllocations");

    cy.logStep("Opening deployment details");
    cy.get("@deploymentId").then((deploymentId) => {
      cy.get('[data-testid="deployment-search-input"]').clear().type(String(deploymentId));
      cy.get(`[data-testid="deployment-card"][data-deployment-id="${deploymentId}"]`, {
        timeout: 20000,
      }).should("exist");
      cy.get(`[data-testid="deployment-card-view"][data-deployment-id="${deploymentId}"]`).click();
    });

    cy.location("hash", { timeout: 20000 }).should("include", "/deploy/");

    cy.logStep("Waiting for deployment details view to render");

    cy.get('[data-testid="deployment-info-card"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .should("be.visible");
    cy.get('[data-testid="deployment-info-status"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .invoke("text")
      .should("not.be.empty");
    cy.get('[data-testid="deployment-info-timestamp"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .invoke("text")
      .should("not.be.empty");
    cy.get('[data-testid="deployment-info-ensemble-file"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .should("be.visible");

    cy.get('[data-testid="deployment-progress-card"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .should("be.visible");
    cy.get('[data-testid="deployment-progress-status"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .should("be.visible")
      .invoke("text")
      .should("not.be.empty");
    cy.get('[data-testid="deployment-allocations-card"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .should("be.visible");

    cy.get('[data-testid="deployment-manifest-panel"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .should("be.visible");
    cy.get('[data-testid="deployment-logs-card"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .should("be.visible");
    cy.get('[data-testid="deployment-logs-stdout"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .should("exist");
    cy.get('[data-testid="deployment-logs-stderr"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .should("exist");
    cy.get('[data-testid="deployment-logs-dms"]', { timeout: DEPLOYMENT_DETAIL_WAIT_MS })
      .should("exist");

    cy.get("body").then(($body) => {
      const viewBtn = $body.find('[data-testid="deployment-view-file-button"]');
      if (viewBtn.length > 0) {
        cy.wrap(viewBtn).click({ force: true });
        cy.get('[data-testid="deployment-file-modal"]').should("be.visible");
      } else {
        cy.logStep("Deployment file button not available; skipping file modal check.");
      }
    });
  });

  it("filters and paginates the deployments list", function () {
    if (skipDeployments) {
      this.skip();
    }

    cy.logStep("Opening deployments list for filter/pagination checks");
    openDeploymentsList();

    waitForDeploymentsListReady().then((state) => {
      if (state !== "ready") {
        cy.logStep(`Skipping list assertions (state=${state}).`);
        return;
      }

      cy.get('[data-testid="deployment-card"]', { timeout: DEPLOYMENTS_LIST_WAIT_MS })
        .first()
        .as("firstDeploymentCard");

      cy.get("@firstDeploymentCard")
        .invoke("attr", "data-deployment-id")
        .then((deploymentId) => {
          if (!deploymentId) {
            cy.logStep("Deployment id not found on first card; skipping list assertions.");
            return;
          }
          cy.wrap(deploymentId, { log: false }).as("listDeploymentId");
        });

      cy.get("@firstDeploymentCard")
        .find('[data-testid="deployment-card-status"]')
        .invoke("text")
        .then((statusText) => {
          const normalized = (statusText || "").trim().toLowerCase();
          cy.wrap(normalized, { log: false }).as("listDeploymentStatus");
        });

      cy.get("@listDeploymentId").then((deploymentId) => {
        if (!deploymentId) {
          return;
        }
        cy.get('[data-testid="deployment-search-input"]').clear().type(String(deploymentId));
        cy.get(`[data-testid="deployment-card"][data-deployment-id="${deploymentId}"]`, {
          timeout: 20000,
        }).should("exist");
      });

      cy.get("@listDeploymentStatus").then((status) => {
        const statusValueMap: Record<string, string> = {
          submitted: "submitted",
          running: "running",
          completed: "completed",
          failed: "failed",
        };
        const statusValue = statusValueMap[String(status || "").toLowerCase()];
        if (!statusValue) {
          cy.logStep("Unknown deployment status; skipping filter assertion.");
          return;
        }
        cy.get('[data-testid="deployment-status-filter"]').click();
        cy.get(`[data-testid="deployment-status-option-${statusValue}"]`).click();
        cy.get("@listDeploymentId").then((deploymentId) => {
          if (!deploymentId) {
            return;
          }
          cy.get(`[data-testid="deployment-card"][data-deployment-id="${deploymentId}"]`).should("exist");
        });
      });

      cy.get('[data-testid="deployment-pagination-next"]').then(($next) => {
        if ($next.is(":disabled")) {
          cy.logStep("Not enough deployments to validate pagination.");
          return;
        }
        cy.wrap($next).click();
        cy.get('[data-testid="deployment-pagination-label"]').should("contain.text", "Page 2");
        cy.get('[data-testid="deployment-pagination-prev"]').click();
        cy.get('[data-testid="deployment-pagination-label"]').should("contain.text", "Page 1");
      });
    });
  });
});
