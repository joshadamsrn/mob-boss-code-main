import sys
import unittest
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
                role_name="Police Chief",
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
                life_state="alive",
                money_balance=300,
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
        self.assertEqual(own_row.role_label, "Police / Police Chief (1)")
        self.assertEqual(other_row.role_label, "Hidden")
        self.assertFalse(page.can_report_death)

    def test_moderator_view_shows_full_roles_and_sanitized_trial_data(self) -> None:
        page = build_gameplay_page_view(_snapshot(), "u_mod")

        self.assertTrue(page.is_moderator)
        mob_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        self.assertEqual(mob_row.role_label, "Mob / Mob Boss (1)")
        self.assertIsNotNone(page.pending_trial)
        self.assertEqual(page.pending_trial.current_responder_user_id, "u_police")
        self.assertEqual(page.pending_trial.murdered_user_id, "u_x")

    def test_non_participant_player_is_rejected(self) -> None:
        with self.assertRaises(PermissionError):
            build_gameplay_page_view(_snapshot(), "u_outsider")


if __name__ == "__main__":
    unittest.main()
