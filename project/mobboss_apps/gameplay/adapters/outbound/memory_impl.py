"""In-memory gameplay repository adapter implementation."""

from __future__ import annotations

from typing import Dict
from uuid import uuid4

from project.mobboss_apps.gameplay.ports.internal import GameDetailsSnapshot
from project.mobboss_apps.gameplay.ports.outbound import GameplayOutboundPort


class MemoryGameplayOutboundPortImpl(GameplayOutboundPort):
    def __init__(self) -> None:
        self._sessions: Dict[str, GameDetailsSnapshot] = {}
        self._sequence = 0

    def reserve_game_id(self, room_id: str) -> str:
        self._sequence += 1
        return f"{room_id}-g{self._sequence}-{str(uuid4())[:8]}"

    def save_game_session(self, snapshot: GameDetailsSnapshot) -> None:
        self._sessions[snapshot.game_id] = snapshot

    def get_game_session(self, game_id: str) -> GameDetailsSnapshot | None:
        return self._sessions.get(game_id)

