import { APIRequestContext, Page, expect, request as playwrightRequest } from "@playwright/test";

export const DEFAULT_BASE_URL =
  process.env.APPLIANCE_BASE_URL?.replace(/\/$/, "") ?? "https://localhost:8443";

let cachedAuthHeaders: Record<string, string> | null = null;

export async function authedRequest(): Promise<APIRequestContext> {
  if (!cachedAuthHeaders) {
    const password = process.env.APPLIANCE_ADMIN_PASSWORD?.trim() ?? "";
    if (!password) {
      throw new Error("APPLIANCE_ADMIN_PASSWORD is required for API helpers");
    }
    const bootstrap = await playwrightRequest.newContext({
      baseURL: DEFAULT_BASE_URL,
      ignoreHTTPSErrors: true,
    });
    const login = await bootstrap.post("/auth/token", { data: { password } });
    expect(login.ok(), `auth token status ${login.status()}`).toBeTruthy();
    const body = (await login.json()) as { access_token?: string };
    if (!body.access_token) {
      throw new Error("Auth response missing access_token");
    }
    cachedAuthHeaders = { Authorization: `Bearer ${body.access_token}` };
    await bootstrap.dispose();
  }
  return playwrightRequest.newContext({
    baseURL: DEFAULT_BASE_URL,
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: cachedAuthHeaders,
  });
}

export function logStep(message: string) {
  // eslint-disable-next-line no-console
  console.log(`[e2e] ${message}`);
}

export async function ensureAppMode(page: Page, mode: "simple" | "advanced" = "simple") {
  await page.addInitScript((m) => {
    sessionStorage.setItem("nunet-e2e", "1");
    localStorage.setItem(
      "app-mode-storage",
      JSON.stringify({ state: { mode: m }, version: 0 })
    );
  }, mode);
}

function parseOnboardedFromStatus(onboarding_status?: string): boolean {
  const raw = (onboarding_status ?? "").replace(/\x1b\[[0-9;]*m/g, "");
  const normalized = raw.trim().toUpperCase();
  return normalized.includes("ONBOARDED") && !normalized.includes("NOT ONBOARD");
}

/** True when DMS reports the node is onboarded (same rule as dashboard section-cards). */
export async function isDmsOnboarded(refresh = false): Promise<boolean> {
  const request = await authedRequest();
  try {
    const resp = await request.get(
      "/dms/status/full",
      refresh ? { params: { refresh: true } } : undefined
    );
    if (!resp.ok()) {
      return false;
    }
    const body = (await resp.json()) as { onboarding_status?: string };
    return parseOnboardedFromStatus(body.onboarding_status);
  } finally {
    await request.dispose();
  }
}

/** Poll DMS until onboarded flag matches (for long offboard/onboard transitions). */
export async function waitForDmsOnboarded(
  expected: boolean,
  options?: { maxMs?: number; intervalMs?: number }
): Promise<boolean> {
  const maxMs = options?.maxMs ?? 120_000;
  const intervalMs = options?.intervalMs ?? 15_000;
  const started = Date.now();
  while (Date.now() - started < maxMs) {
    if ((await isDmsOnboarded(true)) === expected) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return false;
}

export async function resetOnboarding() {
  const request = await authedRequest();
  const resp = await request.post("/organizations/onboarding/reset");
  expect(resp.ok(), `onboarding reset status ${resp.status()}`).toBeTruthy();
  await request.dispose();
}

export async function openSidebar(page: Page, label: RegExp) {
  await page.locator('[data-slot="sidebar"]').getByText(label).click();
}
