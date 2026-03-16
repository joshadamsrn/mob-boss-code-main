"""Inbound ports: gameplay use-case contracts."""

from __future__ import annotations

from typing import Protocol

from .internal import (
    AdvanceAccusedSelectionTimeoutCommand,
    GameDetailsSnapshot,
    ReportDeathCommand,
    StartSessionFromRoomCommand,
)


class GameplayInboundPort(Protocol):
    def start_session_from_room(self, command: StartSessionFromRoomCommand) -> GameDetailsSnapshot:
        ...

    def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
        ...

    def report_death(self, command: ReportDeathCommand) -> GameDetailsSnapshot:
        ...

    def advance_accused_selection_timeout(self, command: AdvanceAccusedSelectionTimeoutCommand) -> GameDetailsSnapshot:
        ...
