# App Boundaries

This file defines ownership boundaries between Django apps so ports and DTOs stay coherent as implementation grows.

## Authoritative Ownership

- `iam`
  - Owns auth/account identity only.
  - Typical concepts: `UserAccount`, login/session lifecycle.
  - Explicitly does not own room/game/economy state.

- `rooms`
  - Owns pre-game room lifecycle.
  - Typical concepts: `GameRoom`, room membership, readiness, moderator assignment.
  - Owns room-to-game launch orchestration.

- `gameplay`
  - Owns in-game authoritative session state.
  - Typical concepts: `GameSession`, `Participant`, role/rank assignment, succession, phase/round progression.
  - Owns win-condition checks and in-round state transitions.

- `economy`
  - Owns game-economy policy and item catalog.
  - Typical concepts: item classification policy, catalog entries, prices, inventory, transfers, ledger.
  - Approved item classifications are code-defined enums, not user-editable runtime values.

- `notebook`
  - Owns private per-participant intelligence notes.
  - Typical concepts: suspect entry by `(owner_participant_id, target_participant_id)` with presumed faction/role, confidence, and note text.
  - One suspect entry per owner-target pair (upsert semantics).

- `web`
  - Owns HTML/UI edge adapters only.
  - Uses inbound ports; does not contain domain logic.

- `operations`
  - Owns runtime health/metrics/ops surfaces.
  - Must avoid leaking secret game state by default.

- `mobboss`
  - Project shell and composition root/wiring.

## Transitional Apps

- `moderation` and `events` currently exist as scaffolds.
- Until a cross-cutting design is approved, prefer:
  - moderator capability implementation in `rooms` and `gameplay`
  - event/audit behavior in the domain app that owns the behavior

## Dependency Direction

- Views/adapters call inbound ports.
- Inbound use cases depend on internal DTOs and outbound ports.
- Outbound adapters implement outbound ports.
- Domain apps must not reach across boundaries by importing other apps' adapters.

## Open Items

- Decide whether `events` becomes a dedicated event-stream/audit app or remains distributed by domain ownership.
- Decide whether moderator tooling remains split by use case (`rooms`/`gameplay`/`economy`) or is later promoted to a dedicated cross-cutting app.
