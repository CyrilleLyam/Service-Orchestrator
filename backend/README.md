# ServiceOrchestrator backend

A schema-driven backend for defining, publishing, validating and processing configurable services
without writing new backend code for each one. A service is **configuration data**: a JSON Schema
for its payload, declarative rules, fees and UI hints. New services and new versions go live through
the API; nothing is redeployed.

This is the proof of concept described in the project brief (backend milestones M1–M5; the optional
React/Next.js renderer is not built yet).

- **Architecture:** modular monolith, pragmatic DDD, Clean Architecture
- **Stack:** Python 3.12, FastAPI, PostgreSQL (JSONB), SQLAlchemy 2, Alembic, uv
- **Rules:** JSON Schema 2020-12 and a restricted JSON Logic evaluator

## Quick start

Run these from `backend/` (Docker Compose finds `compose.yaml` in the repository root).

```bash
docker compose up -d db                 # PostgreSQL on localhost:5433
uv sync                                 # install dependencies
uv run alembic upgrade head             # create the schema
uv run service-orchestrator-seed        # apply seeds/services.sql: three published services
uv run uvicorn --factory service_orchestrator.main:create_app --reload --no-access-log
```

Open http://localhost:8000/docs for the interactive API. To run everything in containers instead:
`docker compose up --build` from the repository root (the API container migrates on start), then seed with
`docker compose exec api service-orchestrator-seed`.

### Seed data

[seeds/services.sql](seeds/services.sql) inserts the three example services (Parcel Delivery,
Conference Registration, Equipment Rental), each with a published version 1. It is idempotent:
services that already exist are left untouched. Apply it with the seed command above, or directly:

```bash
docker compose exec -T db psql -U orchestrator -d service_orchestrator < seeds/services.sql
```

The same definitions are in [examples/](examples) as API payloads; a test keeps the two in sync.

Configuration is read from environment variables or `.env` (see [.env.example](.env.example)).
The database is published on port 5433 so it does not clash with a local PostgreSQL; set
`DB_PORT` to change it.

## Walkthrough

```bash
# 1. Define a service and its first draft, then publish it
curl -X POST localhost:8000/v1/services -H 'Content-Type: application/json' \
  -d '{"code": "delivery", "name": "Parcel Delivery"}'
curl -X POST localhost:8000/v1/services/delivery/versions -H 'Content-Type: application/json' \
  -d "{\"definition\": $(jq .definition examples/delivery_service.json)}"
curl -X POST localhost:8000/v1/services/delivery/versions/1/publish

# 2. A client reads the published definition (schema, rules, fees, uiSchema) and renders a form
curl localhost:8000/v1/services/delivery

# 3. Check or price a payload without saving anything
curl -X POST localhost:8000/v1/services/delivery/validate -H 'Content-Type: application/json' \
  -d '{"data": {"distanceKm": 80, "weightKg": 2, "express": true}}'
curl -X POST localhost:8000/v1/services/delivery/quote -H 'Content-Type: application/json' \
  -d '{"data": {"distanceKm": 12, "weightKg": 2, "express": true}}'

# 4. Create a draft application (pinned to version 1), save data in steps, submit
curl -X POST localhost:8000/v1/applications -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: order-1001' -d '{"serviceCode": "delivery", "data": {"distanceKm": 12}}'
curl -X PATCH localhost:8000/v1/applications/<id> -H 'Content-Type: application/merge-patch+json' \
  -d '{"data": {"weightKg": 2, "express": true}}'
curl -X POST localhost:8000/v1/applications/<id>/submit
curl localhost:8000/v1/applications/<id>          # includes fee snapshot and audit events

# 5. Dynamic pricing: Equipment Rental charges per day, a tiered service fee and 10% insurance
curl -X POST localhost:8000/v1/services/equipment-rental/quote -H 'Content-Type: application/json' \
  -d '{"data": {"equipmentCategory": "camera", "durationDays": 10, "startDate": "2026-11-02", "insurance": true}}'

# 6. Ship version 2: start from the current definition, edit, publish
curl -X POST localhost:8000/v1/services/delivery/versions -H 'Content-Type: application/json' -d '{}'
curl -X PUT  localhost:8000/v1/services/delivery/versions/2 -H 'Content-Type: application/json' \
  -d '{"definition": { ... }}'
curl -X POST localhost:8000/v1/services/delivery/versions/2/publish
# New applications pin version 2; existing ones keep validating and pricing with version 1.
```

## HTTP API

Every response, success or failure, has the same envelope:

```jsonc
{"error": false, "data": { /* the resource */ }, "pagination": null}
{"error": false, "data": [ /* a page */ ], "pagination": {"page": 1, "pageSize": 20, "total": 3, "totalPages": 1}}
{"error": true,  "data": {"code": "...", "message": "...", "errors": [ /* field errors */ ], "requestId": "..."}, "pagination": null}
```

`pagination` is filled in for list endpoints, which accept `?page=` (from 1) and `?pageSize=`
(1–100, default 20). Every response carries an `X-Request-ID` header; send your own to trace a
request across systems, or one is generated.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/v1/services` | Create service |
| GET | `/v1/services` | List services (paged) |
| GET | `/v1/services/{code}` | Service metadata, version list and the published definition |
| GET | `/v1/services/{code}/versions` | List versions (paged) *(addition)* |
| GET | `/v1/services/{code}/versions/{version}` | Read one version, e.g. the one an application is pinned to *(addition)* |
| POST | `/v1/services/{code}/versions` | Create draft (omit `definition` to copy the current published one) |
| PUT | `/v1/services/{code}/versions/{version}` | Edit draft definition |
| POST | `/v1/services/{code}/versions/{version}/publish` | Check and publish an immutable version |
| POST | `/v1/services/{code}/validate` | Validate a payload against the current version (always 200; see `valid`) |
| POST | `/v1/services/{code}/quote` | Informational fee quote (422 if the payload is invalid) |
| GET | `/v1/applications` | Paginated summaries, newest first; optional `serviceCode` and `status=draft\|submitted` filters |
| POST | `/v1/applications` | Create a draft pinned to the current version; honours `Idempotency-Key` |
| PATCH | `/v1/applications/{id}` | JSON Merge Patch of the draft: `{"data": {...}}`, `null` removes a field |
| POST | `/v1/applications/{id}/submit` | Validate, price, submit |
| GET | `/v1/applications/{id}` | Application, fee snapshot and audit events |

Field errors use JSON Pointers into the document that was checked:

```json
{
  "error": true,
  "data": {
    "code": "submission_rejected",
    "message": "The application failed validation and was not submitted",
    "errors": [
      {"path": "/distanceKm", "code": "assertion_failed",
       "message": "Express delivery is only available up to 50 km.", "ruleId": "express-max-distance"}
    ],
    "requestId": "019a0f6e5c2b7a41b93be1a5c2d0f7aa"
  },
  "pagination": null
}
```

| Status | When |
|---|---|
| 404 | unknown service, version, application or route |
| 409 | state conflicts: duplicate code, editing a published version, second draft, changing a submitted application, service not yet published, lost race |
| 413 | request body over `MAX_REQUEST_BYTES` |
| 422 | malformed request, invalid definition on publish, invalid payload on quote/submit |
| 500 | unexpected error; the body has the `requestId` to find it in the logs |

## Definition contract

A version stores one JSON document. See [examples/](examples) for three complete services:
parcel delivery, conference registration and equipment rental.

```jsonc
{
  "dataSchema": { /* JSON Schema 2020-12, root "type": "object" */ },
  "rules": [
    {"id": "company-required", "type": "require",
     "when": {"==": [{"var": "attendeeType"}, "corporate"]}, "fields": ["companyName"]},
    {"id": "company-only-for-corporate", "type": "visible",
     "when": {"==": [{"var": "attendeeType"}, "corporate"]}, "fields": ["companyName"]},
    {"id": "express-max-distance", "type": "assert",
     "when": {"==": [{"var": "express"}, true]}, "assert": {"<=": [{"var": "distanceKm"}, 50]},
     "path": "/distanceKm", "message": {"en": "Express delivery is only available up to 50 km."}}
  ],
  "fees": [
    {"code": "BASE", "amount": 5000, "currency": "KHR"},
    {"code": "EXPRESS", "amount": 3000, "currency": "KHR", "when": {"==": [{"var": "express"}, true]}}
  ],
  "uiSchema": {
    "steps": [{"id": "parcel", "title": {"en": "Parcel"}, "fields": ["distanceKm", "weightKg", "express"]}],
    "fields": {"express": {"widget": "switch"}}
  }
}
```

**Rules**

| Type | Meaning |
|---|---|
| `require` | When `when` holds (or always, if omitted), each field must be present and non-empty |
| `visible` | When `when` does not hold, the fields must be absent; drives conditional visibility in the UI |
| `assert` | When `when` holds, `assert` must be truthy; otherwise an error at `path` with `message` |

`require`/`visible` errors are reported together with JSON Schema errors. `assert` rules assume
well-typed data, so they run once the schema passes.

**Rule language.** A restricted JSON Logic: `var` (dot paths such as `contact.email`), `if`, `and`,
`or`, `!`, `!!`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `+`, `-`, `*`, `/`, `%`, `min`, `max`, `in`.
Unlike jsonlogic.js, equality is strict (`1` never equals `true` or `"1"`), ordering comparisons
between mismatched types are false, and arithmetic on non-numbers is an error.

**Fees.** Every fee has a `code`, a `currency` (one per definition), an optional `label`, an
optional `when` condition, and exactly one way to price it:

| Pricing | Example | Amount |
|---|---|---|
| `amount` | `"amount": 5000` | fixed |
| `perUnit` | `"perUnit": {"unitAmount": 300, "quantity": {"var": "distanceKm"}, "roundQuantity": "up"}` | quantity × unit amount; `roundQuantity` charges per started unit |
| `tiers` | `"tiers": {"basis": {"var": "weightKg"}, "brackets": [{"upTo": 2, "amount": 0}, {"upTo": 10, "amount": 2000}, {"unitAmount": 300}]}` | first bracket whose `upTo` ≥ basis; a bracket has a flat `amount` or a `unitAmount` × basis; the last bracket has no `upTo` |
| `formula` | `"formula": {"*": [0.1, {"var": "durationDays"}, 60000]}` | any rule expression that yields a number |

Computed fees (`perUnit`, `tiers`, `formula`) also take `rounding` (`nearest` by default, `up`,
`down`), `minAmount` and `maxAmount`. Amounts are integers in minor units and must end up between
0 and 10¹². Arithmetic is decimal, so 0.1 × 3 × 40000 is 12000, not 12000.000000000002 rounded
up. Fees are always calculated on the server from validated data, and each line in the snapshot
records the `quantity` and `unitAmount` it used. A fee that cannot be calculated (for example a
`quantity` that is null) fails the submission with `fee_calculation_failed`; use a `var` default
such as `{"var": ["extraBags", 0]}` for optional inputs.

**Publication checks** (`POST .../publish` → 422 with paths into the definition):

- size and nesting limits, then the platform meta-schema
- `dataSchema` is valid 2020-12 and uses only supported keywords; `$ref` must be local and resolve;
  `format` limited to `date`, `date-time`, `time`, `email`, `uuid`
- regex `pattern`s are length-limited and screened for catastrophic backtracking
  (nested unbounded quantifiers, backreferences, lookaround)
- rules use supported operators with the right arity, reference fields that exist in
  `dataSchema` (following `$ref`, `allOf`/`anyOf`/`oneOf`, `then`/`else`), and stay within depth
  and node limits; rule ids are unique
- fee codes unique; exactly one pricing method; amounts non-negative integers; brackets
  ascending and open-ended; `minAmount` ≤ `maxAmount`; fee expressions checked like rules; one currency
- every UI field reference exists

Remote references are never fetched, and nothing in a definition is executed as code.

## Architecture

```
Presentation   FastAPI routers, request/response DTOs, error mapping
     │
Application    use cases, ports (repositories, unit of work, schema/rule engines, catalog gateway)
     │
Domain         Service / ServiceVersion, Application, Money, fee policy, invariants
     ▲
Infrastructure SQLAlchemy repositories, jsonschema adapter, JSON Logic adapter
```

```
src/service_orchestrator/
├── main.py, config.py, seed.py
├── bootstrap/dependencies.py      composition root
├── service_catalog/               Service aggregate, drafts, publishing, definition checks
├── application_processing/        Application aggregate, drafts, submission, audit events
├── fee_policy/calculator.py       pure fee policy
└── shared/                        Money, field errors, JSON limits, engine adapters, HTTP plumbing
```

- **Bounded contexts.** Application Processing reaches the catalog only through its
  `ServiceCatalogGateway` port; the adapter calls the catalog's public `PublishedVersions` query.
  `tests/unit/test_architecture.py` fails if a domain or application module imports a framework,
  infrastructure, or (for Application Processing) the catalog directly.
- **Invariants in two places.** The aggregates enforce them, and the database backs them up:
  unique `(service_id, version)`, at most one draft per service, the current-version pointer must
  belong to the same service, triggers that reject any change to published versions or submitted
  applications or to an application's pinned version, and an append-only `application_events` table.
- **Transactions.** Each use case is one unit of work. Publishing, draft creation and submission
  lock the aggregate row (`SELECT … FOR UPDATE`), so racing requests resolve to one winner and
  clean 409s; unique-constraint races surface as `concurrent_modification` (409).
- **Pinning.** An application stores its `service_version_id` and is always validated and priced
  with that version, even after newer versions are published.
- **Identifiers.** Services, versions, applications and generated request IDs are UUIDv7
  (RFC 9562): unique, and sortable by creation time.

## Logging

Logs go to stderr. Every line carries the request ID, so one request can be followed from the
HTTP layer through the use case:

```
2026-10-21 14:03:01,123 INFO    service_orchestrator.application_processing.application.commands.submit_application [019a0f6e5c2b7a41b93be1a5c2d0f7aa] application submitted application_id=019a0f6e-... service=delivery version=1 total=8000 currency=KHR
2026-10-21 14:03:01,124 INFO    service_orchestrator.shared.presentation.middleware [019a0f6e5c2b7a41b93be1a5c2d0f7aa] request completed method=POST path=/v1/applications/019a0f6e-.../submit status=200 duration_ms=18.4
```

- one `request completed` line per request (INFO, WARNING for 4xx, ERROR for 5xx)
- `request rejected` with the error code and failing paths, never the submitted values
- business events: service created, draft created/updated, version published, application
  created/updated/submitted, submission rejected
- `unhandled error` with the full traceback; the client gets a 500 with the same `requestId`

| Setting | Default | |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` adds the evaluated errors and fee lines for each payload |
| `LOG_FORMAT` | `text` | `json` for one JSON object per line (log aggregators) |
| `LOG_SQL` | `false` | log every SQL statement |

Run uvicorn with `--no-access-log`; the request lines above replace its access log.

## Development

```bash
docker compose up -d db
uv run pytest                    # unit + integration (integration skips if PostgreSQL is down)
uv run pytest tests/unit         # no database needed
uv run ruff check . && uv run ruff format --check .
uv run alembic check             # ORM models and migrations agree
```

Integration tests use `TEST_DATABASE_URL` (default `…@localhost:5433/service_orchestrator_test`),
create that database if needed, migrate it down and up, and truncate tables between tests. They
cover repositories, the database guards, concurrent publish/draft/create/submit races, and the full
HTTP lifecycle for two unrelated services, including version pinning across a new release,
plus dynamic pricing, pagination, the response envelope and logging.

## Not in this POC

Authentication and authorization, rate limiting, metrics and tracing, approval workflows, payment
collection, file storage, remote validators and webhooks. Patterns run on Python's `re`, which is
close to but not identical to ECMA-262 regex. A production deployment needs a security review.
