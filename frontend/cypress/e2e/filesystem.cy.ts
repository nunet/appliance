const TEST_PASSWORD = (Cypress.env("ADMIN_PASSWORD") as string) || "nunettest";
const backendBaseUrl = (Cypress.env("BACKEND_BASE_URL") as string) || "http://localhost:8080";

const DEFAULT_ROOT = "/home/ubuntu";
const CONTRACTS_ROOT = `${DEFAULT_ROOT}/contracts`;
const TEST_PARENT_NAME = "cypress-filesystem-e2e";
const TEST_PARENT_PATH = `${CONTRACTS_ROOT}/${TEST_PARENT_NAME}`;

function resolveRetrySafeId(prefix: string, storageKey: string) {
  return cy
    .task("getRunValue", { key: storageKey }, { log: false })
    .then((existing) => {
      const existingValue = (existing as string | null) ?? null;
      if (existingValue) {
        return existingValue;
      }
      const next = `${prefix}-${Date.now()}`;
      return cy.task("setRunValue", { key: storageKey, value: next }, { log: false }).then(() => next);
    });
}

function getAuthToken() {
  return cy.window({ log: false }).then((win) => {
    const token = win.localStorage.getItem("nunet-admin-token");
    if (!token) {
      throw new Error("Missing auth token in localStorage");
    }
    return token;
  });
}

function apiRequest<T = unknown>(options: {
  method: "GET" | "POST" | "DELETE";
  url: string;
  body?: unknown;
  failOnStatusCode?: boolean;
}) {
  return getAuthToken().then((token) =>
    cy.request<T>({
      method: options.method,
      url: `${backendBaseUrl}${options.url}`,
      body: options.body,
      headers: { Authorization: `Bearer ${token}` },
      failOnStatusCode: options.failOnStatusCode ?? true,
    })
  );
}

function openDirectory(name: string) {
  cy.logStep(`Opening directory: ${name}`);
  cy.get("table").within(() => {
    cy.contains("button", name).click({ force: true });
  });
  cy.wait("@fsList");
}

function createFolder(name: string) {
  cy.logStep(`Creating folder: ${name}`);
  cy.contains("button", /^New Folder$/).should("be.visible").click({ force: true });
  cy.findByRole("dialog").within(() => {
    cy.findByPlaceholderText("Folder name").should("be.visible").clear().type(`${name}{enter}`, { delay: 0 });
  });
  cy.wait("@fsFolder");
  cy.wait("@fsList");
  cy.get("table").within(() => {
    cy.contains("button", name).should("exist");
  });
}

function uploadTextFile(fileName: string, contents: string) {
  cy.logStep(`Uploading file: ${fileName}`);
  cy.get('input[type="file"]').selectFile(
    {
      contents: Cypress.Buffer.from(contents),
      fileName,
      mimeType: "text/plain",
    },
    { force: true }
  );
  cy.wait("@fsUpload");
  cy.wait("@fsList");
  cy.get("table").within(() => {
    cy.contains("button", fileName).should("exist");
  });
}

function selectEntry(name: string) {
  cy.logStep(`Selecting entry: ${name}`);
  cy.get("table").within(() => {
    cy.contains("tr", name).within(() => {
      cy.get('[role="checkbox"]').first().click({ force: true });
    });
  });
}

function renameInline(oldName: string, newName: string) {
  cy.logStep(`Renaming ${oldName} -> ${newName}`);
  selectEntry(oldName);
  cy.contains("button", /^Rename$/).should("not.be.disabled").click({ force: true });
  cy.get(`input[value="${oldName}"]`).should("be.visible").clear().type(`${newName}{enter}`, { delay: 0 });
  cy.wait("@fsMove");
  cy.wait("@fsList");
  cy.get("table").within(() => {
    cy.contains("button", newName).should("exist");
    cy.contains("button", oldName).should("not.exist");
  });
}

function openFilesystemPage() {
  cy.logStep("Opening filesystem page");
  cy.visit("/#/");
  cy.window({ log: false }).then((win) => {
    win.localStorage.setItem("filesystemView", "list");
  });
  cy.get('[data-slot="sidebar"]').contains("span", /^File System$/).click({ force: true });
  cy.location("hash", { timeout: 20000 }).should("eq", "#/appliance/filesystem");
  cy.contains('[data-slot="card-title"]', "File System", { timeout: 20000 }).should("be.visible");
  cy.wait("@fsList");
}

describe("Filesystem browser", () => {
  beforeEach(() => {
    cy.loginOrInitialize({ password: TEST_PASSWORD, backendBaseUrl });
    cy.ensureAppMode("simple");

    cy.intercept("GET", "**/filesystem/list*").as("fsList");
    cy.intercept("POST", "**/filesystem/folder").as("fsFolder");
    cy.intercept("POST", "**/filesystem/upload").as("fsUpload");
    cy.intercept("POST", "**/filesystem/copy").as("fsCopy");
    cy.intercept("POST", "**/filesystem/move").as("fsMove");
    cy.intercept("DELETE", "**/filesystem").as("fsDelete");
  });

  it("shows allowlisted roots and supports view toggle", () => {
    openFilesystemPage();

    cy.logStep("Asserting allowlisted roots at /home/ubuntu");
    cy.get("table").within(() => {
      cy.contains("button", /^contracts$/).should("exist");
      cy.contains("button", /^ensembles$/).should("exist");
      cy.contains("button", /^nunet$/).should("exist");
      // Ensure we are not showing the full /home/ubuntu directory.
      cy.contains("button", /^appliance$/).should("not.exist");
    });

    cy.logStep("Switching to grid view");
    cy.get('button[aria-label="Grid view"]').click({ force: true });
    cy.contains("Last modified").should("be.visible");
    cy.get("table").should("not.exist");

    cy.logStep("Switching back to list view");
    cy.get('button[aria-label="List view"]').click({ force: true });
    cy.get("table").should("exist");
  });

  it("creates folders, uploads, renames, copies, moves, and deletes recursively", () => {
    return resolveRetrySafeId("fs", "filesystem:RUN_ID").then((runId) => {
      const runFolder = `${TEST_PARENT_PATH}/${runId}`;

      cy.logStep(`Ensuring test parent exists: ${TEST_PARENT_PATH}`);
      apiRequest({
        method: "POST",
        url: "/filesystem/folder",
        body: { path: TEST_PARENT_PATH, parents: true, exist_ok: true },
      });

      cy.logStep(`Cleaning up previous run folder (if any): ${runFolder}`);
      apiRequest({
        method: "DELETE",
        url: "/filesystem",
        body: { paths: [runFolder], recursive: true },
        failOnStatusCode: false,
      });

      openFilesystemPage();

      openDirectory("contracts");
      openDirectory(TEST_PARENT_NAME);

      createFolder(runId);
      openDirectory(runId);

      createFolder("src");
      createFolder("dst");

      openDirectory("src");

      uploadTextFile("copy.txt", "copied by cypress");
      renameInline("copy.txt", "copy-renamed.txt");

      cy.logStep("Copying file to dst");
      selectEntry("copy-renamed.txt");
      cy.contains("button", /^Copy$/).should("not.be.disabled").click({ force: true });
      cy.contains("button", /^Up$/).click({ force: true });
      cy.wait("@fsList");
      openDirectory("dst");
      cy.contains("button", /^Paste$/).should("not.be.disabled").click({ force: true });
      cy.wait("@fsCopy");
      cy.wait("@fsList");
      cy.get("table").within(() => {
        cy.contains("button", "copy-renamed.txt").should("exist");
      });

      cy.logStep("Moving a file from src to dst using cut/paste");
      cy.contains("button", /^Up$/).click({ force: true });
      cy.wait("@fsList");
      openDirectory("src");
      uploadTextFile("move.txt", "moved by cypress");
      selectEntry("move.txt");
      cy.contains("button", /^Cut$/).should("not.be.disabled").click({ force: true });
      cy.contains("button", /^Up$/).click({ force: true });
      cy.wait("@fsList");
      openDirectory("dst");
      cy.contains("button", /^Paste$/).should("not.be.disabled").click({ force: true });
      cy.wait("@fsMove");
      cy.wait("@fsList");
      cy.get("table").within(() => {
        cy.contains("button", "move.txt").should("exist");
      });

      cy.logStep("Verifying moved file is no longer in src");
      cy.contains("button", /^Up$/).click({ force: true });
      cy.wait("@fsList");
      openDirectory("src");
      cy.get("table").within(() => {
        cy.contains("button", "move.txt").should("not.exist");
      });

      cy.logStep("Deleting the run folder recursively from the parent directory");
      cy.contains("button", /^Up$/).click({ force: true }); // back to run folder
      cy.wait("@fsList");
      cy.contains("button", /^Up$/).click({ force: true }); // back to parent folder
      cy.wait("@fsList");

      selectEntry(runId);
      cy.contains("button", /^Delete$/).should("not.be.disabled").click({ force: true });
      cy.findByRole("dialog").within(() => {
        cy.contains("Folders will be deleted recursively").should("be.visible");
        cy.contains("button", /^Delete$/).click({ force: true });
      });
      cy.wait("@fsDelete");
      cy.wait("@fsList");
      cy.get("table").within(() => {
        cy.contains("button", runId).should("not.exist");
      });
    });
  });
});
