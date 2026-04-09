import { defineConfig } from "cypress";
import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import crypto from "crypto";

const configDir = path.dirname(fileURLToPath(import.meta.url));
/** Repository root (parent of `frontend/` where this config lives). */
const repoRoot = path.resolve(configDir, "..");

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

function maybeRebuildFrontendBeforeRun(): void {
  const v = process.env.CYPRESS_REBUILD_FRONTEND;
  if (!v || !["1", "true", "yes"].includes(String(v).trim().toLowerCase())) {
    return;
  }
  const script = path.join(repoRoot, "deploy", "scripts", "nunet-web-mode.sh");
  if (!fs.existsSync(script)) {
    // eslint-disable-next-line no-console
    console.warn(`[cypress.config] CYPRESS_REBUILD_FRONTEND: missing ${script}`);
    return;
  }
  // eslint-disable-next-line no-console
  console.log("[cypress.config] CYPRESS_REBUILD_FRONTEND — running deploy/scripts/nunet-web-mode.sh rebuild …");
  execSync(`bash "${script}" rebuild`, {
    stdio: "inherit",
    cwd: repoRoot,
    env: process.env,
  });
}

/**
 * After Cypress starts (and after optional rebuild), wait so CPU/RAM can settle before specs —
 * helps DMS onboard tests when rebuild + Electron would otherwise keep load high.
 */
async function settleBeforeSpecsRun(): Promise<void> {
  const raw = process.env.CYPRESS_RUN_SETTLE_MS;
  if (raw !== undefined && ["0", "false", "no", "off"].includes(String(raw).trim().toLowerCase())) {
    return;
  }
  const ms = Math.min(
    600_000,
    Math.max(0, Number.parseInt(process.env.CYPRESS_RUN_SETTLE_MS ?? "30000", 10) || 30000)
  );
  if (ms <= 0) {
    return;
  }
  // eslint-disable-next-line no-console
  console.log(
    `[cypress.config] Waiting ${ms}ms before specs (host settle after startup/rebuild) — set CYPRESS_RUN_SETTLE_MS=0 to skip`
  );
  await new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });
}

type SpecRunStats = { startedAt?: string; endedAt?: string };

/**
 * After a failed spec on the integrated appliance, print `journalctl` for the spec run window so
 * DMS/onboard errors (exact `nunet` command, rc, stdout) appear next to Cypress output.
 * Uses `results.stats.startedAt` / `endedAt` from Cypress (whole spec, including retries): by default
 * 10s before start and 60s after end. Override with CYPRESS_JOURNAL_BEFORE_SEC / _AFTER_SEC.
 * If stats are missing, falls back to last N lines (CYPRESS_JOURNAL_LINES).
 * Disable: `CYPRESS_JOURNAL_ON_FAILURE=0`. Unit: `CYPRESS_JOURNAL_SERVICE`.
 */
function logJournalTailOnFailure(results: { stats?: SpecRunStats } | null | undefined): void {
  const raw = process.env.CYPRESS_JOURNAL_ON_FAILURE;
  if (raw !== undefined && ["0", "false", "no", "off"].includes(String(raw).trim().toLowerCase())) {
    return;
  }
  const defaultUnit = "nunet-appliance-web.service";
  const unitEnv = process.env.CYPRESS_JOURNAL_SERVICE?.trim();
  const unit =
    unitEnv && /^[a-zA-Z0-9.@\-]+$/.test(unitEnv) ? unitEnv : defaultUnit;
  const lines = Math.min(
    500,
    Math.max(20, Number.parseInt(process.env.CYPRESS_JOURNAL_LINES ?? "120", 10) || 120)
  );
  const beforeSec = Math.min(
    120,
    Math.max(0, Number.parseInt(process.env.CYPRESS_JOURNAL_BEFORE_SEC ?? "10", 10) || 10)
  );
  const afterSec = Math.min(
    600,
    Math.max(0, Number.parseInt(process.env.CYPRESS_JOURNAL_AFTER_SEC ?? "60", 10) || 60)
  );

  const stats = results?.stats;
  const startedAt = stats?.startedAt;
  const endedAt = stats?.endedAt;
  let out: string;
  let label: string;

  try {
    if (startedAt && endedAt) {
      const startMs = new Date(startedAt).getTime();
      const endMs = new Date(endedAt).getTime();
      if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) {
        throw new Error("invalid stats.startedAt/endedAt");
      }
      const sinceSec = Math.floor(startMs / 1000) - beforeSec;
      const untilSec = Math.floor(endMs / 1000) + afterSec;
      out = execSync(`journalctl -u ${unit} --since @${sinceSec} --until @${untilSec} --no-pager`, {
        encoding: "utf8",
        maxBuffer: 10 * 1024 * 1024,
        timeout: 60000,
      });
      label = `journalctl -u ${unit} --since @${sinceSec} (-${beforeSec}s from spec start) --until @${untilSec} (+${afterSec}s after spec end)`;
    } else {
      out = execSync(`journalctl -u ${unit} -n ${lines} --no-pager`, {
        encoding: "utf8",
        maxBuffer: 10 * 1024 * 1024,
        timeout: 60000,
      });
      label = `journalctl -u ${unit} (last ${lines} lines; spec stats.startedAt/endedAt missing)`;
    }
    // eslint-disable-next-line no-console
    console.error(`\n[cypress] --- ${label} ---`);
    // eslint-disable-next-line no-console
    console.error(out);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn(
      "[cypress] journalctl skipped (not on systemd host, bad time window, or no permission — try `adm` group or sudo):",
      err instanceof Error ? err.message : err
    );
  }
}

/** Env wins over defaults. If Cypress still probes 5173, `CYPRESS_BASE_URL` is set (often from `frontend/.env.e2e`). */
const resolvedBaseUrl = process.env.CYPRESS_BASE_URL ?? "https://localhost:8443";
const resolvedBackendUrl = process.env.CYPRESS_BACKEND_BASE_URL ?? "https://localhost:8443";
// eslint-disable-next-line no-console
console.log(
  "[cypress.config] baseUrl:",
  resolvedBaseUrl,
  process.env.CYPRESS_BASE_URL ? "(from CYPRESS_BASE_URL)" : "(default; set CYPRESS_BASE_URL to override)",
);

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
    baseUrl: resolvedBaseUrl,
    specPattern: "cypress/e2e/**/*.cy.ts",
    supportFile: "cypress/support/e2e.ts",
    chromeWebSecurity: false,
    env: {
      BACKEND_BASE_URL: resolvedBackendUrl,
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
      on("before:run", async () => {
        maybeRebuildFrontendBeforeRun();
        await settleBeforeSpecsRun();
      });
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
        const rel = spec.relative.replace(/\\/g, "/");
        const journalAll = ["1", "true", "yes"].includes(
          String(process.env.CYPRESS_JOURNAL_ALL_FAILURES ?? "").toLowerCase()
        );
        if (journalAll || rel.includes("real-appliance-dashboard")) {
          logJournalTailOnFailure(results);
        }
      });
      return config;
    },
  },
});
