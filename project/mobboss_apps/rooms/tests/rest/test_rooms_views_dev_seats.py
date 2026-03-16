import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.rooms.ports.internal import (  # noqa: E402
    RoomDetailsSnapshot,
    RoomMemberSnapshot,
)
from project.mobboss_apps.rooms.views import add_dev_seat, remove_dev_seat  # noqa: E402


def _room_snapshot(*, moderator_user_id: str = "u_mod") -> RoomDetailsSnapshot:
    return RoomDetailsSnapshot(
        room_id="r-1",
        name="Room 1",
        status="lobby",
        moderator_user_id=moderator_user_id,
        opened_at_epoch_seconds=0,
        members=[
            RoomMemberSnapshot(
                user_id=moderator_user_id,
                username="moderator",
                membership_status="joined",
                is_ready=True,
                starting_balance=0,
                assigned_role=None,
            ),
            RoomMemberSnapshot(
                user_id="dev-seat-01",
                username="Dev Seat 01",
                membership_status="joined",
                is_ready=False,
                starting_balance=0,
                assigned_role=None,
            ),
        ],
        items=[],
    )


class _StubRoomsInboundPort:
    def __init__(self, room: RoomDetailsSnapshot) -> None:
        self._room = room
        self.join_commands = []
        self.leave_commands = []

    def get_room_details(self, room_id: str) -> RoomDetailsSnapshot:
        return self._room

    def join_room(self, command) -> RoomDetailsSnapshot:
        self.join_commands.append(command)
        return self._room

    def leave_room(self, command) -> RoomDetailsSnapshot:
        self.leave_commands.append(command)
        return self._room


class _StubContainer:
    def __init__(self, *, room_dev_mode: bool, rooms_inbound_port: _StubRoomsInboundPort) -> None:
        self.room_dev_mode = room_dev_mode
        self.rooms_inbound_port = rooms_inbound_port


class RoomDevSeatEndpointTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.moderator_user = type(
            "StubModerator",
            (),
            {"is_authenticated": True, "id": "u_mod", "username": "moderator"},
        )()
        self.participant_user = type(
            "StubParticipant",
            (),
            {"is_authenticated": True, "id": "u_1", "username": "p1"},
        )()

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    def test_add_dev_seat_requires_moderator(self, _mock_success, _mock_error) -> None:
        inbound = _StubRoomsInboundPort(_room_snapshot())
        container = _StubContainer(room_dev_mode=True, rooms_inbound_port=inbound)
        request = self.factory.post("/rooms/r-1/dev/add-seat", data={"seat_name": "Seat"})
        request.user = self.participant_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=container):
            response = add_dev_seat(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/rooms/r-1/")
        self.assertEqual(len(inbound.join_commands), 0)

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    def test_add_dev_seat_requires_dev_mode(self, _mock_success, _mock_error) -> None:
        inbound = _StubRoomsInboundPort(_room_snapshot())
        container = _StubContainer(room_dev_mode=False, rooms_inbound_port=inbound)
        request = self.factory.post("/rooms/r-1/dev/add-seat", data={"seat_name": "Seat"})
        request.user = self.moderator_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=container):
            response = add_dev_seat(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/rooms/r-1/")
        self.assertEqual(len(inbound.join_commands), 0)

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    def test_add_dev_seat_uses_next_incrementing_dev_seat_id(self, _mock_success, _mock_error) -> None:
        inbound = _StubRoomsInboundPort(_room_snapshot())
        container = _StubContainer(room_dev_mode=True, rooms_inbound_port=inbound)
        request = self.factory.post("/rooms/r-1/dev/add-seat", data={"seat_name": "Seat Two"})
        request.user = self.moderator_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=container):
            response = add_dev_seat(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(inbound.join_commands), 1)
        self.assertEqual(inbound.join_commands[0].user_id, "dev-seat-02")
        self.assertEqual(inbound.join_commands[0].username, "Seat Two")

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    def test_remove_dev_seat_requires_moderator(self, _mock_success, _mock_error) -> None:
        inbound = _StubRoomsInboundPort(_room_snapshot())
        container = _StubContainer(room_dev_mode=True, rooms_inbound_port=inbound)
        request = self.factory.post("/rooms/r-1/dev/remove-seat", data={"user_id": "dev-seat-01"})
        request.user = self.participant_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=container):
            response = remove_dev_seat(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(inbound.leave_commands), 0)

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    def test_remove_dev_seat_rejects_non_dev_target(self, _mock_success, _mock_error) -> None:
        inbound = _StubRoomsInboundPort(_room_snapshot())
        container = _StubContainer(room_dev_mode=True, rooms_inbound_port=inbound)
        request = self.factory.post("/rooms/r-1/dev/remove-seat", data={"user_id": "u_1"})
        request.user = self.moderator_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=container):
            response = remove_dev_seat(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(inbound.leave_commands), 0)

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    def test_remove_dev_seat_calls_leave_for_valid_dev_target(self, _mock_success, _mock_error) -> None:
        inbound = _StubRoomsInboundPort(_room_snapshot())
        container = _StubContainer(room_dev_mode=True, rooms_inbound_port=inbound)
        request = self.factory.post("/rooms/r-1/dev/remove-seat", data={"user_id": "dev-seat-01"})
        request.user = self.moderator_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=container):
            response = remove_dev_seat(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(inbound.leave_commands), 1)
        self.assertEqual(inbound.leave_commands[0].user_id, "dev-seat-01")


if __name__ == "__main__":
    unittest.main()
