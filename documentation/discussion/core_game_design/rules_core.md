# Rules (Core)

This is the player-facing core rule set. Use TODO markers for missing details.

## Game Loop
- Phase 1: information seeking until a murder occurs.
- Phase 2: trial triggered by the murder.
- Phase 3: return to Phase 1 (new round begins).
- Only one death per round. One murder triggers one trial.

## Roles and Factions
- Police: team-based, limited kills.
- Mob: team-based, hidden.
- Merchants: solo win condition, money goal.

## Trials
- Triggered by a death.
- Police Chief selects the accused.
- Jury is randomly selected by the server.
- Moderator initiates a 10-second countdown to force the vote.
- If a juror does not vote before countdown ends, the server assigns a random vote for that juror.
- Jury votes Guilty or Innocent.
- Guilty: if accused has Escape From Jail (EFJ), it auto-uses immediately after conviction and the accused remains in game; otherwise accused is eliminated.
- Innocent: game immediately advances to the next round.
- If no Police member responds in the accused-selection chain, no trial occurs, no conviction occurs, all players are notified, and gameplay continues as no-conviction.
- If no Police member responds in the accused-selection chain, murdered player resources transfer to the murderer directly and no stash is used.

## Murders and Deaths
- Honor system.
- Killed players must immediately admit death to the Moderator.
- Dead players may not communicate with living players.
- No murders may occur during an active trial.
- If a shot is blocked by a Bulletproof Vest, no death is recorded and no trial is triggered.

## Police Kill Limit
- Police may kill up to half of the initial Mob count (rounded down).
- Police may kill at most 1 per round.
- Police are not required to kill in a round.
- If the Police exceed their total allowed kills, Police lose.

## Merchant Rules
- Merchants can murder freely without constraints.
- Merchants can sell to anyone and may adjust prices above or below shop price.
- Only Merchants can buy from central supply.
- Unlimited items may be carried.
- All trades are logged by the server.

## Merchant Goal
- Each Merchant wins by reaching personal money goal.
- Goal formula: starting money + 40% of total circulating currency.

## Items and Money
- Money and item transfers are server-authoritative.
- Purchases are allowed during gameplay but not during trials.
- No items may be used during an active trial by player action.
- Stash/resource resolution after trial:
- Correct accusation with Guilty verdict and no EFJ: Police Chief receives accused resources.
- Wrong accusation with Guilty verdict and no EFJ: Mob Boss receives accused resources.
- Innocent verdict: accused keeps resources.
- Guilty verdict with EFJ auto-use: no transfer and no reveal.
- If a vest blocks a gunshot: vest is consumed, no trial occurs, vest value transfers to attacker anonymously, and gameplay continues.
- See `economy_and_weights.md` and `items_and_weapons.md`.

## Jailed vs Dead
- Jailed players cannot purchase items.
- In conviction flow, jailed state is transient:
- EFJ present: EFJ auto-uses immediately and the player remains active.
- EFJ absent: player is eliminated to Dead/Ghost immediately.

## Dead/Ghost
- Dead players can observe the full player state in real time.
- Dead players may not communicate with living players.
- Moderator may silence dead players or disable their view if needed.

## Open Discussion

- Q1: Define liquidation value method for offline-death item conversion (purchase price, current moderator price, or fixed table).
Response:
