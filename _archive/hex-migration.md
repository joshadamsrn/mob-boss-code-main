# Hex Migration Checklist

Goal: enforce a strict composition root where resource access happens via ports/adapters wired by `composition.py`.

## Audit Scope

- Resource acquisition: DB connections, filesystem I/O, media/image handling, auth/session operations, runtime config reads.
- Conformance rule: Django views should resolve dependencies from `get_container()`, then use ports/values from the container.

## Hunt Findings

1. `rooms/views.py` and `rooms/v1_views.py` previously performed direct filesystem and image processing for catalog uploads.
2. `rooms/views.py` previously read several runtime settings directly for launch/polling behavior.
3. `iam/views.py` previously performed direct auth/session operations (`login`, `logout`, auth forms).
4. `economy/src/catalog_defaults.py` previously loaded defaults JSON directly from disk in `src/` instead of via an outbound adapter.
5. Project root URL setup (`mobboss/urls.py`) still directly branches on Django settings for static media mounting.

## Checklist

- [x] Add room media outbound port and adapters:
  - [x] `RoomItemMediaOutboundPort` in `rooms/ports/outbound.py`
  - [x] `rooms/adapters/outbound/media/memory_impl.py`
  - [x] `rooms/adapters/outbound/media/filesystem_impl.py`
- [x] Wire room media outbound port through `mobboss/composition.py`
- [x] Refactor `rooms/views.py` to use container media port (remove direct media/PIL helpers)
- [x] Refactor `rooms/v1_views.py` to use container media port (remove direct media writes)
- [x] Move room launch/polling runtime settings into container-composed config values
- [x] Update rooms HTML views to consume room config from container instead of direct `settings` reads
- [x] Introduce `*_impl` naming for room outbound adapters used by composition:
  - [x] `rooms/adapters/outbound/memory_impl.py`
  - [x] `rooms/adapters/outbound/sqlite_impl.py`
- [x] Migrate IAM auth/session flow to composed ports/adapters (inbound service + outbound auth/session gateway)
- [x] Migrate economy catalog defaults file access behind outbound adapter (`memory_impl` + `json_file_impl`)
- [x] Compose economy catalog defaults outbound adapter in `mobboss/composition.py`
- [ ] Decide whether `mobboss/urls.py` static-media branching should remain framework-level or move behind bootstrap composition
- [ ] Extend composition to explicit ports for other domains as app logic is implemented (economy/gameplay/notebook/events/moderation/operations/web)

## Validation

- [x] Composition tests updated for new room media port and `*_impl` repository classes.
- [x] Full test discovery with Django settings passes in current tree.
- [x] Sweep confirms every non-test Django `*views.py` references `get_container()`.
- [x] Sweep confirms file I/O (`open(...)`) remains confined to outbound adapters.
