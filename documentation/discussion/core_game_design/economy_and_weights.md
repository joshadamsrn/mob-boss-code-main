# Economy and Weights

## Terminology
- Use "circulating currency" instead of "GDP".

## Total Circulating Currency
- Total = number of players x 100.
- All monetary values must be rounded to the nearest 10.
- Rounding rule: values ending in 5 round up; values below 5 round down.

## Team Splits
- Merchants: total 40% of circulating currency, divided across merchants.
- Police: total 50% of circulating currency.
- Mob: total 10% of circulating currency.

Special constraints:
- No single Merchant starts with more than 20% of total circulating currency.
- If only 1 Merchant: remaining 20% is split 15% to Police and 5% to Mob.

## Police Starting Money
- Police Chief: 5% more than a single Merchant starting amount.
- Police Deputy: same as a single Merchant starting amount.
- Remaining Police split the rest of Police total.

## Mob Starting Money
- Mob Boss: 5% of circulating currency.
- Knife Hobo: 0%.
- Remaining Mob split the remainder of Mob total.

## Merchant Goal
- Merchant goal = Merchant starting money + 40% of total circulating currency.

## Merchant Count by Player Count
- 7-9 players: 1 Merchant
- 10-13 players: 2 Merchants
- 14-17 players: 3 Merchants
- 18-21 players: 4 Merchants
- 22-25 players: 5 Merchants

## Faction Count Rule by Player Count
- Remaining players after Merchant assignment split between Police and Mob.
- If odd, extra player goes to Police.
- police_count = ceil((N - merchants_count) / 2)
- mob_count = floor((N - merchants_count) / 2)

## Removal by Moderator (Liquidation)
- If a player is removed by the Moderator, items are liquidated and returned to central supply.
- The money value is evenly distributed among the removed player's team.

## Pricing Authority
- Central supply prices are set by Moderator.
- Moderator may adjust baseline item prices at game start.
- Moderator may adjust baseline item prices during game for balance/velocity.
- Merchant purchase value for an item is the price paid at acquisition time.
- Merchant equity uses acquisition value for unsold inventory (not current markup/list price).
- Merchant net worth = current money_balance + sum(acquisition_value of unsold inventory).
- Merchant resale markup affects net worth only when a sale is completed.

## Adjustable Weights (Authoritative)
- circulating_currency_per_player = 100
- merchant_total_percent = 40
- police_total_percent = 50
- mob_total_percent = 10
- merchant_single_cap_percent = 20
- single_merchant_extra_to_police_percent = 15
- single_merchant_extra_to_mob_percent = 5
- police_chief_bonus_over_single_merchant_percent = 5
- mob_boss_percent = 5
- knife_hobo_percent = 0
- merchant_goal_additional_percent = 40
- police_kill_limit_percent_of_mob = 50
- police_kill_limit_uses_initial_mob_count = true
- police_kill_limit_round_max = 1
- jury_fraction_of_living_players = 0.25
- jury_min_size = 3
- jury_must_be_odd = true
- merchant_count_7_9 = 1
- merchant_count_10_13 = 2
- merchant_count_14_17 = 3
- merchant_count_18_21 = 4
- merchant_count_22_25 = 5
- role_split_extra_player_to_police = true
- moderator_can_adjust_supply_prices_midgame = true

## Open Discussion

- Q1: Define stash outcomes for trial-based transfers when the murderer is identified or misidentified.
Response:
