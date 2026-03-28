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
    RoomItemSnapshot,
    RoomMemberSnapshot,
    RoomRoleAssignmentSnapshot,
)
from project.mobboss_apps.rooms.views import detail  # noqa: E402


def _room_snapshot() -> RoomDetailsSnapshot:
    return RoomDetailsSnapshot(
        room_id="r-1",
        name="Room 1",
        status="lobby",
        moderator_user_id="u_mod",
        opened_at_epoch_seconds=0,
        members=[
            RoomMemberSnapshot(
                user_id="u_mod",
                username="moderator",
                membership_status="joined",
                is_ready=True,
                starting_balance=0,
                assigned_role=None,
            ),
            RoomMemberSnapshot(
                user_id="u_1",
                username="player1",
                membership_status="joined",
                is_ready=True,
                starting_balance=100,
                assigned_role=RoomRoleAssignmentSnapshot(
                    faction="Police",
                    role_name="Lieutenant",
                    rank=4,
                ),
            ),
        ],
        items=[
            RoomItemSnapshot(
                classification="gun",
                display_name="Pocket Pistol",
                base_price=100,
                image_path="",
                is_active=True,
            )
        ],
    )


class _StubRoomsInboundPort:
    def __init__(self, room: RoomDetailsSnapshot) -> None:
        self._room = room

    def get_room_details(self, _room_id: str) -> RoomDetailsSnapshot:
        return self._room


class _StubRoomItemMediaOutboundPort:
    def resolve_room_item_tile_image_url(self, image_path: str) -> str:
        return image_path


class _StubContainer:
    def __init__(self, room: RoomDetailsSnapshot) -> None:
        self.rooms_inbound_port = _StubRoomsInboundPort(room)
        self.room_item_media_outbound_port = _StubRoomItemMediaOutboundPort()
        self.room_dev_mode = False
        self.room_min_launch_players = 7
        self.room_state_poll_interval_seconds = 5


class RoomDetailViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.moderator_user = type("StubModerator", (), {"is_authenticated": True, "id": "u_mod", "username": "moderator"})()
        self.player_user = type("StubPlayer", (), {"is_authenticated": True, "id": "u_1", "username": "player1"})()

    def test_moderator_can_see_central_supply_catalog(self) -> None:
        request = self.factory.get("/rooms/r-1/")
        request.user = self.moderator_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=_StubContainer(_room_snapshot())):
            response = detail(request, room_id="r-1")

        content = response.content.decode("utf-8")

        self.assertContains(response, "Catalog (1)")
        self.assertIn("Items currently in Central Supply.", content)
        self.assertIn("Role: Lieutenant", content)

    def test_non_moderator_cannot_see_central_supply_catalog(self) -> None:
        request = self.factory.get("/rooms/r-1/")
        request.user = self.player_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=_StubContainer(_room_snapshot())):
            response = detail(request, room_id="r-1")

        content = response.content.decode("utf-8")

        self.assertNotIn("Catalog (1)", content)
        self.assertNotIn("Items currently in Central Supply.", content)
        self.assertNotIn("Pocket Pistol", content)
        self.assertNotIn("Role: Lieutenant", content)


if __name__ == "__main__":
    unittest.main()
