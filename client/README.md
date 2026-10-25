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
- **Service workspace (`/services/:code`):** inspect versions, create/edit draft definitions, publish, validate payloads, request fee quotes and create application drafts. Definitions use a JSON editor. Application data uses schema-driven inputs and sections from `uiSchema`, with a JSON editor available for advanced schemas. Server field errors include JSON Pointer paths and request IDs.
- **Applications (`/applications`):** browse a paginated list, filter by exact service code and draft/submitted status, open an application or load it by ID, edit answers with the pinned definition, preview validation and fees for unsaved changes, save drafts, submit, and review immutable fee snapshots and audit history. Filters and pagination stay in the URL when opening an application and returning to the list. Lists show summaries newest first, with each application’s pinned service version.

Catalog validation and quotes target the current published service version. Draft validation and quotes use the application’s pinned version and accept replacement data without saving it. Applications are pinned at creation and the backend validates/prices them against that pinned version on submission. Application creation retains an idempotency key for retries of the same payload. Published versions and submitted applications are read-only. Fee amounts are displayed explicitly as raw minor units, preserving the backend contract.

## Application forms

The renderer supports text, email and date inputs, numbers and integers, booleans, scalar enums, enum arrays, and nested objects with declared properties (`additionalProperties: false`). `uiSchema.steps` orders form sections; radio, switch, textarea and checkbox-group hints are supported. Unlisted fields appear in an additional section.

Visibility and conditional required markers support `var`, strict equality, comparisons, `and`, `or`, `!`, `!!`, `in` and `if`. Changing an answer removes fields that become hidden, including saved values when the draft is next saved. Server validation and fee calculation remain authoritative. Drafts can be saved with partial answers.

Schemas with references, composition, nullable/complex fields, arbitrary properties or unsupported UI conditions use the JSON editor automatically. Switching editors preserves the data. Backend field errors appear beside supported inputs and in the feedback summary.

Draft editing uses the complete data object and computes a JSON Merge Patch on save, including deletions and nested changes. Newly assigning `null` to an object property cannot be represented by JSON Merge Patch and is rejected with an explanation; remove the property to delete its saved value. Submit is enabled after changes are saved or discarded. Submitted applications stay read-only.

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

Tests exercise API envelopes, structured error handling, JSON parsing, idempotency header forwarding, proxy request forwarding, schema layouts, conditional fields, nested edits, merge patches and rendered inputs for the three seeded services. Live persistence workflows require the backend and PostgreSQL to be running. Deploy the Nuxt server output (`.output/server/index.mjs`); the API proxy requires a server runtime.
