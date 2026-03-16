"""SQLite outbound adapter for rooms."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

from project.mobboss_apps.rooms.adapters.outbound import sqlite_queries
from project.mobboss_apps.rooms.ports.internal import (
    RoomDetailsSnapshot,
    RoomItemSnapshot,
    RoomMemberSnapshot,
    RoomRoleAssignmentSnapshot,
    RoomSnapshot,
)
from project.mobboss_apps.rooms.ports.outbound import RoomsOutboundPort


class SqliteRoomsRepository(RoomsOutboundPort):
    def __init__(self, db_path: str, room_media_root: str | Path | None = None) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        sqlite_queries.ensure_schema(self._conn)
        self._room_media_root = Path(room_media_root) if room_media_root else None

    def save_room(self, room: RoomDetailsSnapshot) -> None:
        sqlite_queries.upsert_room(self._conn, _room_to_record(room))
        if room.status == "ended":
            self._cleanup_room_media(room.room_id)

    def get_room(self, room_id: str) -> RoomDetailsSnapshot | None:
        record = sqlite_queries.get_room(self._conn, room_id)
        if record is None:
            return None
        return _record_to_room(record)

    def list_active_rooms(self) -> list[RoomSnapshot]:
        rows = sqlite_queries.list_active_rooms(self._conn)
        return [
            RoomSnapshot(
                room_id=row["room_id"],
                name=row["name"],
                status=row["status"],
                moderator_user_id=row["moderator_user_id"],
                member_count=int(row["member_count"]),
            )
            for row in rows
        ]

    def reserve_game_id(self, room_id: str) -> str:
        seq = sqlite_queries.reserve_game_sequence(self._conn, room_id)
        token = str(uuid4())[:8]
        return f"{room_id}-g{seq}-{token}"

    def delete_room(self, room_id: str) -> None:
        sqlite_queries.delete_room(self._conn, room_id)
        self._cleanup_room_media(room_id)

    def close(self) -> None:
        self._conn.close()

    def _cleanup_room_media(self, room_id: str) -> None:
        if self._room_media_root is None:
            return
        room_dir = self._room_media_root / "rooms" / room_id
        shutil.rmtree(room_dir, ignore_errors=True)


def _room_to_record(room: RoomDetailsSnapshot) -> dict:
    return {
        "room_id": room.room_id,
        "name": room.name,
        "status": room.status,
        "moderator_user_id": room.moderator_user_id,
        "created_at": room.opened_at_epoch_seconds,
        "members": [
            {
                "user_id": member.user_id,
                "username": member.username,
                "membership_status": member.membership_status,
                "is_ready": 1 if member.is_ready else 0,
                "starting_balance": member.starting_balance,
                "assigned_faction": member.assigned_role.faction if member.assigned_role else None,
                "assigned_role_name": member.assigned_role.role_name if member.assigned_role else None,
                "assigned_rank": member.assigned_role.rank if member.assigned_role else None,
            }
            for member in room.members
        ],
        "items": [
            {
                "classification": item.classification,
                "display_name": item.display_name,
                "base_price": item.base_price,
                "image_path": item.image_path,
                "is_active": 1 if item.is_active else 0,
            }
            for item in room.items
        ],
    }


def _record_to_room(record: dict) -> RoomDetailsSnapshot:
    members: list[RoomMemberSnapshot] = []
    for member in record["members"]:
        role = None
        if member["assigned_faction"] and member["assigned_role_name"]:
            role = RoomRoleAssignmentSnapshot(
                faction=member["assigned_faction"],
                role_name=member["assigned_role_name"],
                rank=int(member["assigned_rank"]),
            )
        members.append(
            RoomMemberSnapshot(
                user_id=member["user_id"],
                username=member["username"],
                membership_status=member["membership_status"],
                is_ready=bool(member["is_ready"]),
                starting_balance=int(member["starting_balance"]),
                assigned_role=role,
            )
        )

    items = [
        RoomItemSnapshot(
            classification=item["classification"],
            display_name=item["display_name"],
            base_price=int(item["base_price"]),
            image_path=item["image_path"],
            is_active=bool(item["is_active"]),
        )
        for item in record["items"]
    ]

    return RoomDetailsSnapshot(
        room_id=record["room_id"],
        name=record["name"],
        status=record["status"],
        moderator_user_id=record["moderator_user_id"],
        opened_at_epoch_seconds=_parse_created_at_epoch(record.get("created_at")),
        members=members,
        items=items,
    )


def _parse_created_at_epoch(value: str | int | None) -> int:
    if value is None:
        return int(datetime.now(timezone.utc).timestamp())

    text = str(value).strip()
    if not text:
        return int(datetime.now(timezone.utc).timestamp())
    if text.isdigit():
        return int(text)

    try:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except ValueError:
        return int(datetime.now(timezone.utc).timestamp())

