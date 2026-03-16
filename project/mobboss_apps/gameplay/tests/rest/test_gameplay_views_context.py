import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.gameplay.ports.internal import (  # noqa: E402
    CatalogItemStateSnapshot,
    GameDetailsSnapshot,
    ParticipantStateSnapshot,
)
from project.mobboss_apps.gameplay.views import detail  # noqa: E402


def _snapshot() -> GameDetailsSnapshot:
    return GameDetailsSnapshot(
        game_id="g-ctx",
        room_id="r-ctx",
        moderator_user_id="u_mod",
        status="in_progress",
        phase="information",
        round_number=1,
        version=1,
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
        pending_trial=None,
    )


class _StubGameplayInboundPort:
    def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
        return _snapshot()


class _StubContainer:
    def __init__(self) -> None:
        self.gameplay_inbound_port = _StubGameplayInboundPort()
        self.room_state_poll_interval_seconds = 5


class GameplayHtmlContextTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.container = _StubContainer()
        self.player = type("U", (), {"is_authenticated": True, "id": "u_police", "username": "police"})()
        self.moderator = type("U", (), {"is_authenticated": True, "id": "u_mod", "username": "moderator"})()

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_player_context_uses_sanitized_page_dto(self, mock_render, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-ctx")
        request.user = self.player

        response = detail(request, game_id="g-ctx")

        self.assertEqual(response.status_code, 200)
        self.assertIn("page", captured_context)
        self.assertNotIn("game", captured_context)
        page = captured_context["page"]
        self.assertFalse(page.is_moderator)
        self.assertIsNone(page.pending_trial)
        own_row = next(row for row in page.participant_rows if row.user_id == "u_police")
        other_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        self.assertEqual(own_row.role_label, "Police / Police Chief (1)")
        self.assertEqual(other_row.role_label, "Hidden")

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_moderator_context_exposes_moderator_page_dto(self, mock_render, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-ctx")
        request.user = self.moderator

        response = detail(request, game_id="g-ctx")

        self.assertEqual(response.status_code, 200)
        page = captured_context["page"]
        self.assertTrue(page.is_moderator)
        mob_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        self.assertEqual(mob_row.role_label, "Mob / Mob Boss (1)")


if __name__ == "__main__":
    unittest.main()
