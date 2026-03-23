# Game Session Lifecycle Monitoring

## Goal

Define the minimum operator-facing checks for detecting stuck or inconsistent room and gameplay lifecycle state.

## Monitoring Notes

- Treat room state and gameplay state as a linked lifecycle pair.
- A launched room should have exactly one persisted gameplay session with the same `room_id`.
- A gameplay session marked `ended` should eventually have its linked room ended as well.
- Mutations should fail fast on version mismatch rather than silently rebasing.
- Gameplay saves now enforce strict ledger reconciliation for implemented transfer routes.

## Practical Checks

- Detect rooms marked `in_progress` with no gameplay session.
- Detect gameplay sessions in `in_progress` where the linked room is not `in_progress`.
- Detect sessions stuck in `accused_selection` with an expired deadline.
- Detect sessions stuck in `trial_voting` with an expired vote deadline.
- Detect sessions whose latest version cannot be saved because ledger reconciliation fails.
- Detect sessions with repeated mutation conflicts that may indicate aggressive polling or stale clients.

## Current Operator Actions

- Use `/operations/healthcheck` for coarse server health only.
- Use `/operations/metrics` for future scrape-based alerting.
- Use `python3 project/mobboss_apps/manage.py clear_stale_lifecycle` for stale room/game cleanup inspection.
- Use `python3 project/mobboss_apps/manage.py clear_stale_lifecycle --apply` only after confirming the stale pairing is invalid.

## Suggested Metrics

- Count of active rooms.
- Count of active gameplay sessions.
- Count of mismatched room/game lifecycle pairs.
- Count of sessions past accused-selection deadline.
- Count of sessions past trial-voting deadline.
- Count of gameplay mutation version conflicts.
- Count of gameplay ledger reconciliation failures.

## Response Guidance

- If lifecycle mismatch is detected, prefer inspecting the latest persisted gameplay session before forcing room cleanup.
- If a phase deadline has elapsed but the session remains active, verify moderator action path and polling before manual cleanup.
- If ledger reconciliation fails, stop adding new gameplay mutations until the offending session snapshot is inspected.
