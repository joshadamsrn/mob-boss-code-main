# Trial System

## Trigger
- A trial begins when a player is killed.
- Only one murder and one trial per round.
- Attempted murder blocked by vest does not trigger a trial.

## Accused Selection
- Police Chief selects the accused via server prompt.
- Police Chief has 15 seconds to select a live player.
- If the Police Chief does not respond, responsibility passes down Police rank order.
- Each Police responder receives 15 seconds.
- The Police Chief is notified immediately upon a death report.
- If timeout occurs, only the responding replacement Police player is notified.
- Public notification is delayed until an accused is selected and trial begins.
- Gameplay remains continuous during this interval.
- If the final eligible Police responder times out, trial is canceled as no-conviction and gameplay continues.
- Players are notified that no conviction occurred.
- In no-conviction outcome, murdered player resources transfer directly to the murderer with no stash flow.

## Jury Selection
- Randomly select 1/4 of remaining living players.
- Jury size must be odd and at least 3.
- Exclude dead players and jailed players.
- No other exclusions.

## Voting
- Moderator initiates a 10-second countdown to force the vote.
- If a juror does not vote before the countdown ends, the server assigns a random vote for that juror.
- Jury votes Guilty or Innocent.
- Guilty + EFJ owned: EFJ auto-uses; accused remains in game.
- Guilty + no EFJ: accused is eliminated.
- Innocent: game advances to next round.

## Trial Phase Rules
- No murders or purchases may occur during an active trial.
- No item use may be initiated during an active trial.

## Stash Resolution
- Correct accusation requires conviction of the actual murderer.
- Correct accusation + Guilty + no EFJ: Police Chief receives accused resources.
- Wrong accusation + Guilty + no EFJ: Mob Boss receives accused resources.
- Innocent: accused keeps resources.
- Guilty + EFJ auto-use: no transfer and no reveal.

## Offline Players
- If a player is offline, they are treated as dead.
- Moderator can mark a player as dead at any time.
- Offline/moderator death handling does not trigger trial flow and does not break round flow.
- Offline death redistribution is forced liquidation:
- All items return to central supply.
- Liquidated money value is based on item purchase price and is distributed evenly to the player's faction.

## Open Discussion

- Q1: If the faction has zero remaining living members at liquidation time, where does redistributed liquidation value go?
Response:
