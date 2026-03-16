# Server and Moderator Responsibilities

## Server (Authoritative)
- Assign roles, hierarchies, and secret code word (Mob).
- Maintain player state, inventories, money, and status.
- Process purchases, transfers, and refunds.
- Trigger trials on death report.
- Ask Police Chief to select accused.
- If Police Chief does not respond, escalate to next highest-ranking Police.
- Randomly select jury and notify them.
- Collect votes and resolve outcomes.
- Confirm accused-vs-actual-murderer match for conviction outcomes and transfer routing.
- Enforce Police kill limit (remaining kills visible to Police).
- Check win conditions and end the game.
- Provide per-player perspective state (no leakage).
- Log all trades and transfers.
- Apply code-word rotation only when enabled by Moderator at game start.

## Moderator (Human-in-the-loop)
- Confirm deaths (honor system validation).
- Enforce no actions during trial.
- Handle disputes and edge cases.
- Manage physical stash locations and item handoffs (if physical).
- Pause, resume, end, and start games.
- Create and launch game rooms.
- Remove players before launch.
- Configure pre-game settings including optional Mob code-word rotation.

TODO
- Define what the server does when the Moderator disputes a death report.

## Open Discussion

- Q1: What is the server workflow if the Moderator disputes a death report?
Response:
