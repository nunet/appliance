import { test, expect } from "@playwright/test";
import { ensureAppMode, logStep, openSidebar, resetOnboarding } from "./helpers";
import { waitForMail } from "./mailhog";

const DEFAULT_ORG_DID =
  process.env.NUTEST_ORG_DID ?? "did:key:z6MksqN98v97yXtaGkuJWeK5yJ9EejZEi6xM19oZa8t4zL5a";
const DEFAULT_ROLE = process.env.NUTEST_ROLE ?? "compute_provider";

test.describe.skip("Join organization with Mailhog confirmation", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAppMode(page, "simple");
    await resetOnboarding();
    await page.goto("/#/");
    await openSidebar(page, /^Organizations$/);
    await expect(page).toHaveURL(/#\/organizations/);
  });

  test("validates join form fields and cancel flow", async ({ page }) => {
    const card = page.locator(`[data-testid="org-card"][data-org-did="${DEFAULT_ORG_DID}"]`);
    const join = page.locator(`[data-testid="org-join-button"][data-org-did="${DEFAULT_ORG_DID}"]`);
    const leave = page.locator(`[data-testid="org-leave-button"][data-org-did="${DEFAULT_ORG_DID}"]`);

    await expect(card).toBeVisible({ timeout: 120_000 });
    if ((await join.count()) === 0 && (await leave.count()) > 0) {
      await leave.click();
      await page.getByTestId("org-leave-confirm-button").click();
      await expect(join).toBeVisible({ timeout: 120_000 });
    }

    await join.click();
    await expect(page.getByTestId("join-submit-button")).toBeDisabled();
    await page.getByTestId("join-name-input").fill("NuNet Playwright Tester");
    await expect(page.getByTestId("join-submit-button")).toBeDisabled();
    await page.getByTestId("join-field-email").fill("invalid-email");
    await expect(page.getByTestId("join-submit-button")).toBeDisabled();
    await page.getByTestId("join-field-email").fill("tester@example.com");
    await page.getByTestId("join-field-location").fill("Test City, Test Country");
    await expect(page.getByTestId("join-submit-button")).toBeEnabled();

    await page.getByTestId("join-cancel-button").click();
    await expect(page.getByText("Cancel joining")).toBeVisible();
    await page.getByRole("button", { name: "Keep Joining" }).click();
    await page.getByTestId("join-cancel-button").click();
    await page.getByRole("button", { name: "Cancel Onboarding" }).click();
    await expect(join).toBeVisible({ timeout: 120_000 });
  });

  test("submits a join request and follows the Mailhog verification link", async ({
    page,
    request,
  }) => {
    test.skip(!process.env.MAILHOG_USERNAME, "MAILHOG_USERNAME is not set");

    const mailbox = `join-${Date.now()}`;
    const inboxDomain = process.env.MAIL_INBOX_DOMAIN ?? "mailhog.nunet.network";
    const email = `${mailbox}@${inboxDomain}`;

    const card = page.locator(`[data-testid="org-card"][data-org-did="${DEFAULT_ORG_DID}"]`);
    const join = page.locator(`[data-testid="org-join-button"][data-org-did="${DEFAULT_ORG_DID}"]`);

    await expect(card).toBeVisible({ timeout: 120_000 });
    await join.click();

    await page.getByTestId("join-name-input").fill("NuNet Playwright Tester");
    await page.getByTestId("join-field-email").fill(email);
    await page.getByTestId("join-field-location").fill("Test City, Test Country");
    await page.getByTestId("join-field-discord").fill("mailhog-user");
    await page.locator(`[data-testid="join-role-${DEFAULT_ROLE}"]`).click();
    await page.getByTestId("join-submit-button").click();

    logStep(`Waiting for Mailhog message to ${email}`);
    const message = await waitForMail(request, mailbox);
    const body = (message.body || "").replace(/=\r?\n/g, "").replace(/=3D/g, "=");
    const hrefMatches = [...body.matchAll(/href="([^"]+)"/gi)].map((m) => m[1]!);
    const urlMatches = [...body.matchAll(/https?:\/\/[^\s"']+/gi)].map((m) => m[0]!);
    const candidates = [...hrefMatches, ...urlMatches].filter((u) => {
      const lower = u.toLowerCase();
      return !lower.endsWith(".svg") && !lower.includes("logo");
    });
    const confirmationUrl = (candidates[0] || "").trim();
    expect(confirmationUrl).toContain("http");
    logStep(`Visiting confirmation URL: ${confirmationUrl}`);
    await page.goto(confirmationUrl);

    await page.goto("/#/organizations");
    await expect(page.getByTestId("org-status-banner")).toBeVisible({ timeout: 120_000 });
  });
});
