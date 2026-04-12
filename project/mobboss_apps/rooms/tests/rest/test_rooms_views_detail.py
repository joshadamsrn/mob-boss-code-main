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
from project.mobboss_apps.rooms.views import assign_role, detail  # noqa: E402


def _room_snapshot(
    *,
    moderator_user_id: str = "u_mod",
    moderator_username: str = "moderator",
) -> RoomDetailsSnapshot:
    return RoomDetailsSnapshot(
        room_id="r-1",
        name="Room 1",
        status="lobby",
        moderator_user_id=moderator_user_id,
        opened_at_epoch_seconds=0,
        members=[
            RoomMemberSnapshot(
                user_id=moderator_user_id,
                username=moderator_username,
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
        self.assigned_role_commands = []

    def get_room_details(self, _room_id: str) -> RoomDetailsSnapshot:
        return self._room

    def assign_room_role(self, command) -> RoomDetailsSnapshot:
        self.assigned_role_commands.append(command)
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
        self.dev_user = type(
            "StubDevUser",
            (),
            {"is_authenticated": True, "id": "u_dev", "username": "devmode", "is_dev_tools_user": True},
        )()

    def test_moderator_can_see_central_supply_catalog(self) -> None:
        request = self.factory.get("/rooms/r-1/")
        request.user = self.moderator_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=_StubContainer(_room_snapshot())):
            response = detail(request, room_id="r-1")

        content = response.content.decode("utf-8")

        self.assertIn("Moderator: moderator", content)
        self.assertNotIn("Moderator: u_mod", content)
        self.assertContains(response, "Catalog (1)")
        self.assertIn("Items currently in Central Supply.", content)
        self.assertNotIn("Role: Lieutenant", content)
        self.assertNotIn('action="/rooms/r-1/assign-role"', content)

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

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    def test_assign_role_rejected_when_dev_mode_disabled(self, _mock_success, _mock_error) -> None:
        room = _room_snapshot()
        container = _StubContainer(room)
        request = self.factory.post(
            "/rooms/r-1/assign-role",
            data={"target_user_id": "u_1", "role_name": "Deputy"},
        )
        request.user = self.moderator_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=container):
            response = assign_role(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/rooms/r-1/")
        self.assertEqual(container.rooms_inbound_port.assigned_role_commands, [])
        _mock_error.assert_called_once_with(request, "Role assignment is only available in dev mode.")

    def test_dev_tools_user_sees_dev_controls_when_room_dev_mode_disabled(self) -> None:
        request = self.factory.get("/rooms/r-1/")
        request.user = self.dev_user
        container = _StubContainer(_room_snapshot(moderator_user_id="u_dev", moderator_username="devmode"))

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=container):
            response = detail(request, room_id="r-1")

        content = response.content.decode("utf-8")

        self.assertIn("Add Dev Seat", content)
        self.assertIn("Mark All Ready", content)
        self.assertIn("Dev View Tabs", content)
        self.assertIn("Min: 1/2", content)

    @patch("project.mobboss_apps.rooms.views.list_room_supply_presets_for_user")
    def test_moderator_sees_presets_button_when_saved_presets_exist(self, mock_list_presets) -> None:
        mock_list_presets.return_value = [
            {
                "id": 1,
                "name": "Standard Setup",
                "updated_at": "2026-04-11T00:00:00",
                "counts": {"tier_1_gun_count": 1, "tier_2_gun_count": 1, "tier_3_gun_count": 0, "knife_count": 2},
                "rows": [],
            }
        ]
        request = self.factory.get("/rooms/r-1/")
        request.user = self.moderator_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=_StubContainer(_room_snapshot())):
            response = detail(request, room_id="r-1")

        self.assertContains(response, 'id="openCentralSupplyPresets"', html=False)

    def test_moderator_hides_presets_button_when_no_presets_exist(self) -> None:
        request = self.factory.get("/rooms/r-1/")
        request.user = self.moderator_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=_StubContainer(_room_snapshot())):
            response = detail(request, room_id="r-1")

        self.assertNotContains(response, 'id="openCentralSupplyPresets"', html=False)

    @patch("project.mobboss_apps.rooms.views.messages.error")
    @patch("project.mobboss_apps.rooms.views.messages.success")
    def test_dev_tools_user_can_assign_role_when_room_dev_mode_disabled(self, _mock_success, _mock_error) -> None:
        room = _room_snapshot(moderator_user_id="u_dev", moderator_username="devmode")
        container = _StubContainer(room)
        request = self.factory.post(
            "/rooms/r-1/assign-role",
            data={"target_user_id": "u_1", "role_name": "Deputy"},
        )
        request.user = self.dev_user

        with patch("project.mobboss_apps.rooms.views.get_container", return_value=container):
            response = assign_role(request, room_id="r-1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/rooms/r-1/")
        self.assertEqual(len(container.rooms_inbound_port.assigned_role_commands), 1)


if __name__ == "__main__":
    unittest.main()
