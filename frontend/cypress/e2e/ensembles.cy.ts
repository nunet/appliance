const TEST_PASSWORD = (Cypress.env("ADMIN_PASSWORD") as string) || "nunettest";
const backendBaseUrl = (Cypress.env("BACKEND_BASE_URL") as string) || "http://localhost:8080";
const skipDestructive = Boolean(Cypress.env("ENSEMBLE_SKIP_DESTRUCTIVE"));

const buildYaml = (stem: string) => `version: "V1"

allocations:
  alloc1:
    executor: docker
    type: task
    resources:
      cpu:
        cores: "{{ allocations_alloc1_resources_cpu_cores }}"
      gpus: []
      ram:
        size: "{{ allocations_alloc1_resources_ram_size }}"
      disk:
        size: "{{ allocations_alloc1_resources_disk_size }}"
    execution:
      type: docker
      image: hello-world
nodes:
  node1:
    allocations:
      - alloc1
metadata:
  name: ${stem}
`;

const buildManualJson = (stem: string) =>
  JSON.stringify(
    {
      name: `${stem} JSON sidecar`,
      description: "Manual JSON provided by Cypress",
      fields: {
        allocations_alloc1_resources_cpu_cores: {
          label: "CPU cores",
          type: "number",
          required: true,
          min: 1,
          default: 1,
        },
        allocations_alloc1_resources_ram_size: {
          label: "RAM size",
          type: "number",
          required: true,
          min: 1,
          default: 1,
        },
        allocations_alloc1_resources_disk_size: {
          label: "Disk size",
          type: "number",
          required: true,
          min: 1,
          default: 10,
        },
      },
    },
    null,
    2
  );

function visitEnsembles() {
  cy.loginOrInitialize({ password: TEST_PASSWORD, backendBaseUrl });
  cy.ensureAppMode("simple");
  cy.logStep("Opening Ensembles page");
  cy.visit("/#/ensembles");
  cy.logStep("Waiting for ensembles list");
  cy.get('[data-testid="ensembles-card"]', { timeout: 20000 }).should("exist");
}

function openCreateDialog() {
  cy.logStep("Opening create ensemble dialog");
  cy.get('[data-testid="ensemble-add-button"]').first().click({ force: true });
  cy.get('[data-testid="ensemble-upload-dialog"]', { timeout: 10000 }).should("be.visible");
}

function uploadYaml(stem: string, yamlContent: string) {
  cy.logStep(`Uploading ensemble YAML for ${stem}`);
  cy.get('[data-testid="ensemble-yaml-input"]', { timeout: 10000 }).selectFile(
    {
      contents: Cypress.Buffer.from(yamlContent),
      fileName: `${stem}.yaml`,
      mimeType: "text/yaml",
    },
    { force: true }
  );
  cy.get('[data-testid="ensemble-yaml-status"]').should("contain", stem);
}

function saveTemplate() {
  cy.logStep("Saving ensemble");
  cy.get('[data-testid="ensemble-dialog-save"]', { timeout: 30000 }).click({ force: true });
  cy.get('[data-testid="ensemble-upload-dialog"]', { timeout: 30000 }).should("not.exist");
}

function appendEditorLine(editorSelector: string, line: string) {
  cy.get(editorSelector, { timeout: 10000 })
    .should("exist")
    .scrollIntoView()
    .click({ force: true })
    .type("{ctrl+end}{enter}" + line, { delay: 0, force: true });
}

function resolveRetrySafeStem(prefix: string, envKey: string) {
  const storageKey = `ensemble:${envKey}`;
  return cy
    .task("getRunValue", { key: storageKey }, { log: false })
    .then((existing) => {
      const existingValue = (existing as string | null) ?? null;
      if (existingValue) {
        Cypress.env(envKey, existingValue);
        return existingValue;
      }
      const next = `${prefix}-${Date.now()}`;
      Cypress.env(envKey, next);
      return cy.task("setRunValue", { key: storageKey, value: next }, { log: false }).then(() => next);
    });
}

describe("Ensembles CRUD + JSON flows", () => {
  beforeEach(() => {
    visitEnsembles();
  });

  it("shows default ensembles on load", () => {
    cy.logStep("Validating default ensembles list");
    cy.get('[data-testid="ensemble-list"]', { timeout: 30000 }).should("exist");
    cy.get('[data-testid="ensemble-row"]').should("have.length.greaterThan", 0);

    const expectedDefaults = (Cypress.env("ENSEMBLE_DEFAULT_STEMS") as string[] | undefined) || [];
    expectedDefaults.forEach((stem) => {
      cy.logStep(`Checking default ensemble: ${stem}`);
      cy.get(`[data-testid="ensemble-row"][data-ensemble-stem="${stem}"]`).should("exist");
    });
  });

  it("creates and deletes an ensemble with the default JSON form", function () {
    if (skipDestructive) {
      this.skip();
    }

    return resolveRetrySafeStem("cypress-ensemble", "ENSEMBLE_EDIT_STEM").then((stem) => {
      const rowSelector = `[data-testid="ensemble-row"][data-ensemble-stem="${stem}"]`;
      const storageKey = "ensemble:ENSEMBLE_EDIT_STEM";
      cy.logStep(`Using ensemble ${stem}`);

      cy.logStep("Checking for existing ensemble via API");
      cy.listEnsembleTemplates(backendBaseUrl).then((body) => {
        const items = body?.items ?? [];
        const expectedSuffixes = [`${stem}.yaml`, `${stem}.yml`];
        const exists = items.some((item: any) => {
          const path = item?.yaml_path || item?.path || "";
          return (
            item?.stem === stem ||
            expectedSuffixes.some((suffix) => path.endsWith(suffix))
          );
        });
        if (exists) {
          cy.logStep("Ensemble already exists via API; skipping creation");
          return;
        }

        cy.logStep("Creating ensemble");
        cy.cleanupEnsembleByStem(stem, { backendBaseUrl });
        openCreateDialog();
        uploadYaml(stem, buildYaml(stem));
        cy.logStep("Advancing to JSON step");
        cy.get('[data-testid="ensemble-dialog-next"]').click();
        saveTemplate();
      });

      cy.logStep("Verifying ensemble appears in list");
      cy.get(rowSelector, { timeout: 60000 }).should("exist");
      cy.listEnsembleTemplates(backendBaseUrl).then((body) => {
        const names = (body.items || []).map((tpl: any) =>
          (tpl.name || tpl.path || "").replace(/\.(ya?ml|json)$/i, "")
        );
        expect(names, "template present in API").to.include(stem);
      });

      cy.logStep("Editing ensemble YAML and saving changes");
      cy.get(`[data-testid="ensemble-row"][data-ensemble-stem="${stem}"] [data-testid="ensemble-edit-button"]`).click({
        force: true,
      });
      cy.get('[data-testid="ensemble-edit-dialog"]', { timeout: 20000 }).should("be.visible");
      cy.get('[data-testid="ensemble-edit-yaml-editor"] .cm-content', { timeout: 10000 }).should("not.be.empty");
      appendEditorLine('[data-testid="ensemble-edit-yaml-editor"] .cm-content', "# edited by cypress");
      cy.get('[data-testid="ensemble-dialog-next"]').should("not.be.disabled").click();
      cy.get('[data-testid="ensemble-edit-json-editor"]', { timeout: 10000 }).should("be.visible");
      cy.logStep("Saving edited ensemble");
      cy.get('[data-testid="ensemble-dialog-save"]', { timeout: 10000 }).should("not.be.disabled").click();
      cy.get('[data-testid="ensemble-edit-dialog"]', { timeout: 20000 }).should("not.exist");

      cy.logStep("Re-opening edit dialog to confirm YAML updates");
      cy.get(`[data-testid="ensemble-row"][data-ensemble-stem="${stem}"] [data-testid="ensemble-edit-button"]`).click({
        force: true,
      });
      cy.get('[data-testid="ensemble-edit-dialog"]', { timeout: 20000 }).should("be.visible");
      cy.get('[data-testid="ensemble-edit-yaml-editor"] .cm-content', { timeout: 10000 })
        .should("contain.text", "edited by cypress");

      cy.logStep("Introducing invalid YAML");
      appendEditorLine('[data-testid="ensemble-edit-yaml-editor"] .cm-content', "invalid: ]");
      cy.get('[data-testid="ensemble-edit-dialog"]')
        .contains("Syntax issue:", { timeout: 20000 })
        .should("be.visible");
      cy.get('[data-testid="ensemble-dialog-next"]').should("be.disabled");
      cy.get('[data-testid="ensemble-dialog-cancel"]').click();

      cy.logStep("Opening delete dialog and canceling");
      cy.get(`${rowSelector} [data-testid="ensemble-delete-button"]`).click({
        force: true,
      });
      cy.get('[data-testid="ensemble-delete-dialog"]').should("be.visible");
      cy.get('[data-testid="ensemble-delete-cancel"]').click();
      cy.get('[data-testid="ensemble-delete-dialog"]').should("not.exist");
      cy.get(rowSelector).should("exist");

      cy.logStep("Deleting ensemble");
      cy.get(`${rowSelector} [data-testid="ensemble-delete-button"]`).click({
        force: true,
      });
      cy.get('[data-testid="ensemble-delete-dialog"]').should("be.visible");
      cy.get('[data-testid="ensemble-delete-confirm"]').click();
      cy.get(rowSelector, { timeout: 60000 }).should("not.exist");
      Cypress.env("ENSEMBLE_EDIT_STEM", null);
      return cy.task("setRunValue", { key: storageKey, value: null }, { log: false });
    });
  });

  it("creates an ensemble with manual JSON and preserves state when toggling modes", function () {
    if (skipDestructive) {
      this.skip();
    }

    const stem = `cypress-manual-${Date.now()}`;
    cy.logStep(`Creating manual JSON ensemble ${stem}`);
    cy.cleanupEnsembleByStem(stem, { backendBaseUrl });

    openCreateDialog();
    uploadYaml(stem, buildYaml(stem));

    cy.logStep("Switching to manual JSON mode");
    cy.get('[data-testid="ensemble-dialog-next"]').click();
    cy.get('[data-testid="ensemble-json-mode-manual"]').click({ force: true });
    cy.get('[data-testid="ensemble-json-toggle"]').click();
    cy.get('[data-testid="ensemble-json-textarea"]', { timeout: 10000 }).clear().type(buildManualJson(stem), {
      delay: 0,
    });

    saveTemplate();

    cy.logStep("Opening edit dialog to validate state");
    cy.get(`[data-testid="ensemble-row"][data-ensemble-stem="${stem}"]`, { timeout: 60000 }).should("exist");
    cy.get(`[data-testid="ensemble-row"][data-ensemble-stem="${stem}"] [data-testid="ensemble-edit-button"]`).click({
      force: true,
    });

    cy.get('[data-testid="ensemble-edit-dialog"]').should("be.visible");
    cy.get('[data-testid="ensemble-dialog-next"]').click();
    cy.get('[data-testid="ensemble-dialog-back"]').click();
    cy.get('[data-testid="ensemble-dialog-cancel"]').click();

    cy.logStep("Deleting manual JSON ensemble");
    cy.get(`[data-testid="ensemble-row"][data-ensemble-stem="${stem}"] [data-testid="ensemble-delete-button"]`).click({
      force: true,
    });
    cy.get('[data-testid="ensemble-delete-confirm"]').click();
    cy.get(`[data-testid="ensemble-row"][data-ensemble-stem="${stem}"]`, { timeout: 60000 }).should("not.exist");
  });

  it("surfaces validation errors for invalid manual JSON", function () {
    if (skipDestructive) {
      this.skip();
    }

    const stem = `cypress-invalid-${Date.now()}`;
    cy.logStep(`Validating JSON errors for ${stem}`);
    cy.cleanupEnsembleByStem(stem, { backendBaseUrl });

    openCreateDialog();
    uploadYaml(stem, buildYaml(stem));
    cy.get('[data-testid="ensemble-dialog-next"]').click();
    cy.get('[data-testid="ensemble-json-mode-manual"]').click({ force: true });
    cy.get('[data-testid="ensemble-json-toggle"]').click();
    cy.get('[data-testid="ensemble-json-textarea"]').clear({ force: true }).type("{invalid json", { delay: 0 });
    cy.get('[data-testid="ensemble-json-helper"]').should("contain.text", "JSON");
    cy.get('[data-testid="ensemble-dialog-save"]').should("be.disabled");
    cy.logStep("Closing invalid JSON dialog");
    cy.get('[data-testid="ensemble-dialog-cancel"]').click();
  });

});
