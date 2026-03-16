"""Inbound ports: system stimulation contracts."""

from __future__ import annotations

from typing import Protocol

from project.mobboss_apps.rooms.ports.internal import (
    AssignRoomRoleCommand,
    CreateRoomCommand,
    DeleteRoomCommand,
    DeactivateRoomItemCommand,
    JoinRoomCommand,
    LeaveRoomCommand,
    LaunchGameFromRoomCommand,
    RoomDetailsSnapshot,
    RoomSnapshot,
    SetMemberBalanceCommand,
    SetRoomReadinessCommand,
    ShuffleRoomRolesCommand,
    UpsertRoomItemCommand,
)


class RoomsInboundPort(Protocol):
    def create_room(self, command: CreateRoomCommand) -> RoomSnapshot:
        ...

    def list_active_rooms(self) -> list[RoomSnapshot]:
        ...

    def get_room_details(self, room_id: str) -> RoomDetailsSnapshot:
        ...

    def join_room(self, command: JoinRoomCommand) -> RoomDetailsSnapshot:
        ...

    def leave_room(self, command: LeaveRoomCommand) -> RoomDetailsSnapshot:
        ...

    def set_room_readiness(self, command: SetRoomReadinessCommand) -> RoomDetailsSnapshot:
        ...

    def assign_room_role(self, command: AssignRoomRoleCommand) -> RoomDetailsSnapshot:
        ...

    def set_member_balance(self, command: SetMemberBalanceCommand) -> RoomDetailsSnapshot:
        ...

    def upsert_room_item(self, command: UpsertRoomItemCommand) -> RoomDetailsSnapshot:
        ...

    def deactivate_room_item(self, command: DeactivateRoomItemCommand) -> RoomDetailsSnapshot:
        ...

    def launch_game_from_room(self, command: LaunchGameFromRoomCommand) -> str:
        """Return a newly created game_id."""
        ...

    def delete_room(self, command: DeleteRoomCommand) -> None:
        ...

    def shuffle_room_roles(self, command: ShuffleRoomRolesCommand) -> RoomDetailsSnapshot:
        ...

