import sys
import unittest
from dataclasses import replace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.gameplay.adapters.internal.page_view_mapper import (  # noqa: E402
    build_gameplay_page_view,
)
from project.mobboss_apps.gameplay.ports.internal import (  # noqa: E402
    CatalogItemStateSnapshot,
    GameDetailsSnapshot,
    InventoryItemStateSnapshot,
    LedgerStateSnapshot,
    ParticipantStateSnapshot,
    TrialStateSnapshot,
)


def _snapshot() -> GameDetailsSnapshot:
    return GameDetailsSnapshot(
        game_id="g-1",
        room_id="r-1",
        moderator_user_id="u_mod",
        status="in_progress",
        phase="accused_selection",
        round_number=1,
        version=2,
        launched_at_epoch_seconds=100,
        ended_at_epoch_seconds=None,
        participants=[
            ParticipantStateSnapshot(
                user_id="u_police",
                username="police",
                faction="Police",
                role_name="Chief of Police",
                rank=1,
                life_state="alive",
                money_balance=300,
                inventory=[
                    InventoryItemStateSnapshot(
                        item_id="inv-1",
                        classification="knife",
                        display_name="Knife",
                        image_path="/static/items/defaults/default_knife.svg",
                        acquisition_value=100,
                        resale_price=100,
                    )
                ],
            ),
            ParticipantStateSnapshot(
                user_id="u_mob",
                username="mob",
                faction="Mob",
                role_name="Mob Boss",
                rank=1,
                life_state="alive",
                money_balance=300,
                inventory=[],
            ),
        ],
        catalog=[
            CatalogItemStateSnapshot(
                classification="knife",
                display_name="Knife",
                base_price=100,
                image_path="/static/items/defaults/default_knife.svg",
                is_active=True,
            )
        ],
        pending_trial=TrialStateSnapshot(
            murdered_user_id="u_x",
            murderer_user_id="u_secret",
            accused_user_id=None,
            accused_selection_cursor=["u_police"],
            accused_selection_deadline_epoch_seconds=123,
            jury_user_ids=[],
            vote_deadline_epoch_seconds=None,
            votes=[],
            verdict=None,
            conviction_correct=None,
            resolution=None,
        ),
    )


class GameplayPageViewMapperTests(unittest.TestCase):
    def test_player_view_hides_other_roles_and_does_not_expose_pending_trial(self) -> None:
        page = build_gameplay_page_view(_snapshot(), "u_police")

        self.assertFalse(page.is_moderator)
        self.assertIsNone(page.pending_trial)
        own_row = next(row for row in page.participant_rows if row.user_id == "u_police")
        other_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        self.assertEqual(own_row.role_label, "Faction: Police / Role: Chief of Police")
        self.assertEqual(other_row.role_label, "Hidden")
        self.assertFalse(page.can_report_death)

    def test_moderator_view_shows_full_roles_and_sanitized_trial_data(self) -> None:
        page = build_gameplay_page_view(_snapshot(), "u_mod")

        self.assertTrue(page.is_moderator)
        mob_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        self.assertEqual(mob_row.role_label, "Faction: Mob / Role: Mob Boss")
        police_row = next(row for row in page.participant_rows if row.user_id == "u_police")
        self.assertEqual(police_row.inventory_text, "Knife")
        self.assertEqual(police_row.money_balance, 300)
        self.assertIsNotNone(page.pending_trial)
        self.assertEqual(page.pending_trial.current_responder_user_id, "u_police")
        self.assertEqual(page.pending_trial.murdered_user_id, "u_x")

    def test_player_view_reveals_all_roles_after_game_has_ended(self) -> None:
        ended_snapshot = GameDetailsSnapshot(
            game_id="g-1",
            room_id="r-1",
            moderator_user_id="u_mod",
            status="ended",
            phase="ended",
            round_number=1,
            version=3,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=150,
            participants=_snapshot().participants,
            catalog=_snapshot().catalog,
            pending_trial=None,
            winning_faction="Police",
        )

        page = build_gameplay_page_view(ended_snapshot, "u_police")

        own_row = next(row for row in page.participant_rows if row.user_id == "u_police")
        other_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        self.assertEqual(own_row.role_label, "Faction: Police / Role: Chief of Police")
        self.assertEqual(other_row.role_label, "Faction: Mob / Role: Mob Boss")

    def test_non_participant_player_is_rejected(self) -> None:
        with self.assertRaises(PermissionError):
            build_gameplay_page_view(_snapshot(), "u_outsider")

    def test_trial_voting_marks_accused_participant_as_on_trial(self) -> None:
        trial_snapshot = GameDetailsSnapshot(
            game_id="g-1",
            room_id="r-1",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="trial_voting",
            round_number=1,
            version=2,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=_snapshot().participants,
            catalog=_snapshot().catalog,
            pending_trial=TrialStateSnapshot(
                murdered_user_id="u_x",
                murderer_user_id="u_secret",
                accused_user_id="u_mob",
                accused_selection_cursor=[],
                accused_selection_deadline_epoch_seconds=None,
                jury_user_ids=["u_police"],
                vote_deadline_epoch_seconds=1234,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution=None,
            ),
        )
        page = build_gameplay_page_view(trial_snapshot, "u_mod")
        mob_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        police_row = next(row for row in page.participant_rows if row.user_id == "u_police")
        self.assertEqual(mob_row.status_label, "on_trial")
        self.assertTrue(police_row.is_juror)

    def test_moderator_view_shows_murder_and_conviction_attribution(self) -> None:
        attribution_snapshot = GameDetailsSnapshot(
            game_id="g-1",
            room_id="r-1",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=2,
            version=3,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_police",
                    username="police",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob",
                    username="mob",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="dead",
                    money_balance=0,
                    murdered_by_user_id="u_police",
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    life_state="jailed",
                    money_balance=260,
                    accused_by_user_id="u_police",
                    convicted_by_user_ids=["u_police"],
                ),
            ],
            catalog=_snapshot().catalog,
            pending_trial=None,
        )
        page = build_gameplay_page_view(attribution_snapshot, "u_mod")
        dead_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        jailed_row = next(row for row in page.participant_rows if row.user_id == "u_merchant")
        self.assertEqual(dead_row.murdered_by_username, "police")
        self.assertEqual(jailed_row.accused_by_username, "police")
        self.assertEqual(jailed_row.convicted_by_label, "police")

    def test_moderator_view_keeps_merchant_goal_fixed_from_baseline(self) -> None:
        baseline = 1000
        snapshot_a = GameDetailsSnapshot(
            game_id="g-1",
            room_id="r-1",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=1,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_merchant",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police",
                    username="police",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=700,
                ),
            ],
            catalog=[],
            pending_trial=None,
            ledger=LedgerStateSnapshot(circulating_currency_baseline=baseline),
        )
        snapshot_b = replace(
            snapshot_a,
            participants=[
                replace(snapshot_a.participants[0], money_balance=620),
                replace(snapshot_a.participants[1], money_balance=180),
            ],
        )

        page_a = build_gameplay_page_view(snapshot_a, "u_mod")
        page_b = build_gameplay_page_view(snapshot_b, "u_mod")
        goal_a = next(row for row in page_a.participant_rows if row.user_id == "u_merchant").merchant_money_goal
        goal_b = next(row for row in page_b.participant_rows if row.user_id == "u_merchant").merchant_money_goal
        self.assertIsNotNone(goal_a)
        self.assertEqual(goal_a, goal_b)


if __name__ == "__main__":
    unittest.main()
