"""Outbound ports: gameplay persistence contracts."""

from __future__ import annotations

from typing import Protocol

from .internal import GameDetailsSnapshot


class GameplayOutboundPort(Protocol):
    def reserve_game_id(self, room_id: str) -> str:
        ...

    def save_game_session(self, snapshot: GameDetailsSnapshot) -> None:
        ...

    def get_game_session(self, game_id: str) -> GameDetailsSnapshot | None:
        ...
