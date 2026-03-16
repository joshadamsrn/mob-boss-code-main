# Roles and Hierarchy

## Police Hierarchy
1. Police Chief
2. Deputy
3. Detective 1
4. Detective 2 (and so on)

Succession:
- If Police Chief is eliminated, the next highest-ranking Police becomes Police Chief.
- Role and responsibilities transfer immediately.
- Hierarchy shifts upward.

## Mob Hierarchy
1. Mob Boss
2. Mob Member 1
3. Mob Member 2 (and so on)
4. Knife Hobo (always lowest rank)

Succession:
- If Mob Boss is eliminated, next Mob Member becomes Mob Boss.

## Merchants
- Independent players with solo win condition.

## Role Counts by Player Count (Authoritative v1)
- Rule:
- Merchant count uses the existing merchant table.
- Remaining players split between Police and Mob.
- If split is odd, the extra player goes to Police.
- Formula:
- police_count = ceil((N - merchants_count) / 2)
- mob_count = floor((N - merchants_count) / 2)

| Players | Merchants | Police | Mob |
|---|---:|---:|---:|
| 7 | 1 | 3 | 3 |
| 8 | 1 | 4 | 3 |
| 9 | 1 | 4 | 4 |
| 10 | 2 | 4 | 4 |
| 11 | 2 | 5 | 4 |
| 12 | 2 | 5 | 5 |
| 13 | 2 | 6 | 5 |
| 14 | 3 | 6 | 5 |
| 15 | 3 | 6 | 6 |
| 16 | 3 | 7 | 6 |
| 17 | 3 | 7 | 7 |
| 18 | 4 | 7 | 7 |
| 19 | 4 | 8 | 7 |
| 20 | 4 | 8 | 8 |
| 21 | 4 | 9 | 8 |
| 22 | 5 | 9 | 8 |
| 23 | 5 | 9 | 9 |
| 24 | 5 | 10 | 9 |
| 25 | 5 | 10 | 10 |

## Role Composition
- Faction names are canonical: `Police`, `Mob`, `Merchant`.
- Police roles: 1 Chief, 1 Deputy, remaining as Detectives.
- Mob roles: 1 Boss, 1 Knife Hobo, remaining as Mob Members.

## Open Discussion

- Q1: Should any player-count ranges use non-even split overrides for balance (for example 14, 18, 22)?
Response:

- Q2: Should Detectives be named numerically only (Detective 1, 2, 3) or support custom aliases?
Response:
