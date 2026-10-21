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
layers/shared/app/           # API transport, contracts, feedback and fee UI
layers/catalog/app/          # Services, version definitions, validation and quotes
layers/applications/app/     # Application lookup, patch, submit and audit history
server/api/backend/          # Same-origin FastAPI proxy
```

Local Nuxt layers are discovered automatically. Each feature depends only on shared; the root coordinates feature navigation. Project components and composables use explicit `#layers/<feature>/app/...` imports. ESLint enforces feature boundaries and rejects root aliases and parent-relative imports inside layers. Nuxt/Vue helpers and Nuxt UI components remain available through framework/module imports.

This follows the [Nuxt Layers modular monolith guide](https://alexop.dev/posts/nuxt-layers-modular-monolith/), adapted to Nuxt 4's `app/` layout. The ESLint plugin has a small compatibility adapter for the `getFilename` API removed in ESLint 10.

To add a feature, create `layers/<feature>/nuxt.config.ts`, put its UI under `app/`, register its allowed dependencies in `eslint.config.mjs`, and add a Tailwind `@source` in the shared stylesheet. Restart the dev server after changing layer configuration.

## Verification and production

```bash
pnpm test
pnpm lint
pnpm typecheck
pnpm build
pnpm preview
```

Tests exercise API envelopes, structured error handling, JSON parsing, idempotency header forwarding and proxy request forwarding. Live persistence workflows require the backend and PostgreSQL to be running. Deploy the Nuxt server output (`.output/server/index.mjs`); the API proxy requires a server runtime.
