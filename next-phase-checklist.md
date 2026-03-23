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
- [x] Add generic role-ability card surface for alive participants.
- [x] Refactor role-ability copy/metadata into a centralized table in `gameplay/views.py`.
- [x] Replace generic fallback text with role-specific placeholder detail blocks for non-powered roles.
- [x] Build a role-by-role implementation matrix for placeholder cards (authoritative next planning step).
- [x] Decide which placeholder roles remain passive-only summaries vs which get future activated powers.
- [x] Record the current authority that remaining placeholder roles stay passive-only until a feature spec defines a new power.

### 6) Economy + Transfer Hooks (Stub Then Harden)

- [x] Introduce ledger entry model in gameplay/economy boundary.
- [x] Add stubbed transfer functions for murder/no-trial routing.
- [x] Add EFJ hook points without full implementation coupling.
- [x] Add vest hook points without full implementation coupling.
- [x] Require attack type on murder reports and broadcast weapon display name in public murder notices.
- [x] Add reconciliation helper (`money cannot leave economy`) and checksum scaffold.

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
- [x] Add sequence diagrams for launch handoff and death-report flow.
- [x] Add operations notes for monitoring game session lifecycle and stuck-phase detection.
- [x] Track unresolved rules in `documentation/discussion/planning_and_execution/open_discussion.md`.
- [x] Update authoritative planning docs with a role-ability implementation matrix once decisions are made.

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

## Current Pickup Point

- Vest/EFJ/report-death gameplay work is complete enough for continued playtest iteration.
- Generic role-ability UI now exists for alive participants:
  - actionable cards are live for `Don`, `Under Boss`, `Kingpin`, `Deputy`, `Sheriff`, `Captain`, `Lieutenant`, `Sergeant`, `Detective`, `Inspector`, `Police Officer`, and `Street Thug`
  - automatic/passive summary cards are live for `Chief of Police`, `Mob Boss`, `Knife Hobo`
  - explicit passive-only summary cards are now live for remaining Police (excluding Deputy, Sheriff, Captain, Lieutenant, Sergeant, Detective, Inspector, and Police Officer), remaining Mob-operative roles, and trade roles
- The next session should not start with 409 auto-retry UX.
- The next session should start with the next unimplemented role power after Street Thug.

### Deputy Role: What Is Already Known

- `Deputy` exists as a canonical Police role title in room assignment and gameplay DTOs.
- `Deputy` now has an activated role ability: `Protective Custody` (once per game).
- Current gameplay behavior for `Protective Custody`:
  - usable during `information` phase only
  - can target any alive player except self
  - target gains 5-minute murder immunity
  - attempted murder on protected target still triggers a trial
  - attempted-murder trial keeps target alive and does not transfer target resources
  - custody notices/timer are visible to moderator, deputy, and target only
- Existing rule/docs support these Deputy-adjacent mechanics:
  - Police hierarchy places `Deputy` directly below `Chief of Police`
  - Police succession is automatic when higher-ranked Police are eliminated
  - EFJ bribe transfer may randomly route to eligible Police, including `Deputy`
  - Deputy starting money is defined in the economy tables
- Deputy power mutation flow now exists in gameplay domain/view layers with targeted tests.

### Detective Role: What Is Already Known

- `Detective` now has an activated role ability: `Investigation` (once per game).
- Current gameplay behavior for `Investigation`:
  - usable during any phase while the game is `in_progress`
  - blocked if the Detective is temporarily removed from interaction by custody/capture
  - can target any participant, including alive, dead, or jailed players
  - privately reveals the target's last 3 player-to-player transactions for 60 seconds with no countdown
  - reveal includes local timestamp, sender, recipient, money amount, item name, and transaction type
  - excludes central-supply and other system-initiated transfers
  - older sale + money-gift history is backfilled from the gameplay ledger where available
  - newly accepted sales, money gifts, and item gifts are now persisted as player transaction history
- Existing rule/docs support these Detective-adjacent mechanics:
  - Police hierarchy places `Detective` below `Sergeant` in succession
  - Detective remains eligible for existing Police-chain logic outside the new power
  - EFJ bribe transfer may randomly route to eligible Police, including `Detective`

### Detective Role: Missing Spec Before Implementation

- None for current Detective scope. Follow-up clarifications, if needed, should only cover edge cases not already implemented.

### Inspector Role: What Is Already Known

- `Inspector` now has an activated role ability: `Record Inspection` (once per game).
- Current gameplay behavior for `Record Inspection`:
  - usable during any phase while the game is `in_progress`
  - blocked if the Inspector is temporarily removed from interaction by custody/capture
  - can target any dead or jailed participant except self
  - privately reveals the target's role name for 60 seconds with no countdown
  - sends no moderator, public, or target-facing notice
  - fails with `No jail or morgue records available yet.` when no dead or jailed targets exist
- Existing rule/docs support these Inspector-adjacent mechanics:
  - Police hierarchy places `Inspector` below `Detective` in succession
  - Inspector remains eligible for existing Police-chain logic outside the new power

### Inspector Role: Missing Spec Before Implementation

- None for current Inspector scope. Follow-up clarifications, if needed, should only cover edge cases not already implemented.

### Police Officer Role: What Is Already Known

- `Police Officer` now has an activated role ability: `Confiscation` (once per game).
- Current gameplay behavior for `Confiscation`:
  - can be armed during `information`, `accused_selection`, or active `trial_voting` before all votes are submitted
  - is blocked if the Police Officer is temporarily removed from interaction by custody/capture
  - applies to the next guilty verdict only
  - if the officer is still alive and EFJ does not trigger, jailed inventory is liquidated into cash and redistributed between the Police Officer and other alive police
  - if the officer is inactive, EFJ triggers, the verdict is not guilty, or no recoverable resources exist, the armed effect is consumed and resolved via notices
  - alive police beneficiaries are notified when they receive funds, and an overridden normal inheritance recipient is notified when confiscation blocks their direct transfer
- Existing rule/docs support these Police Officer-adjacent mechanics:
  - Police hierarchy places `Police Officer` below `Inspector` in succession
  - Police Officer remains eligible for existing Police-chain logic outside the new power

### Police Officer Role: Missing Spec Before Implementation

- None for current Police Officer scope. Follow-up clarifications, if needed, should only cover edge cases not already implemented.

### Street Thug Role: What Is Already Known

- `Street Thug` now has an activated role ability: `Steal` (once per game).
- Current gameplay behavior for `Steal`:
  - usable during any phase while the game is `in_progress`
  - blocked if the Street Thug is temporarily removed from interaction by capture/custody
  - can target any alive non-self participant who is not currently captured
  - if the target has at least `$100`, exactly `$100` moves from the target to the Street Thug
  - if the target has less than `$100`, no money moves and the power is still consumed
  - Street Thug, target, and moderator are notified of the result
  - successful steals are persisted in the gameplay ledger for reconciliation
- Existing rule/docs support these Street Thug-adjacent mechanics:
  - Street Thug remains part of normal Mob succession outside the new power
  - Street Thug starting money is defined in the economy tables
  - Knife Hobo remains the separate automatic starting-knife role and is not part of this activated slice

### Street Thug Role: Missing Spec Before Implementation

- None for current Street Thug scope. Follow-up clarifications, if needed, should only cover edge cases not already implemented.

### Merchant-Faction Clarifications Before Next Slice

- `Merchant`, `Arms Dealer`, `Smuggler`, and `Supplier` are all canonical `Merchant` faction roles.
- Each merchant-type player is solo and pursues their own individual money-goal win condition; merchant-faction players do not share a team win.
- Merchant-type players otherwise participate in the normal game loop:
  - can murder
  - can serve as jurors
  - can be accused, jailed, killed, and affected by ordinary game systems
- Role differentiation comes from role-specific superpowers layered on top of the shared merchant-faction rules.
- At 7 players, the inserted merchant-type role is always `Merchant`.
- Additional merchant-type roles are only added when player count requires more merchant slots; those extra slots are filled from the non-base merchant-role set.

## Next Recommended Order

1. Keep the Detective, Inspector, Police Officer, Street Thug, Ghost View, and Felon escape slices stable while playtesting.
2. Merchant superpower slice is now `Wholesale Order`: once/game discounted central-supply purchase during information phase for the base `Merchant` role.
3. `Arms Dealer` now has automatic `Starting Gun Cache` at launch, `Smuggler` now has active `Smuggle`, and `Gun Runner` now has timed `Charisma`; continue next with `Supplier`.
4. For each role, implement the full vertical slice:
   - domain command/service hook
   - request DTO + endpoint/view
   - role card controls
   - domain tests
   - HTML/JSON tests
5. Revisit deferred 409 auto-retry UX after role card metadata/UI stabilize.
