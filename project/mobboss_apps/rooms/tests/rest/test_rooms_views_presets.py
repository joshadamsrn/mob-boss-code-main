import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import django
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.mobboss_apps.mobboss.settings")
django.setup()

from project.mobboss_apps.rooms.ports.internal import RoomDetailsSnapshot, RoomItemSnapshot, RoomMemberSnapshot  # noqa: E402
from project.mobboss_apps.rooms.views import overwrite_preset, rename_preset, save_catalog_as_preset  # noqa: E402
from rooms.models import RoomSupplyPreset  # noqa: E402


def _room_snapshot(*, moderator_user_id: str, items: list[RoomItemSnapshot] | None = None) -> RoomDetailsSnapshot:
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
        ],
        items=items or [],
    )


class _StubRoomsInboundPort:
    def __init__(self, room: RoomDetailsSnapshot) -> None:
        self._room = room

    def get_room_details(self, _room_id: str) -> RoomDetailsSnapshot:
        return self._room


class _StubRoomsOutboundPort:
    def __init__(self) -> None:
        self.saved_room = None

    def save_room(self, room: RoomDetailsSnapshot) -> None:
        self.saved_room = room


class _StubRoomItemMediaOutboundPort:
    def save_room_item_image(self, **kwargs) -> str:
        return f"/media/rooms/{kwargs['room_id']}/items/{kwargs['classification']}.jpg"

    def save_preset_item_image(self, **kwargs) -> str:
        return f"/media/presets/{kwargs['user_id']}/{kwargs['preset_id']}/items/{kwargs['classification']}.jpg"

    def clone_item_image_to_preset(self, **kwargs) -> str:
        return str(kwargs["source_image_path"])

    def resolve_room_item_tile_image_url(self, image_url: str) -> str:
        return image_url


class _StubContainer:
    def __init__(self, room: RoomDetailsSnapshot) -> None:
        self.rooms_inbound_port = _StubRoomsInboundPort(room)
        self.rooms_outbound_port = _StubRoomsOutboundPort()
        self.room_item_media_outbound_port = _StubRoomItemMediaOutboundPort()


class RoomPresetViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="presetmod", password="pw123456")

    @patch("project.mobboss_apps.rooms.views.get_container")
    def test_save_catalog_as_preset_creates_preset_and_replaces_room_catalog(self, mock_get_container) -> None:
        room = _room_snapshot(moderator_user_id=str(self.user.id))
        container = _StubContainer(room)
        mock_get_container.return_value = container
        request = self.factory.post(
            "/rooms/r-1/presets/save",
            data={
                "preset_name": "Tournament",
                "generated_rows": json.dumps(
                    [
                        {
                            "classification": "gun_tier_1_1",
                            "display_name": "Big Iron",
                            "base_price": 110,
                            "image_path": "/static/items/defaults/default_gun_tier_1.jpg",
                        },
                        {
                            "classification": "knife_1",
                            "display_name": "Knife 1",
                            "base_price": 120,
                            "image_path": "/static/items/defaults/default_knife.jpg",
                        },
                    ]
                ),
            },
        )
        request.user = self.user

        response = save_catalog_as_preset(request, room_id="r-1")
        body = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 201)
        self.assertTrue(body["ok"])
        preset = RoomSupplyPreset.objects.get(user=self.user, name="Tournament")
        self.assertEqual(preset.payload["counts"]["tier_1_gun_count"], 1)
        self.assertEqual(preset.payload["counts"]["knife_count"], 1)
        self.assertEqual(len(container.rooms_outbound_port.saved_room.items), 2)
        self.assertEqual(container.rooms_outbound_port.saved_room.items[0].display_name, "Big Iron")

    @patch("project.mobboss_apps.rooms.views.get_container")
    def test_overwrite_preset_uses_current_room_items_when_generated_rows_missing(self, mock_get_container) -> None:
        preset = RoomSupplyPreset.objects.create(
            user=self.user,
            name="Standard",
            payload={"version": 1, "counts": {}, "rows": []},
        )
        room = _room_snapshot(
            moderator_user_id=str(self.user.id),
            items=[
                RoomItemSnapshot(
                    classification="gun_tier_2_1",
                    display_name="Silent Pistol",
                    base_price=240,
                    image_path="/static/items/defaults/default_gun_tier_2.jpg",
                    is_active=True,
                ),
                RoomItemSnapshot(
                    classification="escape_from_jail",
                    display_name="Escape From Jail",
                    base_price=500,
                    image_path="/static/items/defaults/default_escape_from_jail.jpg",
                    is_active=True,
                ),
            ],
        )
        mock_get_container.return_value = _StubContainer(room)
        request = self.factory.post(f"/rooms/r-1/presets/{preset.id}/overwrite")
        request.user = self.user

        response = overwrite_preset(request, room_id="r-1", preset_id=preset.id)
        body = json.loads(response.content.decode("utf-8"))
        preset.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(len(preset.payload["rows"]), 2)
        self.assertEqual(preset.payload["counts"]["tier_2_gun_count"], 1)
        self.assertEqual(preset.payload["rows"][0]["display_name"], "Silent Pistol")

    @patch("project.mobboss_apps.rooms.views.get_container")
    def test_rename_preset_updates_name_for_moderator(self, mock_get_container) -> None:
        preset = RoomSupplyPreset.objects.create(
            user=self.user,
            name="Old Name",
            payload={"version": 1, "counts": {}, "rows": []},
        )
        room = _room_snapshot(moderator_user_id=str(self.user.id))
        mock_get_container.return_value = _StubContainer(room)
        request = self.factory.post(f"/rooms/r-1/presets/{preset.id}/rename", data={"preset_name": "New Name"})
        request.user = self.user

        response = rename_preset(request, room_id="r-1", preset_id=preset.id)
        body = json.loads(response.content.decode("utf-8"))
        preset.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(preset.name, "New Name")
