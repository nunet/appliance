import { defineConfig } from "cypress";
import fs from "fs";
import path from "path";
import crypto from "crypto";

const runValues = new Map<string, string | null>();

function readSetupTokenFromDisk(customPath?: string): string | null {
  const envToken = process.env.CYPRESS_SETUP_TOKEN;
  if (envToken && envToken.trim()) {
    return envToken.trim();
  }

  const candidates: string[] = [];
  if (customPath) {
    candidates.push(customPath);
  }
  if (process.env.CYPRESS_SETUP_TOKEN_PATH) {
    candidates.push(process.env.CYPRESS_SETUP_TOKEN_PATH);
  }
  const home = process.env.HOME || process.cwd();
  candidates.push(path.join(home, ".secrets", "setup_token"));

  for (const filePath of candidates) {
    try {
      if (filePath && fs.existsSync(filePath)) {
        const value = fs.readFileSync(filePath, "utf8").trim();
        if (value) {
          return value;
        }
      }
    } catch (error) {
      console.warn("[cypress.config] Failed to read setup token", filePath, error);
    }
  }

  return null;
}

function generateSetupToken(targetPath?: string): string | null {
  const token =
    process.env.CYPRESS_SETUP_TOKEN && process.env.CYPRESS_SETUP_TOKEN.trim()
      ? process.env.CYPRESS_SETUP_TOKEN.trim()
      : crypto.randomBytes(12).toString("base64url");

  const home = process.env.HOME || process.cwd();
  const tokenPath = targetPath || process.env.CYPRESS_SETUP_TOKEN_PATH || path.join(home, ".secrets", "setup_token");

  try {
    fs.mkdirSync(path.dirname(tokenPath), { recursive: true, mode: 0o700 });
    fs.writeFileSync(tokenPath, token, { encoding: "utf8", mode: 0o600 });
    return token;
  } catch (error) {
    console.warn("[cypress.config] Failed to write setup token", tokenPath, error);
    return null;
  }
}

export default defineConfig({
  video: false, // disable to save memory on low-spec hosts; enable locally if needed
  screenshotOnRunFailure: true,
  experimentalMemoryManagement: true,
  e2e: {
    retries: {
      runMode: 3,
      openMode: 0,
    },
    numTestsKeptInMemory: 0,
    baseUrl: process.env.CYPRESS_BASE_URL ?? "http://localhost:5173",
    specPattern: "cypress/e2e/**/*.cy.ts",
    supportFile: "cypress/support/e2e.ts",
    chromeWebSecurity: false,
    env: {
      BACKEND_BASE_URL: process.env.CYPRESS_BACKEND_BASE_URL ?? "http://localhost:8080",
      SETUP_TOKEN_PATH: process.env.CYPRESS_SETUP_TOKEN_PATH,
      MAILHOG_BASE_URL: process.env.CYPRESS_MAILHOG_BASE_URL ?? "https://mailhog.nunet.network",
      MAILHOG_USERNAME: process.env.CYPRESS_MAILHOG_USERNAME,
      MAILHOG_PASSWORD: process.env.CYPRESS_MAILHOG_PASSWORD,
      MAIL_INBOX_DOMAIN: process.env.CYPRESS_MAIL_INBOX_DOMAIN ?? "mailhog.nunet.network",
      MAIL_SUBJECT_FRAGMENT:
        process.env.CYPRESS_MAIL_SUBJECT_FRAGMENT ?? "Verify your NuNet onboarding request",
      MAIL_POLL_DELAY_MS: process.env.CYPRESS_MAIL_POLL_DELAY_MS,
      MAIL_TIMEOUT_MS: process.env.CYPRESS_MAIL_TIMEOUT_MS,
    },
    setupNodeEvents(on, config) {
      on("task", {
        log(message: string) {
          // eslint-disable-next-line no-console
          console.log(message);
          return null;
        },
        getRunValue(options?: { key?: string }) {
          const key = options?.key ?? "";
          return runValues.get(key) ?? null;
        },
        setRunValue(options?: { key?: string; value?: string | null }) {
          const key = options?.key ?? "";
          runValues.set(key, options?.value ?? null);
          return null;
        },
        readSetupToken(options?: { path?: string }) {
          return readSetupTokenFromDisk(options?.path ?? config.env?.SETUP_TOKEN_PATH);
        },
        generateSetupToken(options?: { path?: string }) {
          return generateSetupToken(options?.path ?? config.env?.SETUP_TOKEN_PATH);
        },
      });
      on("after:spec", (spec, results) => {
        if (!results || !results.tests) {
          return;
        }
        const failures = results.tests.filter((test) => test.state === "failed");
        if (!failures.length) {
          return;
        }
        // eslint-disable-next-line no-console
        console.error(`[cypress] ${spec.relative} failures: ${failures.length}`);
        failures.forEach((test, index) => {
          const title = Array.isArray(test.title) ? test.title.join(" > ") : String(test.title || "unknown test");
          const attempts = Array.isArray(test.attempts) ? test.attempts : [];
          const lastAttempt = attempts[attempts.length - 1];
          const errorMessage =
            test.displayError ||
            lastAttempt?.error?.message ||
            lastAttempt?.error?.stack ||
            "";
          // eslint-disable-next-line no-console
          console.error(`--- Failure ${index + 1}: ${title}`);
          if (errorMessage) {
            // eslint-disable-next-line no-console
            console.error(errorMessage);
          }
        });
      });
      return config;
    },
  },
});
