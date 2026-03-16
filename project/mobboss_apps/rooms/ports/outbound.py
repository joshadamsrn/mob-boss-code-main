"""Outbound ports: external resource contracts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from project.mobboss_apps.rooms.ports.internal import RoomDetailsSnapshot, RoomSnapshot


class RoomsOutboundPort(Protocol):
    def save_room(self, room: RoomDetailsSnapshot) -> None:
        ...

    def get_room(self, room_id: str) -> RoomDetailsSnapshot | None:
        ...

    def list_active_rooms(self) -> list[RoomSnapshot]:
        ...

    def reserve_game_id(self, room_id: str) -> str:
        ...

    def delete_room(self, room_id: str) -> None:
        ...


class RoomItemMediaOutboundPort(Protocol):
    def save_room_item_image(
        self,
        *,
        room_id: str,
        classification: str,
        original_filename: str,
        chunks: Iterable[bytes],
    ) -> str:
        ...

    def resolve_room_item_tile_image_url(self, image_url: str) -> str:
        ...

