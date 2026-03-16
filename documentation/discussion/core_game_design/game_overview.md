# Game Overview

Mob Boss is a live-action social deduction game for 7-25 players. Players move through a shared space, form alliances, trade items, commit murders, and participate in trials. The game is overseen by a Moderator and assisted by a server and client apps.

Core factions:
- Police (team)
- Mob (team)
- Merchants (solo win condition)

Win conditions:
- Police win: all Mob eliminated, without exceeding their kill limit.
- Mob win: all Police eliminated.
- Merchant win: reach personal money goal.

Win condition evaluation order (at boundaries only):
- Evaluate only at boundary events (murder resolution boundary, trial verdict boundary, moderator elimination boundary, round boundary).
- If a murder event wipes out Police or Mob, game ends immediately and no trial starts.
- If a trial outcome wipes out Police or Mob, game ends immediately.
- Merchant boundary precedence: if any Merchant meets goal at a boundary, Merchant win is resolved first at that boundary.
- Merchant precedence is single-winner resolution for that boundary (do not evaluate additional faction wins after Merchant win is awarded).

Known constraints:
- Gameplay is continuous.
- Each round is driven by a single murder and a single trial.
- Minimum players: 7.
- Maximum players: 25.

## Open Discussion

- Q1: What are the definitive start and end conditions for a game session (beyond win conditions)?
Response:

- Q2: Should there be a time cap or max rounds? If yes, what happens at cap?
Response:
