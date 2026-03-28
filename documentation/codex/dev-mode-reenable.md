# Dev Mode Re-Enable Notes

Purpose: give future Codex turns a single repo file to check when dev mode needs to be turned back on for Mob Boss playtesting.

## Primary switch

Dev mode is controlled by the Django setting `ROOM_DEV_MODE`.

Source:
- `project/mobboss_apps/mobboss/settings.py`
- `project/mobboss_apps/mobboss/adapters/outbound/projectsetting_memory_impl.py`

Current setting behavior:
- `ROOM_DEV_MODE = os.getenv("ROOM_DEV_MODE", "0") == "1"`
- `ROOM_MIN_LAUNCH_PLAYERS = int(os.getenv("ROOM_MIN_LAUNCH_PLAYERS", "7"))`

Important guardrail:
- If `ROOM_DEV_MODE` is off, the project setting adapter forces minimum launch players back up to the normal floor.
- If `ROOM_DEV_MODE` is on, `ROOM_MIN_LAUNCH_PLAYERS` can be lowered for testing.

## Fastest way to re-enable

Set environment variables before starting Django:

```bash
export ROOM_DEV_MODE=1
export ROOM_MIN_LAUNCH_PLAYERS=2
```

Then restart the Django process being used for testing.

If full normal behavior is desired again:

```bash
export ROOM_DEV_MODE=0
export ROOM_MIN_LAUNCH_PLAYERS=7
```

## What dev mode enables

In the room lobby:
- `Add Dev Seat`
- `Mark All Ready`
- Moderator-only `view as` testing flows
- `simulate_actions=1` opt-in action simulation
- lower launch minimums when configured

In gameplay:
- moderator can use `view as` plus `simulate_actions`
- gameplay actions resolve through the selected user when dev simulation is enabled

## Core files to inspect when re-enabling or debugging

Settings and composition:
- `project/mobboss_apps/mobboss/settings.py`
- `project/mobboss_apps/mobboss/composition.py`
- `project/mobboss_apps/mobboss/adapters/outbound/projectsetting_memory_impl.py`

Room dev controls:
- `project/mobboss_apps/rooms/views.py`
- `project/mobboss_apps/rooms/templates/rooms/detail.html`
- `project/mobboss_apps/rooms/urls.py`

Gameplay dev simulation:
- `project/mobboss_apps/gameplay/views.py`
- `project/mobboss_apps/gameplay/templates/gameplay/detail.html`
- `project/mobboss_apps/gameplay/v1_views.py`

Existing test coverage:
- `project/mobboss_apps/rooms/tests/rest/test_rooms_views_dev_seats.py`
- `project/mobboss_apps/gameplay/tests/rest/test_gameplay_views_context.py`

## Notes for future Codex turns

If asked to "turn dev mode back on", check these in order:
1. Confirm which process the user is actually testing against.
2. Set `ROOM_DEV_MODE=1`.
3. Set `ROOM_MIN_LAUNCH_PLAYERS` to the requested test value.
4. Restart the running Django server.
5. Verify the lobby shows `Add Dev Seat`.
6. Verify moderator-only `view as` and `simulate actions` behavior still works.

If dev features appear missing after code changes, first confirm the running process picked up the env vars and restart happened.
