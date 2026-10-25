# Service Orchestrator client

Nuxt 4 / Nuxt UI workspace for the FastAPI backend in `../backend`.

## Run locally

Start and seed the backend using `../backend/README.md`, then:

```bash
pnpm install
cp .env.example .env
pnpm dev
```

Open http://localhost:3000. The shared API helper uses an Axios instance per setup with a 15-second timeout, request-scoped SSR headers and an absolute same-origin base URL. The Nuxt server proxies `/api/backend/**` to `NUXT_BACKEND_URL` (default `http://localhost:8000`). The backend address is server-only; browser requests use the Nuxt origin, so no backend CORS changes are needed. Use an origin reachable from the Nuxt server when running containers.

## Workflows

- **Service catalog (`/`):** paginated services, publication status, service creation.
- **Service workspace (`/services/:code`):** inspect versions, create/edit draft definitions, publish, validate payloads, request fee quotes and create application drafts. Definitions and payloads use JSON object editors to support arbitrary backend schemas. Server field errors include JSON Pointer paths and request IDs.
- **Applications (`/applications?id=:uuid`):** load by ID, inspect saved data, apply JSON Merge Patch updates, submit, review immutable fee snapshots and audit history. The backend has no application-list endpoint; keep the application URL to resume later.

Validation and quotes target the current published service version. Applications are pinned at creation and the backend validates/prices them against that pinned version on submission. Application creation retains an idempotency key for retries of the same payload. Published versions and submitted applications are read-only. Fee amounts are displayed explicitly as raw minor units, preserving the backend contract.

## Architecture

```text
app/                         # Shell, routes, cross-feature navigation
app/features/catalog/        # Services, version definitions, validation and quotes
app/features/applications/   # Application lookup, patch, submit and audit history
app/shared/                  # API transport, contracts, feedback and fee UI
app/assets/css/              # Global styles
server/api/backend/          # Same-origin FastAPI proxy
```

Features live under `app/features/` and depend on `app/shared/`. Pages coordinate routing and cross-feature navigation. Components and composables use explicit `~/features/...` and `~/shared/...` imports. Nuxt/Vue helpers and Nuxt UI components remain available through framework/module imports.

To add a feature, create `app/features/<feature>/`, keep its UI and supporting code together, and add route wrappers under `app/pages/`. Shared code must not depend on features. ESLint enforces these boundaries. Global styles scan the app directory for Tailwind classes.

## Verification and production

```bash
pnpm test
pnpm lint
pnpm typecheck
pnpm build
pnpm preview
```

Tests exercise API envelopes, structured error handling, JSON parsing, idempotency header forwarding and proxy request forwarding. Live persistence workflows require the backend and PostgreSQL to be running. Deploy the Nuxt server output (`.output/server/index.mjs`); the API proxy requires a server runtime.
