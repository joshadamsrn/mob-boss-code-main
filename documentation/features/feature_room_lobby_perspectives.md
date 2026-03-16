# feature_room_lobby_perspectives

## Goal
Define authoritative room/lobby visibility and action permissions by perspective so UI and API behavior are consistent.

## Scope
- `lobby` state room behavior for joined players, waitlisted players, and moderator.
- Visibility rules and allowed actions only.

## Rules
- Shared room visibility for authenticated users in room context:
- room name and status
- moderator identity
- joined count and capacity (`/25`)
- launch requirements summary (`7-25 joined`, all joined ready)
- Single-room participation:
- A user may be in at most one non-ended room context at a time.
- Context means either joined member or waitlisted member.
- Attempting to join or waitlist a second non-ended room is rejected.

## Feature Matrix (Actions)
| Feature | Joined Player | Waitlisted Player | Moderator | Notes |
|---|---|---|---|---|
| Join room | Yes (if not already joined and not blocked) | N/A | Yes | Single-room rule enforced globally |
| Enter waitlist when room full | Auto via join | N/A | N/A | FIFO order, room-scoped |
| Leave room | Yes | N/A | Yes (closes room) | Moderator leave sets room `ended` |
| Leave waitlist | N/A | Yes | Yes (kick/remove) | Removes waitlist context |
| Set own readiness | Yes | No | Yes | Waitlisted users are not readiness-eligible |
| Set another user's readiness | No | No | Yes | Joined targets only |
| Assign role | No | No | Yes | Joined targets only |
| Shuffle roles | No | No | Yes | Joined members only |
| Set starting balance | No | No | Yes | Joined targets only |
| Upsert/deactivate catalog item | No | No | Yes | Moderator-only setup control |
| Kick user | No | No | Yes | Works for joined and waitlisted users |
| Ban user | No | No | Yes | Room-scoped ban until unban or room end |
| Unban user | No | No | Yes | Restores join eligibility |
| Launch game | No | No | Yes | Requires 7-25 joined and all joined ready |
| Delete room | No | No | Yes | Moderator-only destructive action |

## Feature Matrix (Visibility)
| Data / View | Joined Player | Waitlisted Player | Moderator | Notes |
|---|---|---|---|---|
| Room name and status | Yes | Yes | Yes | Shared context data |
| Moderator identity | Yes | Yes | Yes | Shared context data |
| Joined count / capacity | Yes | Yes | Yes | Shared context data |
| Joined roster usernames | Yes | Optional | Yes | Waitlisted roster visibility can be limited |
| Joined readiness states | Yes | Optional | Yes | Same as roster visibility policy |
| Own role assignment | Yes (self only) | No | Yes (all joined) | Moderator can view all roles |
| Own starting balance | Yes (self only) | No | Yes (all joined) | Moderator can view all balances |
| Catalog items and prices | Yes | Yes | Yes | Setup transparency |
| Waitlist count | Yes | Yes | Yes | Shared context data |
| Waitlist order/positions | Self position only | Self position only | Yes (full order) | Prevents unnecessary exposure |
| Ban list | No | No | Yes | Moderator-only moderation surface |

## Joined Player Perspective
- Can see:
- joined roster with username and readiness state
- own assigned role and own starting balance
- room catalog (active/inactive state and prices)
- waitlist count
- Can do:
- leave room
- set own readiness
- Cannot do:
- set readiness for others
- role assignment/shuffle
- balance updates
- catalog updates
- kick/ban/unban
- launch/delete room

## Waitlisted Player Perspective
- Can see:
- room status and joined count/capacity
- own waitlist position
- waitlist count
- Can do:
- leave waitlist
- Cannot do:
- readiness updates
- receive active role/balance setup
- launch/delete/moderation actions

## Moderator Perspective
- Can see:
- all joined roster details
- all role assignments and balances
- full waitlist order
- ban list
- Can do:
- all joined-player actions
- set readiness for any joined member
- assign roles and shuffle roles
- set member balances
- upsert/deactivate catalog and set item image
- kick users (joined or waitlisted)
- ban and unban users
- launch room when launch gates are satisfied
- delete room
- leave room (which closes room immediately)

## Invariants
- No hidden gameplay state is exposed in lobby.
- Permission checks are server-authoritative.
- Joined members and waitlisted users are disjoint sets.
- User participation is unique across non-ended rooms.

## Edge Cases
- Moderator leave closes room; all room actions stop.
- Non-moderator invoking moderator action is forbidden.
- Banned user cannot join or remain on waitlist.
- Full room join attempts route to waitlist unless user blocked by single-room rule.
- User leaving room frees them to join another room.

## Test Notes
- Permission matrix tests per perspective/action pair.
- View payload tests to ensure each perspective sees only allowed fields.
- Single-room participation tests across two non-ended rooms.
