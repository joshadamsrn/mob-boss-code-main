import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.rooms.views import launch_game, set_mob_secret_word  # noqa: E402


class _StubRoomsInboundPort:
    def __init__(self, game_id: str = "g-1") -> None:
        self.game_id = game_id
        self.last_secret_word = None
        self.launch_commands = []

    def launch_game_from_room(self, command) -> str:
        self.launch_commands.append(command)
        return self.game_id

    def set_mob_secret_word(self, command):
        self.last_secret_word = command.secret_mob_word
        return None


class _StubContainer:
    def __init__(self, rooms_inbound_port: _StubRoomsInboundPort) -> None:
        self.rooms_inbound_port = rooms_inbound_port
        self.rooms_outbound_port = object()
        self.gameplay_inbound_port = object()
        self.room_dev_mode = False


class RoomLaunchViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = type("U", (), {"is_authenticated": True, "id": "u_mod", "username": "moderator"})()
        self.dev_user = type(
            "U",
            (),
            {"is_authenticated": True, "id": "u_dev", "username": "devmode", "is_dev_tools_user": True},
        )()

    def _attach_session(self, request) -> None:
        request.session = {}

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
        self._attach_session(request)

        response = launch_game(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/games/game-123/")
        self.assertEqual(request.session["active_game_id"], "game-123")
        self.assertEqual(request.session["active_room_id"], "r-1")
        self.assertEqual(len(mock_get_container.return_value.rooms_inbound_port.launch_commands), 1)

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    @patch("project.mobboss_apps.rooms.views.get_container")
    def test_set_mob_secret_word_posts_to_room_detail(
        self,
        mock_get_container,
        _mock_success,
        _mock_error,
    ) -> None:
        stub = _StubRoomsInboundPort(game_id="game-123")
        mock_get_container.return_value = _StubContainer(stub)
        request = self.factory.post("/rooms/r-1/set-mob-secret-word", data={"secret_mob_word": "RAVEN"})
        request.user = self.user

        response = set_mob_secret_word(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/rooms/r-1/")
        self.assertEqual(stub.last_secret_word, "RAVEN")

    @patch("project.mobboss_apps.rooms.views.RoomsService")
    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    @patch("project.mobboss_apps.rooms.views.get_container")
    def test_dev_tools_user_launch_uses_dev_launch_player_floor_when_room_dev_mode_disabled(
        self,
        mock_get_container,
        _mock_success,
        _mock_error,
        mock_rooms_service,
    ) -> None:
        stub = _StubRoomsInboundPort(game_id="game-456")
        mock_get_container.return_value = _StubContainer(stub)
        mock_rooms_service.return_value = stub
        request = self.factory.post("/rooms/r-1/launch")
        request.user = self.dev_user
        self._attach_session(request)

        response = launch_game(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/games/game-456/")
        self.assertEqual(mock_rooms_service.call_args.kwargs["minimum_launch_players"], 2)


if __name__ == "__main__":
    unittest.main()
