import { chromium, request } from "@playwright/test";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const configDir = path.dirname(fileURLToPath(import.meta.url));
const authDir = path.join(configDir, ".auth");
const authFile = path.join(authDir, "admin.json");

async function globalSetup() {
  const baseURL =
    process.env.APPLIANCE_BASE_URL?.replace(/\/$/, "") ?? "https://localhost:8443";
  const password = process.env.APPLIANCE_ADMIN_PASSWORD?.trim() ?? "";

  if (!password) {
    throw new Error(
      "APPLIANCE_ADMIN_PASSWORD is required for Playwright global setup"
    );
  }

  const api = await request.newContext({
    baseURL,
    ignoreHTTPSErrors: true,
  });

  const login = await api.post("/auth/token", {
    data: { password },
  });
  if (!login.ok()) {
    throw new Error(
      `POST /auth/token failed (${login.status()}): ${await login.text()}`
    );
  }

  const body = (await login.json()) as {
    access_token?: string;
    expires_in?: number;
  };
  const token = body.access_token;
  if (!token) {
    throw new Error("Auth response missing access_token");
  }
  const expiresIn = body.expires_in ?? 1800;
  await api.dispose();

  fs.mkdirSync(authDir, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  await page.goto(`${baseURL}/#/login`);
  await page.evaluate(
    ({ accessToken, ttlSeconds }) => {
      localStorage.setItem("nunet-admin-token", accessToken);
      localStorage.setItem(
        "nunet-admin-expiry",
        String(Date.now() + ttlSeconds * 1000)
      );
      localStorage.setItem(
        "app-mode-storage",
        JSON.stringify({ state: { mode: "simple" }, version: 0 })
      );
    },
    { accessToken: token, ttlSeconds: expiresIn }
  );
  await context.storageState({ path: authFile });
  await browser.close();
}

export default globalSetup;
