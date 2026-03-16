# feature_room_lobby_edge_cases

## Goal
Define explicit edge-case outcomes for room and lobby behavior so implementation and tests use the same expected results.

## Scope
- Pre-game room/lobby flows only.
- Error outcomes and state-protection behavior.

## Rules (Authoritative)
- Invalid input returns validation error; no partial room mutation.
- Forbidden action returns authorization error; no room mutation.
- Missing room returns `404`; no side effects.
- Any failed action is atomic (all-or-nothing).
- Stale write version returns `409`; no side effects.

## Edge Case Matrix
| Area | Scenario | Expected Result |
|---|---|---|
| Room lifecycle | Create room with blank/whitespace name | Reject request; room not created |
| Room lifecycle | Delete room by non-moderator | Forbidden; room unchanged |
| Room lifecycle | Moderator leaves lobby room | Room becomes `ended`; joined and waitlist actions become unavailable |
| Membership | Join room when status is `in_progress` | Reject request |
| Membership | Join room when status is `ended` | Reject request |
| Membership | Join room while already joined in another non-ended room | Reject request |
| Membership | Join room while waitlisted in another non-ended room | Reject request |
| Membership | Join room when already joined | Idempotent success (no duplicate member) |
| Membership | Leave room when already `left` | Idempotent success (no mutation) |
| Membership | Join when joined roster has 25 players | User is appended to waitlist (FIFO) |
| Membership | Rejoin after leave | Membership becomes `joined`; readiness resets to `false` |
| Membership | Waitlist slot opens while room is `lobby` | First non-banned waitlisted user auto-promoted to joined |
| Membership | Banned user is on waitlist during promotion | User skipped; next eligible waitlisted user considered |
| Membership | User leaves current room then joins another room | Success under normal join/waitlist rules |
| Readiness | Participant sets readiness for another user | Forbidden |
| Readiness | Readiness set for non-joined user | Reject request |
| Readiness | Launch with one joined member `is_ready=false` | Reject request |
| Readiness | Same readiness value submitted repeatedly | Idempotent success (no mutation) |
| Readiness | Material setup change after all-ready state | All joined readiness reset to `false` |
| Roles | Assign role with invalid faction | Reject request |
| Roles | Assign role rank `< 1` | Reject request |
| Roles | Shuffle roles with less than 1 joined player | No-op success |
| Economy setup | Starting balance is negative | Reject request |
| Economy setup | Starting balance rounding for `125` | Stored as `130` |
| Economy setup | Starting balance rounding for `124` | Stored as `120` |
| Catalog | Upsert catalog item with unknown classification | Reject request |
| Catalog | Upsert item with negative base price | Reject request |
| Catalog | Replace image for non-existent catalog item | Reject request |
| Catalog | Deactivate unknown classification in room | Reject request |
| Launch | Launch with 6 joined members | Reject request |
| Launch | Launch with 7 joined members | Success; room -> `in_progress`; return `game_id` |
| Launch | Launch requested by non-moderator | Forbidden |
| Launch | Launch called twice | First succeeds; second rejected because room no longer `lobby` |
| Moderation | Moderator kicks joined user | User removed from joined, marked kicked, readiness/role cleared |
| Moderation | Moderator bans joined user | User removed from joined/waitlist and blocked from rejoin until unbanned or room end |
| Moderation | Moderator unbans user | User may join again under normal join/waitlist rules |
| Moderation | Banned user attempts direct join | Reject request and do not waitlist |
| Concurrency | Two simultaneous joins by same user | Exactly one joined member record |
| Concurrency | Launch and join race near threshold | Deterministic order; only one result applies |
| Concurrency | Mutating write with stale room version | Reject request with `409`; room unchanged |
| Errors | Action on missing room id | Return `404` |

## Inputs
- Any room/lobby command payload that can be malformed, unauthorized, stale, or concurrent.

## Outputs
- Stable success payloads with expected room snapshot.
- Stable error codes/messages for invalid and forbidden cases.

## Invariants
- Failed requests never mutate room state.
- Member uniqueness is preserved.
- Launch never occurs below minimum count.
- Setup endpoints never mutate non-`lobby` rooms.
- Joined roster never exceeds 25 users.
- Ban blocks both direct join and waitlist promotion.
- User appears in at most one non-ended room context (joined or waitlisted).

## Test Notes
- Add table-driven tests from this matrix.
- Add race-condition integration tests for `join/join` and `join/launch`.
- Add stale-version conflict tests for all mutating actions.
- Validate room snapshot equality before/after all rejected actions.

## Open Items
- Decide whether to expose waitlist position and ETA hints to clients in v1.
