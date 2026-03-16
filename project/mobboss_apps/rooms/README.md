# Rooms App Scope (Pre-Game Authority)

This document is the implementation checklist for what the room layer must support before game launch.

## Purpose

`rooms` owns lobby and pre-game orchestration. It does not resolve in-round gameplay/trial logic.

## In-Room Capabilities

- Create room.
- Assign room creator as moderator.
- Join room.
- Leave room.
- Track membership state (`joined`, `left`, `kicked`).
- Track readiness state per member.
- Assign pre-game role slots in room (moderator-only).
- Manage pre-game member starting balance (moderator-only).
- Manage pre-game room item catalog (moderator-only):
  - baseline required catalog items are preloaded automatically (7 minimum)
  - add/update item defaults by approved classification only
  - set base price
  - set/replace image path
  - deactivate non-required item
- Launch game from room (moderator-only), which transitions room from `lobby` to `in_progress`.
 - If moderator leaves, room closes immediately and all members are evicted (`left`).
 - Lobby rooms auto-close if not launched within 2 hours of room open time.
 - Room-scoped media under `MEDIA_ROOT/rooms/<room_id>/` is auto-cleaned when a room is closed or deleted.

## Capability Matrix

Moderator can:

- Create room (becomes room moderator).
- Join/leave policy control (may kick in future).
- Mark readiness for any member.
- Assign pre-game faction/role/rank in room.
- Set pre-game starting balance for members.
- Add/update/deactivate room item catalog entries.
- Launch game from room.

Participant can:

- Join a room.
- Leave a room (non-moderator).
- Mark only their own readiness.
- View room state allowed to lobby users.

Participant cannot:

- Assign or edit role slots for any member.
- Change other members' balances.
- Manage room item catalog.
- Launch game.
- Transfer moderator ownership.

Not in scope for `rooms` right now:

- Chat/messaging (no room chat behavior implemented yet).
- Trial/gameplay resolution.
- In-round role succession.

## Constraints

- Moderator is room authority and not treated as a normal participant role.
- Role assignment in room is pre-game setup and can be changed before launch.
- Money values in room setup use nearest-10 rounding (5 rounds up).
- Item classification is enum/approved-list only (not free text).
- A required baseline item set (7) is always present and cannot be deactivated.
- Minimum player count to launch is 7 (per game rules baseline).
- Room data is scoped by room id and must not leak across rooms.
- Lobby room listing prunes orphaned rooms where moderator is not joined by auto-closing and evicting members.
- Room open time is tracked and used for lobby auto-close enforcement.

## Out Of Scope (Handled Elsewhere)

- Trial flow, murders, jury, conviction resolution.
- In-round role succession and game phase progression.
- Runtime player perspective filtering.
- Persistent DB concerns (adapter choice later).

## Current Implementation Target

Use memory adapters first for unit-testable behavior:

- `rooms/src/room_service.py` (inbound use-case logic)
- `rooms/adapters/outbound/memory_repository.py` (in-memory outbound adapter)
