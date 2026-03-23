"""Outbound port for synchronizing room lifecycle from gameplay outcomes."""

from __future__ import annotations

from typing import Protocol


class GameplayRoomLifecycleOutboundPort(Protocol):
    def mark_room_ended_for_game(self, *, room_id: str, game_id: str) -> None:
        ...
