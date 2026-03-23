from __future__ import annotations

import unittest

from project.mobboss_apps.mobboss.src.starting_money import (
    MAX_SUPPORTED_PLAYER_COUNT,
    MIN_SUPPORTED_PLAYER_COUNT,
    STARTING_MONEY_BY_PLAYER_COUNT,
    getStartingMoney,
)


class StartingMoneyTests(unittest.TestCase):
    def test_returns_exact_table_value(self) -> None:
        self.assertEqual(getStartingMoney(7, "Chief of Police"), 240)
        self.assertEqual(getStartingMoney(14, "Merchant"), 260)
        self.assertEqual(getStartingMoney(25, "Arms Dealer"), 180)

    def test_merchant_is_always_arms_dealer_plus_100(self) -> None:
        for player_count, role_values in STARTING_MONEY_BY_PLAYER_COUNT.items():
            self.assertEqual(role_values["Merchant"], role_values["Arms Dealer"] + 100)
            self.assertEqual(getStartingMoney(player_count, "Merchant"), getStartingMoney(player_count, "Arms Dealer") + 100)

    def test_rejects_unsupported_player_count(self) -> None:
        with self.assertRaises(ValueError):
            getStartingMoney(MIN_SUPPORTED_PLAYER_COUNT - 1, "Merchant")
        with self.assertRaises(ValueError):
            getStartingMoney(MAX_SUPPORTED_PLAYER_COUNT + 1, "Merchant")

    def test_rejects_unsupported_role(self) -> None:
        with self.assertRaises(ValueError):
            getStartingMoney(7, "Not A Role")


if __name__ == "__main__":
    unittest.main()
