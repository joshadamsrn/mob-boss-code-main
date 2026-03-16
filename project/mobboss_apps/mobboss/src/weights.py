"""Authoritative system default weights for Mob Boss.

These values are code-level defaults and must be the source of truth for runtime
configuration unless explicitly overridden by room/game configuration.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Weights:
    circulating_currency_per_player: int = 100

    merchant_total_percent: int = 40
    police_total_percent: int = 50
    mob_total_percent: int = 10

    merchant_single_cap_percent: int = 20
    single_merchant_extra_to_police_percent: int = 15
    single_merchant_extra_to_mob_percent: int = 5

    police_chief_bonus_over_single_merchant_percent: int = 5
    mob_boss_percent: int = 5
    knife_hobo_percent: int = 0
    merchant_goal_additional_percent: int = 40

    police_kill_limit_percent_of_mob: int = 50
    police_kill_limit_uses_initial_mob_count: bool = True
    police_kill_limit_round_max: int = 1

    jury_fraction_of_living_players: float = 0.25
    jury_min_size: int = 3
    jury_must_be_odd: bool = True

    # Merchant counts by total player count range.
    merchant_count_7_9: int = 1
    merchant_count_10_13: int = 2
    merchant_count_14_17: int = 3
    merchant_count_18_21: int = 4
    merchant_count_22_25: int = 5

    role_split_extra_player_to_police: bool = True

    # Economy operations.
    moderator_can_adjust_supply_prices_midgame: bool = True

    # Timing defaults (seconds).
    accused_selection_timeout_seconds: int = 15
    jury_vote_timeout_seconds: int = 10
    polling_interval_seconds: int = 5


DEFAULT_WEIGHTS = Weights()
