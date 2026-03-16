# Project Conventions

This file defines the structural and architectural conventions for this repository.

## Core Principles

- Use a modular monolith with hexagonal architecture (ports and adapters).
- Keep Django framework concerns at the edge (views/adapters only).
- Keep game logic authoritative in code, not markdown.
- Keep OpenAPI as the source of API truth (spec-first), not generated from code.
- Prefer deterministic, explicit behavior over implicit framework magic.

## Repository Layout

- `project/mobboss_apps/` is the Django workspace root.
- `project/mobboss_apps/manage.py` is the Django entrypoint.
- `project/mobboss_apps/mobboss/` is the central Django project package.
- `project/mobboss_apps/mobboss/src/weights.py` is the authoritative default weights module.
- `documentation/discussion/` contains evolving notes, decisions, and open discussion.
- `documentation/features/` contains formal feature behavior specs.

## Django App Layout

Each Django app should follow this structure:

- `ports/inbound.py`
- `ports/outbound.py`
- `ports/internal.py`
- `ports/internal_requests_dto.py`
- `adapters/inbound/`
- `adapters/outbound/`
- `adapters/internal/`
- `src/`
- `views.py`
- `urls.py`
- `v1_views.py`
- `v1_urls.py`

## App Boundaries

Use these boundaries as the authoritative ownership map for this repository.

- `iam`: authentication and account identity only (`UserAccount` concerns).
- `rooms`: pre-game lobby state, room membership, readiness, moderator assignment, and room-to-game launch orchestration.
- `gameplay`: game-session lifecycle, participants, role assignment, succession, phase/round progression, and win-condition evaluation.
- `economy`: item catalog, approved item classifications, price changes, inventory, transfers, and ledger/economy invariants.
- `notebook`: private per-participant suspect entries and notes (owner-scoped visibility).
- `web`: HTML surface only (templates/views as edge adapters).
- `operations`: service operations endpoints (health, metrics, diagnostics).
- `mobboss`: Django project shell and cross-app composition/wiring.

Boundary rules:

- `iam` must not own room/game/economy state.
- `rooms` owns lobby/launch concerns, but not in-round gameplay resolution.
- `gameplay` owns authoritative in-game role and participant state.
- `economy` owns money/item transfer logic and classification policy.
- `notebook` data is private to the owner participant by default.
- `web` and `operations` must call inbound ports and must not contain domain logic.
- `moderation` and `events` are currently present as scaffold apps; prefer implementing moderator capabilities under `rooms`/`gameplay` and event/audit behavior within owning domains until a dedicated cross-cutting design is approved.

## Ports and DTOs

- `ports/inbound.py`: use case entry contracts (how the system is stimulated).
- `ports/outbound.py`: contracts for external resources (db, services, infra).
- `ports/internal.py`: internal DTO/data contracts only.
- `ports/internal_requests_dto.py`: request DTO contracts for Django request payload/query/path extraction.
- Request DTO parsing must use `from_payload(payload: dict)` methods.
- DTOs may validate and normalize data.
- Request DTO validation and normalization must happen inside `from_payload`.
- Request DTOs must define explicit typed fields and shape; do not pass through a generic JSON blob field as the primary contract.
- DTOs must not perform I/O, repository calls, or side effects.

## View Request Flow

Use the same flow in every Django view (HTML and JSON variants):

1. Extract framework input into plain payload data (`request.body`, `request.GET`, `request.POST`, path params).
2. Parse immediately into a request DTO via `XRequestDTO.from_payload(payload)` (never pass the Django request object).
3. Resolve the container/inbound port and execute use-case logic with typed values from the DTO.
4. Map the result into the Django response shape.

## API and Versioning

- Version JSON APIs from day one.
- Use app-local `v1_urls.py` and `v1_views.py` for JSON endpoints.
- Use app-local `urls.py` and `views.py` for HTML endpoints.
- OpenAPI lives as a hand-authored contract and is authoritative.
- JSON API error responses must use RFC 7807 Problem Details (`application/problem+json`).
- Use the shared `mobboss.decorators.problem_details` decorator for JSON endpoint exception handling.
- Raise shared API exceptions from `mobboss.exceptions` when a non-default status/type is required.

## Testing Expectations

- Unit tests must not require database access or network/API access.
- Domain and use-case tests should run on pure Python with fakes/stubs.
- Integration tests may cover Django ORM, routing, and database behavior.
- Organize tests per app under only these folders:
- `tests/domain/` for domain logic and use-case behavior.
- `tests/rest/` for Django view/request-response behavior.
- `tests/adapters/` for adapter implementations.

## Composition and Wiring

- `mobboss/composition.py` is the composition root entrypoint.
- Supported container modes are `default` and `unittest`.
- Keep one mode branch at the top-level selector (`get_container`/cached resolver) and compose directly in `compose_default_container()` and `compose_unittest_container()`.
- Keep imports at file scope; do not use function-local imports in composition.
- Keep the two compose functions symmetrical with deliberate single-line section separators.
- Resolve credentials and project settings ports near the top of each compose function.
- Database name/url must come from credentials DTOs provided by the credentials outbound port.
- Project/media behavior constants (for example media root/url and room tunables) must be defined in project settings adapters, not preloaded in composition.

## Import Conventions

- For app-to-app imports, use fully-qualified imports rooted at `project.mobboss_apps`.
- For URL include module strings, use fully-qualified module paths rooted at `project.mobboss_apps`.

## Multi-Tenancy and Data Scope

- Game data is scoped by room/game boundary.
- Query patterns must enforce room scoping to prevent cross-room leakage.
- Prefer indexes and constraints that include room/game scope fields.

## Operations Surface

- Keep an `operations` app for server-level endpoints and controls.
- Current endpoints:
- `/operations/`
- `/operations/healthcheck`
- `/operations/metrics`
- Additional aliases (for example `/healthz`, `/metrics`) may be added later.

## Naming Conventions

- Canonical factions: `Police`, `Mob`, `Merchant`.
- Keep terms consistent across DTOs, APIs, docs, and UI.
- Avoid deprecated terminology in new code and contracts.

## Documentation Usage

- `documentation/features/*.md` defines expected behavior and test intent.
- `documentation/discussion/*` is design context and decision history.
- Runtime logic must be implemented in Python modules, not parsed from docs.
