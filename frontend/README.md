# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default tseslint.config([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      ...tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      ...tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      ...tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default tseslint.config([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

## E2E testing (Playwright)

Browser tests use **Playwright** against the **integrated appliance** (`APPLIANCE_BASE_URL`, DEV ON). Full testing layout (pytest unit / integration / contract + Playwright) is documented in the [repository root README](../README.md#testing-dev-on-pyramid) and [`.cursor/rules/testing.mdc`](../.cursor/rules/testing.mdc).

**Env:** copy [`.env.test.example`](../.env.test.example) to `.env.test` at the repo root (`APPLIANCE_BASE_URL`, `APPLIANCE_ADMIN_PASSWORD`).

**CI parity** (from repo root, after `nunet-web-mode.sh dev-on` + `rebuild`):

```bash
set -a && source .env.test && set +a
./deploy/scripts/run-playwright-ci.sh
```

Uses Docker + `mcr.microsoft.com/playwright` by default (Chromium isolated from the appliance). Pass extra args to `pnpm e2e`, e.g. `./deploy/scripts/run-playwright-ci.sh playwright/login-and-dashboard.spec.ts`.

**Native on host** (optional):

```bash
set -a && source .env.test && set +a
cd frontend
pnpm install --frozen-lockfile
npx playwright install --with-deps chromium
pnpm e2e          # headless
pnpm e2e:ui       # interactive UI mode
```

Or `RUN_PLAYWRIGHT_NATIVE=1 ./deploy/scripts/run-playwright-ci.sh`.

Specs live in **`playwright/`**. Auth is prepared in **`playwright/global-setup.ts`** (`POST /auth/token` → `playwright/.auth/admin.json`).

Optional env: `MAILHOG_*` (join-mail spec), `NUTEST_ORG_DID`, `DEPLOYMENTS_SKIP=1`, `ENSEMBLE_SKIP_DESTRUCTIVE=1`.
