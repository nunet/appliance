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

## E2E testing (Cypress)

Run end-to-end tests in a Docker container with a single script and a shared env file.

### Setup

1. Copy the example env file:
   ```bash
   cp .env.e2e.example .env.e2e
   ```
2. Edit `.env.e2e` with the correct credentials/URLs for your environment.

### Run all E2E specs in order (Docker)

The Docker runner script runs specs in this order by default:
1. Join organization (Mailhog)
2. Offboard/onboard
3. Deployments wizard + details
4. Ensembles CRUD/JSON flows

```bash
./scripts/run-e2e-docker.sh
```

### Run from another machine

Set the base URLs to the reachable host/IP for the UI and backend:

```bash
CYPRESS_BASE_URL=http://appliance-host:5173 \\
CYPRESS_BACKEND_BASE_URL=http://appliance-host:8080 \\
./scripts/run-e2e-docker.sh
```

On Linux, you can also use host networking for the container:

```bash
DOCKER_NETWORK=host ./scripts/run-e2e-docker.sh
```

### Customize which specs run

Override the spec list (comma-separated) if you need a different order or a subset:

```bash
CYPRESS_SPECS=cypress/e2e/deployments.cy.ts,cypress/e2e/ensembles.cy.ts \\
./scripts/run-e2e-docker.sh
```

### Notes

- The join-organization spec uses Mailhog. Configure `CYPRESS_MAILHOG_BASE_URL`, `CYPRESS_MAIL_INBOX_DOMAIN`, and `CYPRESS_MAIL_SUBJECT_FRAGMENT` if you use a different setup.
- Override the join-org target with `CYPRESS_NUTEST_ORG_DID` and `CYPRESS_NUTEST_ROLE` if needed.
- For test-only orgs, place `known_organizations.e2e.json` next to the main known-orgs file on the appliance; it is merged at load time.
- The script uses `cypress/included:13.15.2` and installs dependencies inside the container. It keeps `node_modules` and pnpm store in Docker volumes so the repo stays clean.
