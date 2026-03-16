import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.rooms.views import launch_game  # noqa: E402


class _StubRoomsInboundPort:
    def __init__(self, game_id: str = "g-1") -> None:
        self.game_id = game_id

    def launch_game_from_room(self, _command) -> str:
        return self.game_id


class _StubContainer:
    def __init__(self, rooms_inbound_port: _StubRoomsInboundPort) -> None:
        self.rooms_inbound_port = rooms_inbound_port


class RoomLaunchViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = type("U", (), {"is_authenticated": True, "id": "u_mod", "username": "moderator"})()

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    @patch("project.mobboss_apps.rooms.views.get_container")
    def test_launch_redirects_to_gameplay_detail_on_success(
        self,
        mock_get_container,
        _mock_success,
        _mock_error,
    ) -> None:
        mock_get_container.return_value = _StubContainer(_StubRoomsInboundPort(game_id="game-123"))
        request = self.factory.post("/rooms/r-1/launch")
        request.user = self.user

        response = launch_game(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/games/game-123/")


if __name__ == "__main__":
    unittest.main()
