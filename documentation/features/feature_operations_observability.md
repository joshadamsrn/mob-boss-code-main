# feature_operations_observability

## Goal
Define baseline operational endpoints and server observability surface.

## Rules
- Operations app exposes:
- `/operations/` HTML operations surface.
- `/operations/healthcheck` machine-readable health endpoint.
- `/operations/metrics` metrics endpoint for scraping.
- Versioned JSON APIs should start at v1 from first release.

## Invariants
- Operations endpoints must not expose secret game state by default.
- Health endpoint should not depend on full game query execution.

## Open Items
- Alias endpoints (`/healthz`, `/metrics`) adoption timing.
- Authentication policy for operations UI/actions.
