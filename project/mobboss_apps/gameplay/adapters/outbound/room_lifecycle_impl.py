"""Room lifecycle sync adapter used by gameplay service."""

from __future__ import annotations

from dataclasses import replace

from project.mobboss_apps.gameplay.ports.room_lifecycle_outbound import (
    GameplayRoomLifecycleOutboundPort,
)
from project.mobboss_apps.rooms.ports.outbound import RoomsOutboundPort


class RoomsLifecycleSyncOutboundPortImpl(GameplayRoomLifecycleOutboundPort):
    def __init__(self, rooms_repository: RoomsOutboundPort) -> None:
        self._rooms_repository = rooms_repository

    def mark_room_ended_for_game(self, *, room_id: str, game_id: str) -> None:
        room = self._rooms_repository.get_room(room_id)
        if room is None:
            return
        if room.launched_game_id != game_id:
            return

        ended_members = [
            replace(member, membership_status="left", is_ready=False, assigned_role=None)
            for member in room.members
        ]
        updated = replace(room, status="ended", launched_game_id=None, members=ended_members)
        self._rooms_repository.save_room(updated)
