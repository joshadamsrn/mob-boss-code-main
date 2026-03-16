# feature_hex_request_dto_and_composition

## Goal
Define the request DTO anti-corruption boundary and symmetric container composition rules used by all Django apps.

## Scope
- All Django views in `project/mobboss_apps/*/views.py` and `project/mobboss_apps/*/v1_views.py`.
- All app request DTO modules in `ports/internal_requests_dto.py`.
- Composition root in `project/mobboss_apps/mobboss/composition.py`.

## Rules
- Every app that accepts HTTP input must define request DTOs in `ports/internal_requests_dto.py`.
- Request DTOs must define explicit typed fields for accepted inputs.
- Request DTOs must parse via `from_payload(payload: dict)`.
- Request DTOs must validate and normalize inside `from_payload`.
- DTOs must not accept the Django `request` object directly.
- Views follow a fixed 4-step flow:
1. Extract body/query/path data into a plain payload dictionary.
2. Parse payload immediately into a request DTO.
3. Execute inbound/domain behavior using typed DTO fields.
4. Map result to Django `HttpResponse`/`JsonResponse`.
- Composition supports only `default` and `unittest` modes.
- `compose_default_container()` and `compose_unittest_container()` remain symmetrical in section order.
- Composition imports stay at file scope (no local imports inside compose functions).
- Credentials are provided by credentials outbound port DTO getters.
- Database name/url comes from credentials DTOs.
- Project/media constants come from project settings outbound port DTO getters.
- Project settings constants are defined in memory adapter implementations, not preloaded in composition.
- Cross-app imports and URL include module strings use `project.mobboss_apps...` fully qualified paths.

## Invariants
- Django views do not pass untyped payloads beyond DTO parsing boundaries.
- Validation logic for HTTP inputs is not duplicated across views.
- Container composition does not embed environment constants that belong in settings adapters.

## Inputs
- HTTP request body/query/path values.
- Container mode (`default` or `unittest`).

## Outputs
- Typed DTO instances used by inbound ports and services.
- Fully wired container objects with credentials/settings/ports and services.

## Edge Cases
- Missing required fields raise DTO validation errors from `from_payload`.
- Invalid body JSON is converted to payload parse errors before domain execution.
- Unsupported container mode raises a composition error.

## Test Notes
- Per app, keep tests only under:
- `tests/domain/`
- `tests/rest/`
- `tests/adapters/`
- `rest` tests assert request extraction and DTO parsing behavior.
- `domain` tests stay free of Django framework concerns.
- `adapters` tests validate port implementation behavior.

## Open Items
- None.
