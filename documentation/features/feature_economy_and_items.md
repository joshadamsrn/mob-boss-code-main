# feature_economy_and_items

## Goal
Define economic invariants, item money destinations, pricing authority, and liquidation.

## Rules
- Money cannot leave the game economy.
- Circulating currency baseline: players * 100.
- Monetary rounding: nearest 10, ties at 5 round up.
- Central supply baseline prices are moderator-controlled.
- Moderator may adjust baseline prices at game start and during game.
- Merchant net worth = money_balance + sum(acquisition_value of unsold inventory).
- Unsold inventory equity uses purchase price, not listed markup.
- Vest block outcome: vest consumed, no trial, vest value transfers to attacker anonymously.
- EFJ purchase value transfers to a random Police player (Chief/Deputy/Detective eligible).
- Offline-death liquidation uses purchase price, items return to supply, value distributes evenly to faction.

## Invariants
- Ledger should be reconcilable to prove no value leak.

## Open Items
- Destination rule when faction has zero eligible recipients.
