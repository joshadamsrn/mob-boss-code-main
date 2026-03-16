"""Room use-case service backed by room ports."""

from __future__ import annotations

from dataclasses import replace
import random
import time
from math import ceil, floor
from uuid import uuid4

from project.mobboss_apps.gameplay.ports.inbound import GameplayInboundPort
from project.mobboss_apps.gameplay.ports.internal import (
    StartSessionCatalogItemInput,
    StartSessionFromRoomCommand,
    StartSessionParticipantInput,
)
from project.mobboss_apps.rooms.ports.inbound import RoomsInboundPort
from project.mobboss_apps.rooms.ports.internal import (
    APPROVED_ITEM_CLASSIFICATIONS,
    AssignRoomRoleCommand,
    CreateRoomCommand,
    DeleteRoomCommand,
    DeactivateRoomItemCommand,
    ITEM_CLASSIFICATION_DISPLAY_NAMES,
    JoinRoomCommand,
    LeaveRoomCommand,
    LaunchGameFromRoomCommand,
    MIN_REQUIRED_ROOM_ITEMS,
    REQUIRED_ROOM_ITEM_CLASSIFICATIONS,
    RoomDetailsSnapshot,
    RoomItemSnapshot,
    RoomMemberSnapshot,
    RoomRoleAssignmentSnapshot,
    RoomSnapshot,
    SetMemberBalanceCommand,
    SetRoomReadinessCommand,
    ShuffleRoomRolesCommand,
    UpsertRoomItemCommand,
)
from project.mobboss_apps.rooms.ports.outbound import RoomsOutboundPort

LOBBY_AUTO_CLOSE_SECONDS = 2 * 60 * 60
MIN_LAUNCH_PLAYERS = 7
ROLE_STARTING_BALANCE_BY_NAME: dict[str, int] = {
    "Police Chief": 300,
    "Police Deputy": 250,
    "Police Detective": 220,
    "Mob Boss": 300,
    "Mob Member": 250,
    "Knife Hobo": 180,
    "Merchant": 400,
}


class RoomsService(RoomsInboundPort):
    def __init__(
        self,
        repository: RoomsOutboundPort,
        minimum_launch_players: int = MIN_LAUNCH_PLAYERS,
        gameplay_inbound_port: GameplayInboundPort | None = None,
    ) -> None:
        self._repository = repository
        self._minimum_launch_players = max(1, min(int(minimum_launch_players), 25))
        self._gameplay_inbound_port = gameplay_inbound_port

    def create_room(self, command: CreateRoomCommand):
        room_id = str(uuid4())
        creator_name = command.creator_username or command.creator_user_id
        room = RoomDetailsSnapshot(
            room_id=room_id,
            name=command.name,
            status="lobby",
            moderator_user_id=command.creator_user_id,
            opened_at_epoch_seconds=self._now_epoch_seconds(),
            members=[
                RoomMemberSnapshot(
                    user_id=command.creator_user_id,
                    username=creator_name,
                    membership_status="joined",
                    is_ready=True,
                    starting_balance=0,
                    assigned_role=None,
                )
            ],
            items=_build_required_default_items(),
        )
        room = self._assign_roles_for_joined_members(room, shuffle=False)
        self._repository.save_room(room)
        return self._to_summary(room)

    def list_active_rooms(self):
        summaries = self._repository.list_active_rooms()
        active: list[RoomSnapshot] = []
        for summary in summaries:
            room = self._repository.get_room(summary.room_id)
            if room is None:
                continue
            if self._is_lobby_room_expired(room):
                closed = self._close_room_and_evict(room)
                self._repository.save_room(closed)
                continue
            if not self._moderator_is_joined(room):
                closed = self._close_room_and_evict(room)
                self._repository.save_room(closed)
                continue
            active.append(self._to_summary(room))
        return active

    def get_room_details(self, room_id: str) -> RoomDetailsSnapshot:
        room = self._require_room(room_id)
        return room

    def join_room(self, command: JoinRoomCommand) -> RoomDetailsSnapshot:
        room = self._require_room(command.room_id)
        self._ensure_room_lobby(room)

        username = command.username or command.user_id
        members = list(room.members)
        idx = self._find_member_index(members, command.user_id)
        if idx >= 0:
            members[idx] = replace(members[idx], membership_status="joined", username=username)
        else:
            members.append(
                RoomMemberSnapshot(
                    user_id=command.user_id,
                    username=username,
                    membership_status="joined",
                    is_ready=False,
                    starting_balance=0,
                    assigned_role=None,
                )
            )
        updated = replace(room, members=members)
        updated = self._assign_roles_for_joined_members(updated, shuffle=False)
        self._repository.save_room(updated)
        return updated

    def leave_room(self, command: LeaveRoomCommand) -> RoomDetailsSnapshot:
        room = self._require_room(command.room_id)
        if command.user_id == room.moderator_user_id:
            closed = self._close_room_and_evict(room)
            self._repository.save_room(closed)
            return closed

        self._ensure_room_lobby(room)
        members = list(room.members)
        idx = self._find_member_index(members, command.user_id)
        if idx < 0:
            raise ValueError("User is not a room member.")
        members[idx] = replace(members[idx], membership_status="left", is_ready=False, assigned_role=None)
        updated = replace(room, members=members)
        updated = self._assign_roles_for_joined_members(updated, shuffle=False)
        self._repository.save_room(updated)
        return updated

    def set_room_readiness(self, command: SetRoomReadinessCommand) -> RoomDetailsSnapshot:
        room = self._require_room(command.room_id)
        self._ensure_room_lobby(room)
        if command.user_id == room.moderator_user_id:
            raise ValueError("Moderator readiness is implicit and cannot be changed.")
        if command.requested_by_user_id != command.user_id and command.requested_by_user_id != room.moderator_user_id:
            raise PermissionError("Participants can only set their own readiness.")
        members = list(room.members)
        idx = self._find_member_index(members, command.user_id)
        if idx < 0 or members[idx].membership_status != "joined":
            raise ValueError("Only joined members can set readiness.")
        members[idx] = replace(members[idx], is_ready=command.is_ready)
        updated = replace(room, members=members)
        self._repository.save_room(updated)
        return updated

    def assign_room_role(self, command: AssignRoomRoleCommand) -> RoomDetailsSnapshot:
        room = self._require_room(command.room_id)
        self._ensure_room_lobby(room)
        self._ensure_moderator(room, command.moderator_user_id)
        if command.target_user_id == room.moderator_user_id:
            raise ValueError("Moderator cannot be assigned a player role.")
        if command.rank < 1:
            raise ValueError("Rank must be >= 1.")
        members = list(room.members)
        idx = self._find_member_index(members, command.target_user_id)
        if idx < 0 or members[idx].membership_status != "joined":
            raise ValueError("Target must be a joined room member.")
        members[idx] = replace(
            members[idx],
            assigned_role=RoomRoleAssignmentSnapshot(
                faction=command.faction,
                role_name=command.role_name,
                rank=command.rank,
            ),
        )
        updated = replace(room, members=members)
        self._repository.save_room(updated)
        return updated

    def set_member_balance(self, command: SetMemberBalanceCommand) -> RoomDetailsSnapshot:
        room = self._require_room(command.room_id)
        self._ensure_room_lobby(room)
        self._ensure_moderator(room, command.moderator_user_id)
        if command.target_user_id == room.moderator_user_id:
            raise ValueError("Moderator does not have a player balance.")
        rounded = _round_to_nearest_ten(command.starting_balance)
        if rounded < 0:
            raise ValueError("Starting balance must be >= 0.")
        members = list(room.members)
        idx = self._find_member_index(members, command.target_user_id)
        if idx < 0 or members[idx].membership_status != "joined":
            raise ValueError("Target must be a joined room member.")
        members[idx] = replace(members[idx], starting_balance=rounded)
        updated = replace(room, members=members)
        self._repository.save_room(updated)
        return updated

    def upsert_room_item(self, command: UpsertRoomItemCommand) -> RoomDetailsSnapshot:
        room = self._require_room(command.room_id)
        self._ensure_room_lobby(room)
        self._ensure_moderator(room, command.moderator_user_id)
        if command.classification not in APPROVED_ITEM_CLASSIFICATIONS:
            raise ValueError("Unsupported item classification.")
        price = _round_to_nearest_ten(command.base_price)
        if price < 0:
            raise ValueError("Item base price must be >= 0.")

        items = list(room.items)
        idx = self._find_item_index(items, command.classification)
        image_path = command.image_path or f"/static/items/defaults/default_{command.classification}.svg"
        item = RoomItemSnapshot(
            classification=command.classification,
            display_name=command.display_name,
            base_price=price,
            image_path=image_path,
            is_active=True,
        )
        if idx >= 0:
            items[idx] = item
        else:
            items.append(item)
        updated = replace(room, items=items)
        self._repository.save_room(updated)
        return updated

    def deactivate_room_item(self, command: DeactivateRoomItemCommand) -> RoomDetailsSnapshot:
        room = self._require_room(command.room_id)
        self._ensure_room_lobby(room)
        self._ensure_moderator(room, command.moderator_user_id)
        if command.classification in REQUIRED_ROOM_ITEM_CLASSIFICATIONS:
            raise ValueError("Required catalog items cannot be deactivated.")
        items = list(room.items)
        idx = self._find_item_index(items, command.classification)
        if idx < 0:
            raise ValueError("Unknown item classification in room catalog.")
        items[idx] = replace(items[idx], is_active=False)
        updated = replace(room, items=items)
        self._repository.save_room(updated)
        return updated

    def launch_game_from_room(self, command: LaunchGameFromRoomCommand) -> str:
        room = self._require_room(command.room_id)
        self._ensure_room_lobby(room)
        self._ensure_moderator(room, command.requested_by_user_id)
        room = self._ensure_required_catalog_items(room)
        participant_count = sum(
            1
            for member in room.members
            if member.membership_status == "joined" and member.user_id != room.moderator_user_id
        )
        if participant_count < self._minimum_launch_players:
            raise ValueError(
                f"At least {self._minimum_launch_players} joined players are required to launch (excluding moderator)."
            )
        active_items = sum(1 for item in room.items if item.is_active)
        if active_items < MIN_REQUIRED_ROOM_ITEMS:
            raise ValueError(f"At least {MIN_REQUIRED_ROOM_ITEMS} active catalog items are required to launch.")
        if self._gameplay_inbound_port is None:
            game_id = self._repository.reserve_game_id(room.room_id)
        else:
            start_command = _build_start_session_from_room_command(room)
            game_id = self._gameplay_inbound_port.start_session_from_room(start_command).game_id
        updated = replace(room, status="in_progress")
        self._repository.save_room(updated)
        return game_id

    def delete_room(self, command: DeleteRoomCommand) -> None:
        room = self._require_room(command.room_id)
        self._ensure_moderator(room, command.requested_by_user_id)
        self._repository.delete_room(command.room_id)

    def shuffle_room_roles(self, command: ShuffleRoomRolesCommand) -> RoomDetailsSnapshot:
        room = self._require_room(command.room_id)
        self._ensure_room_lobby(room)
        self._ensure_moderator(room, command.moderator_user_id)
        updated = self._assign_roles_for_joined_members(room, shuffle=True, seed=command.seed)
        self._repository.save_room(updated)
        return updated

    def _require_room(self, room_id: str) -> RoomDetailsSnapshot:
        room = self._repository.get_room(room_id)
        if room is None:
            raise ValueError("Room not found.")
        if self._is_lobby_room_expired(room):
            closed = self._close_room_and_evict(room)
            self._repository.save_room(closed)
            return closed
        room = self._ensure_required_catalog_items(room)
        return room

    @staticmethod
    def _find_member_index(members: list[RoomMemberSnapshot], user_id: str) -> int:
        for idx, member in enumerate(members):
            if member.user_id == user_id:
                return idx
        return -1

    @staticmethod
    def _find_item_index(items: list[RoomItemSnapshot], classification: str) -> int:
        for idx, item in enumerate(items):
            if item.classification == classification:
                return idx
        return -1

    @staticmethod
    def _ensure_moderator(room: RoomDetailsSnapshot, user_id: str) -> None:
        if user_id != room.moderator_user_id:
            raise PermissionError("Only moderator can perform this action.")

    @staticmethod
    def _ensure_room_lobby(room: RoomDetailsSnapshot) -> None:
        if room.status != "lobby":
            raise ValueError("Room is not editable outside lobby state.")

    @staticmethod
    def _moderator_is_joined(room: RoomDetailsSnapshot) -> bool:
        return any(
            member.user_id == room.moderator_user_id and member.membership_status == "joined"
            for member in room.members
        )

    @staticmethod
    def _close_room_and_evict(room: RoomDetailsSnapshot) -> RoomDetailsSnapshot:
        members = [
            replace(member, membership_status="left", is_ready=False, assigned_role=None)
            for member in room.members
        ]
        return replace(room, status="ended", members=members)

    @classmethod
    def _is_lobby_room_expired(cls, room: RoomDetailsSnapshot) -> bool:
        if room.status != "lobby":
            return False
        age_seconds = cls._now_epoch_seconds() - room.opened_at_epoch_seconds
        return age_seconds >= LOBBY_AUTO_CLOSE_SECONDS

    @staticmethod
    def _now_epoch_seconds() -> int:
        return int(time.time())

    def _ensure_required_catalog_items(self, room: RoomDetailsSnapshot) -> RoomDetailsSnapshot:
        items = list(room.items)
        changed = False
        for required in _build_required_default_items():
            idx = self._find_item_index(items, required.classification)
            if idx < 0:
                items.append(required)
                changed = True
                continue

            existing = items[idx]
            if not existing.is_active:
                items[idx] = replace(existing, is_active=True)
                changed = True

        if not changed:
            return room

        updated = replace(room, items=items)
        self._repository.save_room(updated)
        return updated

    @staticmethod
    def _to_summary(room: RoomDetailsSnapshot) -> RoomSnapshot:
        member_count = sum(
            1
            for member in room.members
            if member.membership_status == "joined" and member.user_id != room.moderator_user_id
        )

        return RoomSnapshot(
            room_id=room.room_id,
            name=room.name,
            status=room.status,
            moderator_user_id=room.moderator_user_id,
            member_count=member_count,
        )

    @staticmethod
    def _assign_roles_for_joined_members(
        room: RoomDetailsSnapshot, *, shuffle: bool, seed: int | None = None
    ) -> RoomDetailsSnapshot:
        joined_indexes = [
            idx
            for idx, member in enumerate(room.members)
            if member.membership_status == "joined" and member.user_id != room.moderator_user_id
        ]
        joined_count = len(joined_indexes)

        members = list(room.members)
        for idx, member in enumerate(members):
            if member.user_id == room.moderator_user_id and member.assigned_role is not None:
                members[idx] = replace(member, assigned_role=None, starting_balance=0)

        if joined_count == 0:
            return replace(room, members=members)

        slots = _build_role_slots(joined_count)
        if shuffle:
            rng = random.Random(seed)
            rng.shuffle(slots)

        for offset, member_index in enumerate(joined_indexes):
            assigned_role = slots[offset]
            members[member_index] = replace(
                members[member_index],
                assigned_role=assigned_role,
                starting_balance=_starting_balance_for_role(assigned_role),
            )

        return replace(room, members=members)


def _round_to_nearest_ten(value: int) -> int:
    remainder = value % 10
    if remainder >= 5:
        return value + (10 - remainder)
    return value - remainder


def _merchant_count_for_players(player_count: int) -> int:
    if 7 <= player_count <= 9:
        return 1
    if 10 <= player_count <= 13:
        return 2
    if 14 <= player_count <= 17:
        return 3
    if 18 <= player_count <= 21:
        return 4
    if 22 <= player_count <= 25:
        return 5
    return 0


def _build_role_slots(player_count: int) -> list[RoomRoleAssignmentSnapshot]:
    merchants = _merchant_count_for_players(player_count)
    remaining = max(player_count - merchants, 0)
    police = ceil(remaining / 2)
    mob = floor(remaining / 2)

    slots: list[RoomRoleAssignmentSnapshot] = []

    if police > 0:
        slots.append(RoomRoleAssignmentSnapshot(faction="Police", role_name="Police Chief", rank=1))
    if police > 1:
        slots.append(RoomRoleAssignmentSnapshot(faction="Police", role_name="Police Deputy", rank=2))
    for idx in range(3, police + 1):
        slots.append(RoomRoleAssignmentSnapshot(faction="Police", role_name="Police Detective", rank=idx))

    if mob > 0:
        slots.append(RoomRoleAssignmentSnapshot(faction="Mob", role_name="Mob Boss", rank=1))
    if mob > 1:
        for idx in range(2, mob):
            slots.append(RoomRoleAssignmentSnapshot(faction="Mob", role_name="Mob Member", rank=idx))
        slots.append(RoomRoleAssignmentSnapshot(faction="Mob", role_name="Knife Hobo", rank=mob))

    for idx in range(1, merchants + 1):
        slots.append(RoomRoleAssignmentSnapshot(faction="Merchant", role_name="Merchant", rank=idx))

    while len(slots) < player_count:
        slots.append(RoomRoleAssignmentSnapshot(faction="Police", role_name="Police Detective", rank=police + 1))

    return slots[:player_count]


def _starting_balance_for_role(role: RoomRoleAssignmentSnapshot) -> int:
    return ROLE_STARTING_BALANCE_BY_NAME.get(role.role_name, 200)


def minimum_launch_starting_balance(player_count: int = MIN_LAUNCH_PLAYERS) -> int:
    safe_player_count = max(1, int(player_count))
    return sum(_starting_balance_for_role(role) for role in _build_role_slots(safe_player_count))


def _build_required_default_items() -> list[RoomItemSnapshot]:
    return [
        RoomItemSnapshot(
            classification=classification,
            display_name=ITEM_CLASSIFICATION_DISPLAY_NAMES.get(classification, classification),
            base_price=100,
            image_path=f"/static/items/defaults/default_{classification}.svg",
            is_active=True,
        )
        for classification in REQUIRED_ROOM_ITEM_CLASSIFICATIONS
    ]


def _build_start_session_from_room_command(room: RoomDetailsSnapshot) -> StartSessionFromRoomCommand:
    participants: list[StartSessionParticipantInput] = []
    for member in room.members:
        if member.membership_status != "joined":
            continue
        if member.user_id == room.moderator_user_id:
            continue
        if member.assigned_role is None:
            raise ValueError(f"Cannot launch game: member '{member.user_id}' has no assigned role.")

        participants.append(
            StartSessionParticipantInput(
                user_id=member.user_id,
                username=member.username,
                faction=member.assigned_role.faction,
                role_name=member.assigned_role.role_name,
                rank=member.assigned_role.rank,
                starting_balance=member.starting_balance,
            )
        )

    catalog = [
        StartSessionCatalogItemInput(
            classification=item.classification,
            display_name=item.display_name,
            base_price=item.base_price,
            image_path=item.image_path,
            is_active=item.is_active,
        )
        for item in room.items
    ]
    return StartSessionFromRoomCommand(
        room_id=room.room_id,
        moderator_user_id=room.moderator_user_id,
        launched_at_epoch_seconds=RoomsService._now_epoch_seconds(),
        participants=participants,
        catalog=catalog,
    )

