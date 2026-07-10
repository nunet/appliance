import { defineConfig, devices } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";

const configDir = path.dirname(fileURLToPath(import.meta.url));
const authFile = path.join(configDir, "playwright", ".auth", "admin.json");

const baseURL =
  process.env.APPLIANCE_BASE_URL?.replace(/\/$/, "") ?? "https://localhost:8443";

export default defineConfig({
  testDir: "./playwright",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { open: 'never'}],
    ["json", { outputFile: "playwright-report/results.json" }],
  ],
  timeout: 120_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    ignoreHTTPSErrors: true,
    storageState: authFile,
    //screenshot: 'on-first-retry', // Only takes a screenshot on failure
    //video: 'on-first-retry',      // Only records a video on failure
    //trace: 'on-first-retry',      // Only generates a trace on failure
    //screenshot: 'retain-on-failure',
    //video: 'retain-on-failure',
    //trace: 'retain-on-failure',
    screenshot: 'on',
    video: 'on',
    trace: 'on',
    headless: true,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  globalSetup: path.join(configDir, "playwright", "global-setup.ts"),
});
