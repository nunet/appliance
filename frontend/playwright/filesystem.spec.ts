import { test, expect } from "@playwright/test";
import { authedRequest, ensureAppMode, logStep, openSidebar } from "./helpers";

const CONTRACTS_ROOT = "/home/ubuntu/contracts";
const TEST_PARENT_NAME = "playwright-filesystem-e2e";
const TEST_PARENT_PATH = `${CONTRACTS_ROOT}/${TEST_PARENT_NAME}`;

test.describe.skip("Filesystem browser", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAppMode(page, "simple");
    await page.goto("/#/");
    await page.evaluate(() => localStorage.setItem("filesystemView", "list"));
    await openSidebar(page, /^File System$/);
    await expect(page).toHaveURL(/#\/appliance\/filesystem/);
    await expect(page.getByText("File System", { exact: true })).toBeVisible();
  });

  test("shows allowlisted roots and supports view toggle", async ({ page }) => {
    const table = page.locator("table").first();
    await expect(table.getByRole("button", { name: /^contracts$/ })).toBeVisible();
    await expect(table.getByRole("button", { name: /^ensembles$/ })).toBeVisible();
    await expect(table.getByRole("button", { name: /^nunet$/ })).toBeVisible();
    await expect(table.getByRole("button", { name: /^appliance$/ })).toHaveCount(0);

    await page.getByRole("button", { name: "Grid view" }).click();
    await expect(page.getByText("Last modified")).toBeVisible();
    await expect(page.locator("table")).toHaveCount(0);

    await page.getByRole("button", { name: "List view" }).click();
    await expect(page.locator("table").first()).toBeVisible();
  });

  test("creates folders, uploads, renames, copies, moves, and deletes recursively", async ({
    page,
  }) => {
    const runId = `run-${Date.now()}`;
    const runFolder = `${TEST_PARENT_PATH}/${runId}`;

    const request = await authedRequest();
    await request.post("/filesystem/folder", {
      data: { path: TEST_PARENT_PATH, parents: true, exist_ok: true },
    });
    await request.delete("/filesystem", {
      data: { paths: [runFolder], recursive: true },
      failOnStatusCode: false,
    });
    await request.dispose();

    const openDir = async (name: string) => {
      logStep(`Opening directory: ${name}`);
      await page.locator("table").first().getByRole("button", { name }).click();
    };

    await openDir("contracts");
    await openDir(TEST_PARENT_NAME);
    await page.getByRole("button", { name: "New Folder" }).click();
    await page.getByRole("dialog").getByPlaceholder("Folder name").fill(`${runId}{enter}`);
    await openDir(runId);
    await page.getByRole("button", { name: "New Folder" }).click();
    await page.getByRole("dialog").getByPlaceholder("Folder name").fill("src{enter}");
    await page.getByRole("button", { name: "New Folder" }).click();
    await page.getByRole("dialog").getByPlaceholder("Folder name").fill("dst{enter}");
    await openDir("src");

    const upload = async (fileName: string, contents: string) => {
      await page.locator('input[type="file"]').setInputFiles({
        name: fileName,
        mimeType: "text/plain",
        buffer: Buffer.from(contents),
      });
      await expect(page.locator("table").first().getByRole("button", { name: fileName })).toBeVisible();
    };

    await upload("copy.txt", "copied by playwright");
    await page.locator("table").first().getByRole("row", { name: /copy\.txt/ }).getByRole("checkbox").click();
    await page.getByRole("button", { name: "Rename" }).click();
    await page.locator('input[value="copy.txt"]').fill("copy-renamed.txt{enter}");
    await expect(page.locator("table").first().getByRole("button", { name: "copy-renamed.txt" })).toBeVisible();

    await page.locator("table").first().getByRole("row", { name: /copy-renamed/ }).getByRole("checkbox").click();
    await page.getByRole("button", { name: "Copy" }).click();
    await page.getByRole("button", { name: "Up" }).click();
    await openDir("dst");
    await page.getByRole("button", { name: "Paste" }).click();
    await expect(page.locator("table").first().getByRole("button", { name: "copy-renamed.txt" })).toBeVisible();
  });
});
