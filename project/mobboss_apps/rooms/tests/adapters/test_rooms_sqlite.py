import sys
import unittest
from dataclasses import replace
import shutil
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
TMP_ROOT = Path(__file__).resolve().parents[1] / "_tmp"

from project.mobboss_apps.rooms.adapters.outbound.sqlite_repository import (  # noqa: E402
    SqliteRoomsRepository,
)
from project.mobboss_apps.rooms.ports.internal import (  # noqa: E402
    CreateRoomCommand,
    DeleteRoomCommand,
    JoinRoomCommand,
    LeaveRoomCommand,
    MIN_REQUIRED_ROOM_ITEMS,
    REQUIRED_ROOM_ITEM_CLASSIFICATIONS,
)
from project.mobboss_apps.rooms.src.room_service import RoomsService  # noqa: E402


class RoomSqliteServiceTests(unittest.TestCase):
    def test_create_room_preloads_required_catalog_items(self) -> None:
        tmp_dir = TMP_ROOT
        tmp_dir.mkdir(parents=True, exist_ok=True)
        db_path = tmp_dir / "rooms_required_items_test.sqlite3"
        if db_path.exists():
            db_path.unlink()

        repo = SqliteRoomsRepository(db_path=str(db_path))
        service = RoomsService(repo)
        room_summary = service.create_room(
            CreateRoomCommand(name="SQLite Room", creator_user_id="u_mod", creator_username="mod")
        )
        details = service.get_room_details(room_summary.room_id)

        self.assertGreaterEqual(len(details.items), MIN_REQUIRED_ROOM_ITEMS)
        required = {item.classification for item in details.items if item.classification in REQUIRED_ROOM_ITEM_CLASSIFICATIONS}
        self.assertEqual(required, set(REQUIRED_ROOM_ITEM_CLASSIFICATIONS))

        repo.close()
        if db_path.exists():
            db_path.unlink()

    def test_room_persists_and_can_be_deleted(self) -> None:
        tmp_dir = TMP_ROOT
        tmp_dir.mkdir(parents=True, exist_ok=True)
        db_path = tmp_dir / "rooms_test.sqlite3"
        if db_path.exists():
            db_path.unlink()

        repo_1 = SqliteRoomsRepository(db_path=str(db_path))
        service_1 = RoomsService(repo_1)
        room_summary = service_1.create_room(
            CreateRoomCommand(name="SQLite Room", creator_user_id="u_mod", creator_username="mod")
        )

        repo_2 = SqliteRoomsRepository(db_path=str(db_path))
        service_2 = RoomsService(repo_2)
        listed = service_2.list_active_rooms()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].room_id, room_summary.room_id)

        service_2.delete_room(DeleteRoomCommand(room_id=room_summary.room_id, requested_by_user_id="u_mod"))
        self.assertEqual(service_2.list_active_rooms(), [])

        repo_1.close()
        repo_2.close()
        if db_path.exists():
            db_path.unlink()

    def test_list_active_rooms_prunes_orphan_room_when_moderator_not_joined(self) -> None:
        tmp_dir = TMP_ROOT
        tmp_dir.mkdir(parents=True, exist_ok=True)
        db_path = tmp_dir / "rooms_orphan_test.sqlite3"
        if db_path.exists():
            db_path.unlink()

        repo_1 = SqliteRoomsRepository(db_path=str(db_path))
        service_1 = RoomsService(repo_1)
        room_summary = service_1.create_room(
            CreateRoomCommand(name="SQLite Room", creator_user_id="u_mod", creator_username="mod")
        )
        service_1.join_room(JoinRoomCommand(room_id=room_summary.room_id, user_id="u_1", username="p1"))

        details = service_1.get_room_details(room_summary.room_id)
        corrupted_members = [
            replace(member, membership_status="left", is_ready=False, assigned_role=None)
            if member.user_id == "u_mod"
            else member
            for member in details.members
        ]
        repo_1.save_room(replace(details, members=corrupted_members))

        repo_2 = SqliteRoomsRepository(db_path=str(db_path))
        service_2 = RoomsService(repo_2)

        self.assertEqual(service_2.list_active_rooms(), [])
        closed = service_2.get_room_details(room_summary.room_id)
        self.assertEqual(closed.status, "ended")
        self.assertTrue(all(member.membership_status == "left" for member in closed.members))

        repo_1.close()
        repo_2.close()
        if db_path.exists():
            db_path.unlink()

    def test_list_active_rooms_auto_closes_lobby_rooms_older_than_two_hours(self) -> None:
        tmp_dir = TMP_ROOT
        tmp_dir.mkdir(parents=True, exist_ok=True)
        db_path = tmp_dir / "rooms_expiry_test.sqlite3"
        if db_path.exists():
            db_path.unlink()

        repo_1 = SqliteRoomsRepository(db_path=str(db_path))
        service_1 = RoomsService(repo_1)
        room_summary = service_1.create_room(
            CreateRoomCommand(name="SQLite Room", creator_user_id="u_mod", creator_username="mod")
        )
        details = service_1.get_room_details(room_summary.room_id)
        repo_1.save_room(replace(details, opened_at_epoch_seconds=int(time.time()) - (2 * 60 * 60 + 1)))

        repo_2 = SqliteRoomsRepository(db_path=str(db_path))
        service_2 = RoomsService(repo_2)
        self.assertEqual(service_2.list_active_rooms(), [])

        closed = service_2.get_room_details(room_summary.room_id)
        self.assertEqual(closed.status, "ended")

        repo_1.close()
        repo_2.close()
        if db_path.exists():
            db_path.unlink()

    def test_moderator_close_auto_cleans_room_media_directory(self) -> None:
        tmp_dir = TMP_ROOT
        tmp_dir.mkdir(parents=True, exist_ok=True)
        db_path = tmp_dir / "rooms_media_cleanup_test.sqlite3"
        media_root = tmp_dir / "media_sqlite_cleanup"
        if db_path.exists():
            db_path.unlink()
        if media_root.exists():
            shutil.rmtree(media_root, ignore_errors=True)

        repo = SqliteRoomsRepository(db_path=str(db_path), room_media_root=media_root)
        service = RoomsService(repo)
        room_summary = service.create_room(
            CreateRoomCommand(name="SQLite Media Room", creator_user_id="u_mod", creator_username="mod")
        )
        room_media_dir = media_root / "rooms" / room_summary.room_id / "items"
        room_media_dir.mkdir(parents=True, exist_ok=True)
        (room_media_dir / "test.txt").write_text("x", encoding="utf-8")

        service.leave_room(LeaveRoomCommand(room_id=room_summary.room_id, user_id="u_mod"))
        self.assertFalse((media_root / "rooms" / room_summary.room_id).exists())

        repo.close()
        if db_path.exists():
            db_path.unlink()
        if media_root.exists():
            shutil.rmtree(media_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
