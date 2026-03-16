# Events and Notifications

Server-driven events:
- Trial started
- Jury selected
- Vote requested
- Verdict announced
- Player eliminated
- Attempted murder blocked by vest
- Police kill limit updated
- Merchant goal progress
- Game ended
- Player online/offline status changed

Notification sequencing:
- Police Chief is notified immediately upon a death report.
- If Chief times out, next-ranked Police is notified.
- Public notification is delayed until an accused is selected and trial begins.
- For attempted murder blocked by vest, all players are notified of vest use and survival; attacker identity is not globally disclosed.
- If no Police responder selects an accused in the full 15-second chain, players are notified that no conviction occurred and trial did not start.

Delivery:
- Clients poll the server for updates (no push concept).
- Default polling interval: 5 seconds.

Offline handling:
- Offline players are treated as dead.
- Moderator can mark players dead at any time.
- Offline/moderator death does not trigger trial and does not pause gameplay.

## Open Discussion

- Q1: Notification ordering guarantees?
Response:
