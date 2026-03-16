# feature_game_flow

## Goal
Define authoritative round flow and boundary behavior.

## Scope
- In scope:
  - phase transitions for `information`, `accused_selection`, `trial_voting`, `boundary_resolution`, `ended`
  - death report entry into accused-selection chain
  - no-selection branch into boundary resolution
- Out of scope:
  - full jury voting implementation detail
  - detailed economy transfer bookkeeping

## Rules
- Gameplay is continuous.
- Round structure: `information` -> (`accused_selection` -> `trial_voting` if triggered) -> `boundary_resolution` -> next round `information`.
- One murder can trigger at most one trial.
- `report_death` is moderator-gated and optimistic-concurrency guarded (`expected_version`).
- If a trial is already pending, additional death reports are rejected.
- Win checks occur at boundaries only.
- Merchant boundary precedence: if a Merchant meets goal at a boundary, Merchant win resolves first and is single-winner for that boundary.
- Police accused-selection chain: 15 seconds per eligible Police responder in rank order.
- `report_death` initializes first accused-selection deadline at `now + 15s` (first eligible police by rank).
- Timeout advancement consumes one responder at a time and sets next `+15s` deadline.
- If no Police responder selects an accused: no trial, `no_conviction`, phase moves to `boundary_resolution`.
- Conflict handling for stale client mutations is strict-manual for now (no auto-retry/rebase flow).

## Invariants
- No cross-room state interactions.
- No hidden-role leakage in public notifications.
- Role visibility is projection-filtered: moderators see full participant role data; non-moderators see role details for self only.
- Boundary checks are not evaluated inline during death-report or timeout-advance mutations.

## Open Items
- Multi-death report serialization policy before poll sync.
