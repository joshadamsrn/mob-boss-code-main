# Next Phase Checklist

This file is the coordination board for the next implementation phase: moving from room launch to an authoritative in-game session engine.

## Status Legend

- `[ ]` unclaimed / not started
- `[~]` claimed and in progress
- `[x]` done

## Phase Goal

Build the first authoritative gameplay slice:

1. `rooms.launch_game_from_room(...)` hands off to `gameplay.start_session_from_room(...)`
2. A persisted `GameSession` aggregate exists
3. A first gameplay read model exists (`GET game state`)
4. A first gameplay transition exists (`report_death` into accused-selection/no-trial branch)

## Foundational Context (Authoritative)

- Room/lobby is pre-game authority; gameplay app owns in-game authority.
- Launch transitions room state from `lobby` to `in_progress` and returns `game_id`.
- Gameplay loop is continuous with boundary checks and trial branch rules.
- One murder can trigger at most one trial.
- Hidden role information must not leak in public/player views.
- Money must remain fully reconcilable inside the game economy.

## Reference Docs to Read First

### Project Conventions (authoritative for implementation shape)

- `CONVENTIONS.md`
- `documentation/features/feature_hex_request_dto_and_composition.md`

### Feature Specs (authoritative contracts)

- `documentation/features/feature_room_lobby_preparation.md`
- `documentation/features/feature_room_lobby_perspectives.md`
- `documentation/features/feature_room_lobby_edge_cases.md`
- `documentation/features/feature_game_flow.md`
- `documentation/features/feature_trials_and_convictions.md`
- `documentation/features/feature_economy_and_items.md`
- `documentation/features/feature_player_views.md`

### App Boundaries + System Design

- `documentation/discussion/system_and_data_design/app_boundaries.md`
- `documentation/discussion/system_and_data_design/state_model.md`
- `documentation/discussion/system_and_data_design/client_views.md`
- `documentation/discussion/system_and_data_design/server_api_contract.md`

### Core Rule Detail (supporting)

- `documentation/discussion/core_game_design/game_loop.md`
- `documentation/discussion/core_game_design/trial_system.md`
- `documentation/discussion/core_game_design/roles_and_hierarchy.md`
- `documentation/discussion/core_game_design/economy_and_weights.md`
- `documentation/discussion/core_game_design/items_and_weapons.md`

### Current Implementation Entry Points

- `project/mobboss_apps/rooms/src/room_service.py`
- `project/mobboss_apps/rooms/ports/internal.py`
- `project/mobboss_apps/rooms/ports/internal_requests_dto.py`
- `project/mobboss_apps/rooms/views.py`
- `project/mobboss_apps/rooms/v1_views.py`
- `project/mobboss_apps/mobboss/composition.py`
- `project/mobboss_apps/mobboss/urls.py`
- `openapi.yml`

## Proposed Aggregate Shapes (Initial Contract)

These are proposed implementation shapes to align all agents before coding. Adjust only through explicit team agreement.

### `GameSession` aggregate

```text
GameSession
- game_id: str
- room_id: str
- status: "in_progress" | "paused" | "ended"
- phase: "information" | "accused_selection" | "trial_voting" | "boundary_resolution" | "ended"
- round_number: int
- version: int  # optimistic concurrency
- launched_at_epoch_seconds: int
- ended_at_epoch_seconds: int | null
- participants: list[ParticipantState]
- catalog: list[CatalogItemState]
- ledger: LedgerState
- pending_trial: TrialState | null
- boundary_checkpoint: BoundaryCheckpoint | null
- win_result: WinResult | null
```

### `ParticipantState`

```text
ParticipantState
- user_id: str
- username: str
- faction: "Police" | "Mob" | "Merchant"
- role_name: str
- rank: int
- life_state: "alive" | "dead" | "jailed"
- money_balance: int
- inventory: list[InventoryItem]
- is_online: bool
- notes_ref: str | null  # notebook ownership hook
```

### `TrialState`

```text
TrialState
- murdered_user_id: str
- murderer_user_id: str | null  # server-known, hidden from most views
- accused_user_id: str | null
- accused_selection_cursor: list[str]  # eligible police in rank order
- accused_selection_deadline_epoch_seconds: int | null
- jury_user_ids: list[str]
- vote_deadline_epoch_seconds: int | null
- votes: list[JurorVote]
- verdict: "guilty" | "innocent" | null
- conviction_correct: bool | null
- resolution: "efj_saved" | "eliminated" | "no_conviction" | null
```

### `LedgerState` (minimal now, expandable later)

```text
LedgerState
- circulating_currency_baseline: int
- entries: list[LedgerEntry]
- checksum: str | null
```

### `GameDetailsSnapshot` (internal full snapshot)

```text
GameDetailsSnapshot
- game_id
- room_id
- status
- phase
- round_number
- version
- participants (full internal)
- catalog
- pending_trial
- boundary_checkpoint
- win_result
- server_time_epoch_seconds
```

### Perspective View Shapes (external)

```text
ModeratorGameView
- full participant role/faction/rank
- full trial internals
- full ledger metadata

PlayerGameView (alive)
- self role/faction/rank
- allowed shared state
- hidden-role-safe participant summaries

DeadPlayerGameView
- extended visibility policy per feature spec
- read-only actions only
```

## Workstream Checklist

### 0) Coordination

- [x] Create shared next-phase checklist document.
- [~] Assign each workstream to an owner agent in this file.
- [ ] Add PR/branch links next to each claimed task.

### 0.5) Dev Playtest Mode (Cross-Cutting)

- [x] Add dev-only room launch minimum override setting (`ROOM_DEV_MODE`, `ROOM_MIN_LAUNCH_PLAYERS`).
- [x] Ensure launch gate remains server-authoritative when override is active.
- [x] Update room UI to show the effective minimum launch player requirement.
- [x] Add dev-only moderator perspective switching tabs (read-only first pass).
- [x] Evaluate bot-seat vs real-session-switch strategy and record decision in docs.

### 1) Gameplay Domain Contract

- [x] Create `gameplay/ports/internal.py` DTOs for session/participant/trial snapshots and commands.
- [x] Create `gameplay/ports/inbound.py` with `start_session_from_room`, `get_game_details`, `report_death`.
- [x] Create `gameplay/ports/outbound.py` for repository contract and game id reservation strategy.
- [x] Define enum literals for phase/status/life-state/verdict in one place.
- [x] Add explicit invariants in code comments/docstrings (no role leakage, boundary-only win checks, one-trial-per-murder).

### 2) Gameplay Service + Repository (Authoritative Core)

- [x] Implement `gameplay/src/game_service.py` with aggregate construction from room snapshot.
- [x] Implement round/phase bootstrap (`information` phase on launch).
- [x] Implement `report_death` happy path to `accused_selection`.
- [x] Implement accused-selection timeout chain (15 seconds per eligible police rank).
- [x] Implement no-selection branch (`no_conviction`, direct transfer routing placeholder).
- [x] Implement minimal repository adapter (memory first) for `GameSession`.
- [x] Wire sqlite adapter scaffold for game session persistence.

### 3) Rooms -> Gameplay Launch Handoff

- [x] Extend `rooms` outbound/inbound boundaries so launch calls gameplay start use-case.
- [x] Build launch snapshot mapper from `RoomDetailsSnapshot` -> `StartSessionFromRoomCommand`.
- [x] Keep room launch gate enforcement server-side; remove any UI-only assumptions.
- [x] Ensure launch is atomic enough to avoid room marked `in_progress` without gameplay session.
- [x] Return stable `{game_id}` from real gameplay session creation.

### 4) API + Routing

- [x] Add gameplay routes under `mobboss/urls.py` (`/games/...` or `/gameplay/v1/...`).
- [x] Implement first read endpoint: game details by `game_id` with perspective filtering.
- [x] Implement first mutation endpoint: `report_death`.
- [x] Map exceptions to RFC 7807 problem-details response style.
- [x] Update `openapi.yml` for gameplay endpoints and schemas.
- [ ] (Deferred) Add automatic conflict-retry UX for `report_death` on 409; keep strict manual refresh/retry for now.
- [x] Standardize version-conflict response shape for gameplay mutations (`expected_version`, `current_version`).

### 5) Web Surface (Minimal Vertical Slice)

- [x] Add post-launch redirect from room page to gameplay page using returned `game_id`.
- [x] Create gameplay template shell with phase banner + participant list (role-safe view).
- [x] Add poll loop for gameplay state (match existing cadence unless changed by config).
- [x] Add moderator-only controls needed for initial death reporting flow.
- [x] Preserve mobile-first behavior and avoid hidden-role leakage in HTML payloads.
- [x] Use one shared frontend helper for all versioned gameplay mutations (strict-manual retry policy).

### 6) Economy + Transfer Hooks (Stub Then Harden)

- [ ] Introduce ledger entry model in gameplay/economy boundary.
- [ ] Add stubbed transfer functions for murder/no-trial routing.
- [ ] Add EFJ and vest hook points without full implementation coupling.
- [ ] Add reconciliation helper (`money cannot leave economy`) and checksum scaffold.

### 7) Testing (Required for Merge)

- [x] Add unit tests for `start_session_from_room` aggregate creation.
- [x] Add unit tests for accused-selection rank-chain timeout behavior.
- [x] Add unit tests for no-trial branch when no police responds.
- [x] Add integration test for room launch handoff creates game session and returns `game_id`.
- [x] Add API tests for perspective filtering (moderator vs player vs dead-player policy).
- [x] Add conflict/version tests for game-state mutation commands.
- [x] Add endpoint-level tests for dev seat add/remove permission gates.

### 8) Documentation + Operations

- [x] Add `documentation/features/feature_game_session_start.md` (new authoritative feature spec).
- [x] Update `feature_game_flow.md` if behavior changed during implementation.
- [ ] Add sequence diagrams for launch handoff and death-report flow.
- [ ] Add operations notes for monitoring game session lifecycle and stuck-phase detection.
- [ ] Track unresolved rules in `documentation/discussion/planning_and_execution/open_discussion.md`.

## Parallelization Notes

- Workstreams `1`, `2`, and `4` can start in parallel if DTO contracts are frozen first.
- Workstream `3` depends on `1` and initial `2`.
- Workstream `5` depends on `4` read endpoint and stable launch redirect contract.
- Workstream `7` should be developed alongside each workstream, not at the end.

## Claim Board (Update Live)

- Domain Contract Owner: `[~]` Codex (current session)
- Gameplay Service Owner: `[~]` Codex (current session)
- Rooms Handoff Owner: `[x]` Codex (launch handoff slice complete)
- API/Routing Owner: `[x]` Codex (gameplay routes + read/mutation + OpenAPI)
- Web Owner: `[x]` Codex (dev-playtest UI + gameplay launch redirect shell + polling)
- Tests Owner: `[x]` Codex (dev launch override + handoff/domain + gameplay API/conflict tests)
- Docs/Ops Owner: `[~]` Codex (checklist + decisions updates)
