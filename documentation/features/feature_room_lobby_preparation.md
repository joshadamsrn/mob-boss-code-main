# feature_room_lobby_preparation

## Goal
Define authoritative pre-game lobby behavior so room setup is deterministic, testable, and ready for launch into gameplay.

## Scope
- Room lifecycle before game start.
- Membership and readiness behavior.
- Moderator authority and permissions.
- Pre-game role assignment/shuffle.
- Pre-game starting balances and room item catalog setup.
- Launch gating rules.
- Perspective-specific visibility/action matrix (see `feature_room_lobby_perspectives.md`).

## Out Of Scope
- In-round gameplay resolution (murders, trials, voting, win checks).
- Chat/social systems.
- Post-launch gameplay state transitions.

## Authoritative Defaults (v1)
- `moderator_leave_policy = close_room`
- `launch_requires_all_ready = true`
- `kick_enabled = true`
- `ban_enabled = true`
- `ban_scope = room_scoped_until_room_end`
- `room_capacity_joined = 25`
- `waitlist_enabled = true`
- `waitlist_order = fifo`
- `readiness_reset_policy = reset_on_material_change`
- `idempotency_policy = no_op_success_on_repeat`
- `concurrency_policy = optimistic_versioning`
- `error_contract = 403/404/422/409`

## Rules
- Authentication is required for all room actions.
- Room states:
- `lobby`: editable; supports membership, setup, and launch.
- `in_progress`: not editable via lobby setup actions.
- `ended`: not editable and not active for join/setup.
- Room creation:
- Creator becomes moderator.
- Creator is inserted as joined member immediately.
- Membership:
- One membership record per `(room_id, user_id)`.
- A user may be associated with at most one non-ended room at a time (either joined or waitlisted).
- Join is allowed only in `lobby`.
- Leave is allowed only in `lobby`.
- Join or waitlist enrollment is rejected if user is already joined/waitlisted in another non-ended room.
- User must leave current room context (or be removed) before joining another room.
- If moderator leaves, the room closes immediately (`ended`) and no further lobby actions are allowed.
- Joined capacity is capped at 25 players.
- If room is at joined capacity, additional join requests are added to a room-scoped waitlist.
- Waitlist order is FIFO.
- When a joined slot opens in `lobby`, first waitlisted non-banned user is promoted to joined.
- Promoted users start as `is_ready = false`.
- Repeated `join` for already-joined user is no-op success.
- Repeated `leave` for already-left user is no-op success.
- Permissions:
- Moderator-only: assign role, shuffle roles, set member balance, upsert/deactivate catalog items, kick member, ban member, unban member, launch, delete room.
- Participant: join/leave and set own readiness.
- Moderator may set readiness for any joined member.
- Readiness:
- Only joined members can have readiness set.
- Readiness is boolean and room-scoped.
- Repeated readiness update with same value is no-op success.
- Readiness resets to `false` for all joined members after material lobby changes:
- member join/leave/kick/ban/unban
- role assign/shuffle
- balance update
- catalog upsert/deactivate/image change
- Launch itself does not reset readiness.
- Waitlisted users are not readiness-eligible until joined.
- Role assignment:
- Role/faction values use canonical naming (`Police`, `Mob`, `Merchant`).
- Moderator may manually assign role name/rank for joined users.
- Shuffle only reorders assignments among joined members.
- Balance setup:
- Starting balance must be non-negative.
- Balance is rounded to nearest 10 (5 rounds up).
- Catalog setup:
- Classification must be from approved enum list.
- Base price must be non-negative and rounded to nearest 10 (5 rounds up).
- Upsert preserves classification identity and replaces display/price/image.
- Deactivate marks item unavailable without deleting history.
- Kick and ban:
- Kick removes target from joined roster and waitlist, clears readiness and assigned role, and marks membership as `kicked`.
- Ban is room-scoped and remains active until room ends or moderator unbans.
- Ban removes target from joined roster and waitlist if present.
- Banned users cannot join or be promoted from waitlist.
- Launch gating:
- Only moderator can launch.
- Room must be in `lobby`.
- Joined member count must be between 7 and 25 inclusive.
- All joined members must have `is_ready = true`.
- On successful launch, room status becomes `in_progress` and a `game_id` is returned.
- Concurrency/versioning:
- Mutating lobby actions must include expected room version.
- If expected version does not match current room version, action is rejected with conflict.
- Error contract:
- `403` for permission failures.
- `404` for missing room.
- `422` for validation and business-rule failures.
- `409` for optimistic concurrency conflicts.

## Inputs
- Room create request (`name`, creator identity).
- Membership actions (`join`, `leave`).
- Moderation membership actions (`kick`, `ban`, `unban`).
- Readiness action (`is_ready`, optional target user when moderator).
- Role assignment/shuffle actions.
- Balance update action (`starting_balance`).
- Catalog upsert/deactivate/image actions.
- Launch/delete actions.
- Expected room version for mutating actions.

## Outputs
- Room summary for list/create paths.
- Room detail snapshot for setup/membership updates.
- Waitlist snapshot for capacity-driven join handling.
- Launch payload containing `game_id`.
- Structured errors for invalid request / forbidden action.
- Conflict errors for stale version writes.

## Invariants
- No cross-room state access or mutation.
- Hidden gameplay data is not leaked from lobby endpoints.
- Moderator identity is singular per room.
- User room association is globally unique across non-ended rooms.
- Item classification policy is enum-locked (no free-text classes).
- Monetary values are reconcilable and rounding-consistent.
- Joined members never exceed 25.
- Banned users cannot rejoin while ban is active.

## Edge Cases
- User rejoins after leaving: membership returns to `joined`; no duplicate member row.
- User joins with changed username: username refreshes for that user record.
- Moderator leaves: room closes immediately.
- Non-moderator invokes moderator action: forbidden.
- Assign/balance/readiness target is not joined: rejected.
- Unsupported faction or item classification: rejected.
- Room edited after launch (`in_progress`): rejected for setup endpoints.
- Launch with 6 players: rejected.
- Launch with 26 players: rejected.
- Launch with one joined member not ready: rejected.
- Join when room has 25 joined members: request goes to waitlist.
- User tries to join another room while already joined elsewhere: rejected.
- User tries to join another room while already waitlisted elsewhere: rejected.
- Waitlisted player promoted after a joined player leaves/kicked in `lobby`.
- Banned player attempts to join: rejected and not waitlisted.
- Catalog image replacement for missing item: rejected (must upsert item first).
- Duplicate submissions (same action retried): behavior is deterministic and does not corrupt state.
- Mutating request with stale room version: rejected with conflict and no mutation.

## Test Notes
- Unit tests:
- Permission matrix per endpoint/use case.
- Rounding behavior (including tie value `5`).
- Membership rejoin and moderator-leave room closure.
- Launch gates at player-count boundaries (`6`, `7`, `25`, `26`).
- Launch gate for all-ready condition.
- Classification/faction validation.
- Waitlist FIFO promotion behavior.
- Kick/ban permission and rejoin blocking behavior.
- Readiness reset behavior on each material mutation type.
- Idempotency behavior on repeated join/leave/readiness.
- Concurrency conflict behavior with stale versions.
- Integration tests:
- API response codes and error object shape.
- Persistence consistency for sqlite repository.
- Concurrent action safety (double join, join + launch race).

## Open Items
- Whether moderation actions (`kick`, `ban`, `unban`) require audit-log export in v1 or v2.
