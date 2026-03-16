# feature_game_session_start

## Goal
Define the authoritative contract for transitioning a room launch into a persisted gameplay session.

## Scope
- In scope:
  - `rooms.launch_game_from_room(...)` handoff into `gameplay.start_session_from_room(...)`.
  - Initial `GameDetailsSnapshot` creation and persistence.
  - Returned `game_id` authority source.
- Out of scope:
  - Trial voting internals.
  - Economy transfer math.
  - End-game win resolution.

## Rules (authoritative)
- Launch gate remains room-authoritative before handoff:
  - moderator-only request
  - room must be in `lobby`
  - minimum player requirement met
  - active catalog requirement met
- Gameplay session creation is authoritative for `game_id` when gameplay is wired.
- Room status transitions to `in_progress` only after gameplay session creation succeeds.
- Session bootstraps with:
  - `status = in_progress`
  - `phase = information`
  - `round_number = 1`
  - `version = 1`
- Session participants include joined non-moderator room members only.
- Session catalog is copied from room catalog snapshot at launch time.

## Inputs
- Room launch request:
  - `room_id`
  - `requested_by_user_id`
- Mapped start command:
  - `room_id`
  - `moderator_user_id`
  - `launched_at_epoch_seconds`
  - participant list (user/role/rank/balance)
  - catalog list

## Outputs
- Success:
  - stable `game_id`
  - room status set to `in_progress`
  - persisted gameplay session retrievable by `game_id`
- Failure:
  - launch rejected with typed error
  - room status remains unchanged

## Invariants
- One room launch request must not create multiple game sessions for one successful mutation path.
- No moderator participant record is included in gameplay participants.
- Hidden-role protection is projection-layer enforced; full role truth may exist in internal session state.

## Edge Cases
- Missing assigned role on a joined participant blocks launch mapping.
- Gameplay session creation failure must prevent room status flip.
- Dev-mode minimum player override applies only through project settings adapter.

## Test Notes
- Domain:
  - session bootstrap fields
  - room->game command mapping excludes moderator
  - failure path preserves room lobby status
- Integration:
  - launch returns gameplay-backed `game_id`
  - created session reloads from persistence

## Open Items
- Introduce transactional boundary for room-status flip + gameplay session write (single DB transaction if/when both share persistence boundary).
