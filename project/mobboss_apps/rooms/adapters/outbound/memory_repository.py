"""In-memory outbound adapter for room storage."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
from typing import Dict
from uuid import uuid4

from project.mobboss_apps.rooms.ports.internal import RoomDetailsSnapshot, RoomSnapshot
from project.mobboss_apps.rooms.ports.outbound import RoomsOutboundPort


class MemoryRoomsRepository(RoomsOutboundPort):
    def __init__(self, room_media_root: str | Path | None = None) -> None:
        self._rooms: Dict[str, RoomDetailsSnapshot] = {}
        self._game_sequence = 0
        self._room_media_root = Path(room_media_root) if room_media_root else None

    def save_room(self, room: RoomDetailsSnapshot) -> None:
        self._rooms[room.room_id] = room
        if room.status == "ended":
            self._cleanup_room_media(room.room_id)

    def get_room(self, room_id: str) -> RoomDetailsSnapshot | None:
        return self._rooms.get(room_id)

    def list_active_rooms(self) -> list[RoomSnapshot]:
        snapshots: list[RoomSnapshot] = []
        for room in self._rooms.values():
            if room.status == "ended":
                continue
            member_count = sum(
                1
                for m in room.members
                if m.membership_status == "joined" and m.user_id != room.moderator_user_id
            )
            snapshots.append(
                RoomSnapshot(
                    room_id=room.room_id,
                    name=room.name,
                    status=room.status,
                    moderator_user_id=room.moderator_user_id,
                    member_count=member_count,
                )
            )
        return snapshots

    def reserve_game_id(self, room_id: str) -> str:
        self._game_sequence += 1
        token = str(uuid4())[:8]
        return f"{room_id}-g{self._game_sequence}-{token}"

    def delete_room(self, room_id: str) -> None:
        self._cleanup_room_media(room_id)
        self._rooms.pop(room_id, None)

    def update_room_status(self, room_id: str, status: str) -> None:
        room = self._rooms[room_id]
        self._rooms[room_id] = replace(room, status=status)

    def _cleanup_room_media(self, room_id: str) -> None:
        if self._room_media_root is None:
            return
        room_dir = self._room_media_root / "rooms" / room_id
        shutil.rmtree(room_dir, ignore_errors=True)

