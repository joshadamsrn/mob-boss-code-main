import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.rooms.views import create_room  # noqa: E402


class _StubRoomsInboundPort:
    def __init__(self) -> None:
        self.create_commands = []

    def create_room(self, command):
        self.create_commands.append(command)
        return type("RoomSummary", (), {"room_id": "r-123"})()


class _StubContainer:
    def __init__(self) -> None:
        self.rooms_inbound_port = _StubRoomsInboundPort()


class RoomCreateViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = type("StubUser", (), {"is_authenticated": True, "id": "u_mod", "username": "moderator"})()

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    @patch("project.mobboss_apps.rooms.views.get_container")
    @patch("project.mobboss_apps.rooms.views.grant_moderator_access")
    @patch("project.mobboss_apps.rooms.views.moderator_access_code_is_valid", return_value=False)
    @patch("project.mobboss_apps.rooms.views.user_can_create_moderated_room", return_value=False)
    def test_create_room_rejects_user_without_valid_permission_code(
        self,
        _mock_user_can_create,
        _mock_code_is_valid,
        mock_grant_access,
        mock_get_container,
        _mock_success,
        mock_error,
    ) -> None:
        container = _StubContainer()
        mock_get_container.return_value = container
        request = self.factory.post("/rooms/create", data={"name": "Test Room", "moderator_access_code": "wrong"})
        request.user = self.user

        response = create_room(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")
        self.assertEqual(container.rooms_inbound_port.create_commands, [])
        mock_grant_access.assert_not_called()
        mock_error.assert_called_once_with(request, "Valid moderator permission code required to create a room.")

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    @patch("project.mobboss_apps.rooms.views.get_container")
    @patch("project.mobboss_apps.rooms.views.grant_moderator_access", return_value=True)
    @patch("project.mobboss_apps.rooms.views.moderator_access_code_is_valid", return_value=True)
    @patch("project.mobboss_apps.rooms.views.user_can_create_moderated_room", return_value=False)
    def test_create_room_grants_access_and_creates_room_when_code_is_valid(
        self,
        _mock_user_can_create,
        _mock_code_is_valid,
        mock_grant_access,
        mock_get_container,
        mock_success,
        _mock_error,
    ) -> None:
        container = _StubContainer()
        mock_get_container.return_value = container
        request = self.factory.post("/rooms/create", data={"name": "Test Room", "moderator_access_code": "adamspham"})
        request.user = self.user

        response = create_room(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/rooms/r-123/")
        self.assertEqual(len(container.rooms_inbound_port.create_commands), 1)
        mock_grant_access.assert_called_once_with(self.user)
        mock_success.assert_called_once_with(request, "Room created.")

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    @patch("project.mobboss_apps.rooms.views.get_container")
    @patch("project.mobboss_apps.rooms.views.grant_moderator_access")
    @patch("project.mobboss_apps.rooms.views.moderator_access_code_is_valid")
    @patch("project.mobboss_apps.rooms.views.user_can_create_moderated_room", return_value=True)
    def test_create_room_skips_permission_code_for_returning_authorized_user(
        self,
        _mock_user_can_create,
        mock_code_is_valid,
        mock_grant_access,
        mock_get_container,
        mock_success,
        _mock_error,
    ) -> None:
        container = _StubContainer()
        mock_get_container.return_value = container
        request = self.factory.post("/rooms/create", data={"name": "Test Room"})
        request.user = self.user

        response = create_room(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/rooms/r-123/")
        self.assertEqual(len(container.rooms_inbound_port.create_commands), 1)
        mock_code_is_valid.assert_not_called()
        mock_grant_access.assert_not_called()
        mock_success.assert_called_once_with(request, "Room created.")


if __name__ == "__main__":
    unittest.main()
