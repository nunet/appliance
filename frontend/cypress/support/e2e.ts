import "@testing-library/cypress/add-commands";

type LoginOptions = {
  password?: string;
  backendBaseUrl?: string;
  setupTokenPath?: string;
};
type Mode = "simple" | "advanced";

type MailhogAddress = {
  Mailbox?: string;
  Domain?: string;
};

type MailhogMessage = {
  ID?: string;
  Content?: {
    Headers?: Record<string, string[]>;
    Body?: string;
  };
  To?: MailhogAddress[];
};

type MailMessage = {
  id: string;
  subject?: string;
  body?: string;
};

const DEFAULT_PASSWORD = (Cypress.env("ADMIN_PASSWORD") as string) || "nunettest";

const getEnvNumber = (key: string, fallback: number): number => {
  const raw = Cypress.env(key);
  const value = typeof raw === "string" || typeof raw === "number" ? Number(raw) : Number.NaN;
  return Number.isFinite(value) ? value : fallback;
};

const MAIL_POLL_DELAY_MS = getEnvNumber("MAIL_POLL_DELAY_MS", 30000);
const MAIL_TIMEOUT_MS = getEnvNumber("MAIL_TIMEOUT_MS", 600000);

const getBackendBaseUrl = () =>
  (Cypress.env("BACKEND_BASE_URL") as string) || "http://localhost:8080";

const getMailhogBaseUrl = () =>
  ((Cypress.env("MAILHOG_BASE_URL") as string) || "https://mailhog.nunet.network").replace(/\/$/, "");

const getMailInboxDomain = () =>
  (Cypress.env("MAIL_INBOX_DOMAIN") as string) || "mailhog.nunet.network";

const getMailSubjectFragment = () =>
  (Cypress.env("MAIL_SUBJECT_FRAGMENT") as string) || "Verify your NuNet onboarding request";

const getMailhogAuthHeaders = (): Record<string, string> => {
  const username = Cypress.env("MAILHOG_USERNAME") as string | undefined;
  const password = Cypress.env("MAILHOG_PASSWORD") as string | undefined;
  if (!username) {
    return {};
  }
  const token = Cypress.Buffer.from(`${username}:${password ?? ""}`).toString("base64");
  return { Authorization: `Basic ${token}` };
};

const getHeaderValue = (headers: Record<string, string[]> | undefined, key: string): string => {
  if (!headers) {
    return "";
  }
  const match = Object.keys(headers).find((name) => name.toLowerCase() === key.toLowerCase());
  if (!match) {
    return "";
  }
  const value = headers[match];
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return String(value ?? "");
};

const getLogPrefix = () => {
  const spec = Cypress.spec?.name;
  return spec ? `[${spec}]` : "[e2e]";
};

const extractMailhogRecipients = (message: MailhogMessage): string[] => {
  const recipients: string[] = [];
  (message.To || []).forEach((addr) => {
    if (addr?.Mailbox && addr?.Domain) {
      recipients.push(`${addr.Mailbox}@${addr.Domain}`);
    }
  });
  const headerTo = getHeaderValue(message.Content?.Headers, "To");
  if (headerTo) {
    headerTo.split(",").forEach((entry) => {
      const trimmed = entry.trim();
      if (trimmed) {
        recipients.push(trimmed);
      }
    });
  }
  return recipients.map((value) => value.trim().toLowerCase()).filter(Boolean);
};

const matchesMailhogMessage = (
  message: MailhogMessage,
  targetEmail: string,
  subjectFragment: string
): boolean => {
  const recipients = extractMailhogRecipients(message);
  const normalizedEmail = targetEmail.trim().toLowerCase();
  if (!recipients.includes(normalizedEmail)) {
    return false;
  }
  if (!subjectFragment) {
    return true;
  }
  const subject = getHeaderValue(message.Content?.Headers, "Subject");
  return subject.toLowerCase().includes(subjectFragment.toLowerCase());
};

const shouldSkipDestructiveEnsembleOps = () => Boolean(Cypress.env("ENSEMBLE_SKIP_DESTRUCTIVE"));

type EnsembleTemplateListItem = {
  stem: string;
  path: string;
  yaml_path?: string;
  category?: string;
};

type EnsembleTemplatesResponse = {
  items?: EnsembleTemplateListItem[];
};

function persistAppMode(mode: Mode = "simple") {
  cy.window().then((win) => {
    const payload = {
      state: { mode },
      version: 0,
    };
    win.localStorage.setItem("app-mode-storage", JSON.stringify(payload));
  });
}

function storeTokenInLocalStorage(token: string, expiresInSeconds: number) {
  cy.window().then((win) => {
    const expiresAt = Date.now() + expiresInSeconds * 1000;
    win.localStorage.setItem("nunet-admin-token", token);
    win.localStorage.setItem("nunet-admin-expiry", String(expiresAt));
  });
}

function assertAuthTokenStored() {
  cy.window().should((win) => {
    const token = win.localStorage.getItem("nunet-admin-token");
    expect(token, "auth token present").to.be.a("string").and.not.be.empty;
  });
}

Cypress.Commands.add("logStep", (message: string) => {
  const prefix = getLogPrefix();
  cy.log(message);
  return cy.task("log", `${prefix} ${message}`);
});

Cypress.on("fail", (error, runnable) => {
  const title = runnable?.fullTitle ? runnable.fullTitle() : runnable?.title || "unknown test";
  const details = error?.stack || error?.message || String(error);
  // eslint-disable-next-line no-console
  console.error(`[cypress][fail] ${title}\n${details}`);
  throw error;
});

Cypress.on("uncaught:exception", (error) => {
  const details = error?.stack || error?.message || String(error);
  // eslint-disable-next-line no-console
  console.error(`[cypress][uncaught] ${details}`);
});

Cypress.Commands.add("loginOrInitialize", (options: LoginOptions = {}) => {
  const password = options.password ?? DEFAULT_PASSWORD;
  const backendBaseUrl = options.backendBaseUrl ?? getBackendBaseUrl();
  const setupTokenPath = options.setupTokenPath ?? (Cypress.env("SETUP_TOKEN_PATH") as string | undefined);

  cy.request({
    method: "GET",
    url: `${backendBaseUrl}/auth/status`,
    failOnStatusCode: false,
    retryOnNetworkFailure: true,
    timeout: 60000,
  }).then((resp) => {
    const passwordSet = Boolean(resp.body?.password_set);

    if (!passwordSet) {
      cy.logStep("Password not set; running setup flow");
      cy.task("readSetupToken", { path: setupTokenPath })
        .then((token: string | null) => token || cy.task("generateSetupToken", { path: setupTokenPath }))
        .then((token: string | null) => {
          if (!token) {
            throw new Error(
              "Setup token not found. Provide CYPRESS_SETUP_TOKEN, set CYPRESS_SETUP_TOKEN_PATH, or place the token at ~/.secrets/setup_token."
            );
          }
        cy.visit(`/#/setup?setup_token=${token}`);
        cy.get('[data-testid="setup-password-input"]').should("be.visible").clear().type(password, { log: false });
        cy.get('[data-testid="setup-password-confirm-input"]').clear().type(password, { log: false });
        cy.get('[data-testid="setup-submit-button"]').click();
        assertAuthTokenStored();
        });
      return;
    }

    cy.request("POST", `${backendBaseUrl}/auth/token`, { password }).then((loginResp) => {
      const token = loginResp.body?.access_token as string | undefined;
      const expiresIn = loginResp.body?.expires_in ?? 1800;
      if (token) {
        cy.visit("/#/login").then(() => {
          storeTokenInLocalStorage(token, expiresIn);
        });
        cy.visit("/#/");
        return;
      }

      cy.visit("/#/login");
      cy.get("body").then(($body) => {
        if ($body.find('[data-testid="login-form"]').length > 0) {
          cy.get('[data-testid="login-password-input"]').should("be.visible").clear().type(password, { log: false });
          cy.get('[data-testid="login-submit-button"]').click();
        }
      });
      assertAuthTokenStored();
    });
  });

  // land on the app after authentication
  cy.visit("/#/");
});

Cypress.Commands.add("ensureAppMode", (mode: Mode = "simple") => {
  cy.logStep(`Ensuring app mode: ${mode}`);
  // The mode selector UI is not always routed in the app. Keep tests stable by forcing
  // the persisted Zustand value directly.
  return cy.window({ log: false }).then((win) => {
    const raw = win.localStorage.getItem("app-mode-storage");
    if (raw) {
      try {
        const storedMode = (JSON.parse(raw) as { state?: { mode?: string } })?.state?.mode;
        if (storedMode === mode) {
          return;
        }
      } catch {
        // ignore parse errors and overwrite below
      }
    }

    const payload = { state: { mode }, version: 0 };
    win.localStorage.setItem("app-mode-storage", JSON.stringify(payload));
  });
});

Cypress.Commands.add("resetOnboarding", (backendBaseUrl?: string) => {
  const baseUrl = backendBaseUrl ?? getBackendBaseUrl();
  return cy
    .window({ log: false })
    .then((win) => win.localStorage.getItem("nunet-admin-token"))
    .then((token) =>
      cy
        .request({
          method: "POST",
          url: `${baseUrl}/organizations/onboarding/reset`,
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          failOnStatusCode: false,
        })
        .then((resp) => {
          if (resp.status < 200 || resp.status >= 300) {
            throw new Error(`Failed to reset onboarding state: status ${resp.status}`);
          }
          return resp;
        })
    );
});

Cypress.Commands.add(
  "waitForMail",
  (mailbox: string, subjectFragment: string = getMailSubjectFragment(), timeoutMs = MAIL_TIMEOUT_MS) => {
    const apiUrl = getMailhogBaseUrl();
    const headers = getMailhogAuthHeaders();
    const targetEmail = `${mailbox}@${getMailInboxDomain()}`;
    const started = Date.now();
    cy.logStep(`Waiting for Mailhog email to ${targetEmail}, subject~="${subjectFragment}", timeout=${timeoutMs}ms`);

    const poll = (): Cypress.Chainable<MailMessage> => {
      return cy
        .request({
          method: "GET",
          url: `${apiUrl}/api/v2/messages`,
          headers,
          failOnStatusCode: false,
        })
        .then((resp) => {
          if (resp.status !== 200) {
            throw new Error(`Mailhog inbox query failed: ${resp.status}`);
          }
          const items = (resp.body?.items ?? []) as MailhogMessage[];
          const match = items.find((message) => matchesMailhogMessage(message, targetEmail, subjectFragment));

          if (match?.ID) {
            const subject = getHeaderValue(match.Content?.Headers, "Subject");
            const body = match.Content?.Body ?? "";
            return { id: match.ID, subject, body };
          }

          if (Date.now() - started > timeoutMs) {
            throw new Error(
              `Timed out waiting for Mailhog message to ${targetEmail} matching "${subjectFragment || "any subject"}"`
            );
          }

          cy.logStep(`No mail yet for ${targetEmail}, sleeping ${MAIL_POLL_DELAY_MS}ms...`);
          return cy.wait(MAIL_POLL_DELAY_MS).then(() => poll());
        });
    };

    return poll();
  }
);

Cypress.Commands.add("listEnsembleTemplates", (backendBaseUrl?: string) => {
  const baseUrl = backendBaseUrl ?? getBackendBaseUrl();
  return cy
    .window({ log: false })
    .then((win) => win.localStorage.getItem("nunet-admin-token"))
    .then((token) =>
      cy
        .request<EnsembleTemplatesResponse>({
          method: "GET",
          url: `${baseUrl}/ensemble/templates`,
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          failOnStatusCode: false,
        })
        .then((resp) => {
          if (resp.status !== 200) {
            throw new Error(`Failed to list ensemble templates (status ${resp.status})`);
          }
          return resp.body || {};
        })
    );
});

Cypress.Commands.add(
  "deleteEnsembleByPath",
  (templatePath: string, backendBaseUrl?: string) => {
    const baseUrl = backendBaseUrl ?? getBackendBaseUrl();
    if (shouldSkipDestructiveEnsembleOps()) {
      cy.logStep(`Skipping delete for ${templatePath} because ENSEMBLE_SKIP_DESTRUCTIVE is set`);
      return cy.wrap(null);
    }
    return cy
      .window({ log: false })
      .then((win) => win.localStorage.getItem("nunet-admin-token"))
      .then((token) =>
        cy
          .request({
            method: "DELETE",
            url: `${baseUrl}/ensemble/templates/detail`,
            qs: { template_path: templatePath },
            headers: token ? { Authorization: `Bearer ${token}` } : undefined,
            failOnStatusCode: false,
          })
          .then((resp) => {
            if (resp.status >= 400) {
              throw new Error(`Failed to delete template ${templatePath} (status ${resp.status})`);
            }
            return resp;
          })
      );
  }
);

Cypress.Commands.add(
  "cleanupEnsembleByStem",
  (stem: string, options: { category?: string; backendBaseUrl?: string } = {}) => {
    const baseUrl = options.backendBaseUrl ?? getBackendBaseUrl();
    if (shouldSkipDestructiveEnsembleOps()) {
      cy.logStep(`Skipping cleanup for ${stem} because ENSEMBLE_SKIP_DESTRUCTIVE is set`);
      return cy.wrap(null);
    }
    return cy.listEnsembleTemplates(baseUrl).then((body) => {
      const items = body?.items ?? [];
      const matches = items.filter(
        (item) => item.stem === stem && (!options.category || item.category === options.category)
      );
      if (!matches.length) {
        cy.logStep(`No ensembles found for stem=${stem}`);
        return;
      }
      return cy.wrap(matches).each((tpl) => {
        const path = tpl.yaml_path || tpl.path;
        if (!path) return;
        return cy.deleteEnsembleByPath(path, baseUrl);
      });
    });
  }
);

declare global {
  namespace Cypress {
    interface Chainable {
      logStep(message: string): Chainable<void>;
      loginOrInitialize(options?: LoginOptions): Chainable<void>;
      waitForMail(mailbox: string, subjectFragment?: string, timeoutMs?: number): Chainable<MailMessage>;
      resetOnboarding(backendBaseUrl?: string): Chainable<Cypress.Response<any>>;
      ensureAppMode(mode?: Mode): Chainable<void>;
      listEnsembleTemplates(backendBaseUrl?: string): Chainable<EnsembleTemplatesResponse>;
      deleteEnsembleByPath(templatePath: string, backendBaseUrl?: string): Chainable<Cypress.Response<any> | null>;
      cleanupEnsembleByStem(
        stem: string,
        options?: { category?: string; backendBaseUrl?: string }
      ): Chainable<void>;
    }
  }
}

export {};
