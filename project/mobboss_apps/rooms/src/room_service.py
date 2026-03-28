"""Room use-case service backed by room ports."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import random
import time
from decimal import Decimal, ROUND_HALF_UP
from math import ceil, floor
from uuid import uuid4

from project.mobboss_apps.gameplay.ports.inbound import GameplayInboundPort
from project.mobboss_apps.gameplay.ports.internal import (
    StartSessionCatalogItemInput,
    StartSessionFromRoomCommand,
    StartSessionParticipantInput,
)
from project.mobboss_apps.mobboss.src.starting_money import getStartingMoney
from project.mobboss_apps.rooms.ports.inbound import RoomsInboundPort
from project.mobboss_apps.rooms.ports.internal import (
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
    SetMobSecretWordCommand,
    SetMemberBalanceCommand,
    SetRoomReadinessCommand,
    ShuffleRoomRolesCommand,
    UpsertRoomItemCommand,
    is_supported_item_classification,
)
from project.mobboss_apps.rooms.ports.outbound import RoomsOutboundPort

LOBBY_AUTO_CLOSE_SECONDS = 2 * 60 * 60
MIN_LAUNCH_PLAYERS = 7
MAX_ROOM_PLAYERS = 25
DEFAULT_ROOM_ITEM_BASE_PRICE = 100
TOTAL_MONEY_PER_PLAYER = 100
MAX_SECRET_MOB_WORD_LENGTH = 64
POLICE_ROLE_TITLES: tuple[str, ...] = (
    "Chief of Police",
    "Deputy",
    "Sheriff",
    "Captain",
    "Lieutenant",
    "Sergeant",
    "Detective",
    "Inspector",
    "Police Officer",
    "Cop",
)
MOB_ROLE_TITLES: tuple[str, ...] = (
    "Mob Boss",
    "Don",
    "Under Boss",
    "Kingpin",
    "Enforcer",
    "Made Man",
    "Gangster",
    "Street Thug",
    "Felon",
    "Knife Hobo",
)
MERCHANT_ROLE_TITLES: tuple[str, ...] = (
    "Arms Dealer",
    "Smuggler",
    "Merchant",
    "Gun Runner",
    "Supplier",
)


class RoomsService(RoomsInboundPort):
    def __init__(
        self,
        repository: RoomsOutboundPort,
        minimum_launch_players: int = MIN_LAUNCH_PLAYERS,
        gameplay_inbound_port: GameplayInboundPort | None = None,
    ) -> None:
        self._repository = repository
        self._minimum_launch_players = max(1, min(int(minimum_launch_players), MAX_ROOM_PLAYERS))
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
            secret_mob_word="",
        )
        room = self._assign_roles_for_joined_members(room, shuffle=False)
        self._repository.save_room(room)
        return self._to_summary(room)

    def list_active_rooms(self):
        return self._list_active_rooms(refresh_gameplay_lifecycle=True)

    def _list_active_rooms(self, *, refresh_gameplay_lifecycle: bool) -> list[RoomSnapshot]:
        summaries = self._repository.list_active_rooms()
        active: list[RoomSnapshot] = []
        lifecycle_refreshed = False
        for summary in summaries:
            room = self._repository.get_room(summary.room_id)
            if room is None:
                continue
            if (
                refresh_gameplay_lifecycle
                and
                room.status == "in_progress"
                and room.launched_game_id
                and self._gameplay_inbound_port is not None
            ):
                try:
                    game = self._gameplay_inbound_port.get_game_details(room.launched_game_id)
                except ValueError:
                    game = None
                if game is not None and game.status == "ended":
                    lifecycle_refreshed = True
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
        if lifecycle_refreshed and refresh_gameplay_lifecycle:
            return self._list_active_rooms(refresh_gameplay_lifecycle=False)
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
        rejoining_or_new_player = idx < 0 or members[idx].membership_status != "joined"
        if command.user_id != room.moderator_user_id and rejoining_or_new_player:
            joined_player_count = sum(
                1
                for member in members
                if member.membership_status == "joined" and member.user_id != room.moderator_user_id
            )
            if joined_player_count >= MAX_ROOM_PLAYERS:
                raise ValueError("Room is full.")
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
        conflicting_member = next(
            (
                member
                for member in members
                if member.user_id != command.target_user_id
                and member.membership_status == "joined"
                and member.assigned_role is not None
                and member.assigned_role.role_name == command.role_name
            ),
            None,
        )
        if conflicting_member is not None:
            raise ValueError(f"{command.role_name} is already assigned to {conflicting_member.username}.")
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
        if not is_supported_item_classification(command.classification):
            raise ValueError("Unsupported item classification.")
        price = _round_to_nearest_ten(command.base_price)
        if price < 0:
            raise ValueError("Item base price must be >= 0.")

        items = list(room.items)
        idx = self._find_item_index(items, command.classification)
        image_path = command.image_path or _default_image_path_for_classification(command.classification)
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

    def set_mob_secret_word(self, command: SetMobSecretWordCommand) -> RoomDetailsSnapshot:
        room = self._require_room(command.room_id)
        self._ensure_room_lobby(room)
        self._ensure_moderator(room, command.moderator_user_id)
        normalized = str(command.secret_mob_word).strip()
        if not normalized:
            raise ValueError("Secret mob word must be non-empty.")
        if len(normalized) > MAX_SECRET_MOB_WORD_LENGTH:
            raise ValueError(f"Secret mob word must be <= {MAX_SECRET_MOB_WORD_LENGTH} characters.")
        updated = replace(room, secret_mob_word=normalized)
        self._repository.save_room(updated)
        return updated

    def launch_game_from_room(self, command: LaunchGameFromRoomCommand) -> str:
        room = self._require_room(command.room_id)
        self._ensure_room_lobby(room)
        self._ensure_moderator(room, command.requested_by_user_id)
        room = self._ensure_required_catalog_items(room)
        if not str(room.secret_mob_word).strip():
            raise ValueError("Secret mob word must be set before launch.")
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
        if active_items <= 0:
            raise ValueError("At least one central supply item must be saved before launch.")
        if active_items < MIN_REQUIRED_ROOM_ITEMS:
            raise ValueError(f"At least {MIN_REQUIRED_ROOM_ITEMS} active catalog items are required to launch.")
        # Preserve the lobby role mapping at launch so moderator-selected
        # assignments remain stable for targeted role testing.
        room = _apply_launch_catalog_pricing(room, participant_count=participant_count)
        if self._gameplay_inbound_port is None:
            game_id = self._repository.reserve_game_id(room.room_id)
        else:
            start_command = _build_start_session_from_room_command(room)
            game_id = self._gameplay_inbound_port.start_session_from_room(start_command).game_id
        updated = replace(room, status="in_progress", launched_game_id=game_id)
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

        stable_seed = _stable_role_seed(room.room_id, [members[idx].user_id for idx in joined_indexes])
        slots = _build_role_slots(joined_count, rng=random.Random(stable_seed))
        if shuffle:
            random.Random(seed).shuffle(slots)

        balance_player_count = max(MIN_LAUNCH_PLAYERS, min(joined_count, MAX_ROOM_PLAYERS))
        for offset, member_index in enumerate(joined_indexes):
            assigned_role = slots[offset]
            members[member_index] = replace(
                members[member_index],
                assigned_role=assigned_role,
                starting_balance=_starting_balance_for_role(assigned_role, player_count=balance_player_count),
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


def _build_role_slots(player_count: int, *, rng: random.Random) -> list[RoomRoleAssignmentSnapshot]:
    merchants = _merchant_count_for_players(player_count)
    remaining = max(player_count - merchants, 0)
    police = ceil(remaining / 2)
    mob = floor(remaining / 2)

    if player_count >= 7 and merchants <= 0:
        merchants = 1
        remaining = max(player_count - merchants, 0)
        police = ceil(remaining / 2)
        mob = floor(remaining / 2)

    if player_count >= 7 and mob < 2 and police > 1:
        transfer = min(2 - mob, police - 1)
        police -= transfer
        mob += transfer

    slots: list[RoomRoleAssignmentSnapshot] = []

    police_title_rank = {title: idx + 1 for idx, title in enumerate(POLICE_ROLE_TITLES)}
    mob_title_rank = {title: idx + 1 for idx, title in enumerate(MOB_ROLE_TITLES)}

    police_titles: list[str] = []
    if police > 0:
        police_titles.append("Chief of Police")
    police_titles.extend(
        _sample_without_replacement(
            rng=rng,
            candidates=[title for title in POLICE_ROLE_TITLES if title != "Chief of Police"],
            count=max(police - 1, 0),
        )
    )
    for title in police_titles[:police]:
        slots.append(
            RoomRoleAssignmentSnapshot(
                faction="Police",
                role_name=title,
                rank=police_title_rank.get(title, 1),
            )
        )

    mob_titles: list[str] = []
    if mob > 0:
        mob_titles.append("Mob Boss")
    if mob > 1:
        mob_titles.append("Knife Hobo")
    mob_titles.extend(
        _sample_without_replacement(
            rng=rng,
            candidates=[title for title in MOB_ROLE_TITLES if title not in {"Mob Boss", "Knife Hobo"}],
            count=max(mob - len(mob_titles), 0),
        )
    )
    for title in mob_titles[:mob]:
        slots.append(
            RoomRoleAssignmentSnapshot(
                faction="Mob",
                role_name=title,
                rank=mob_title_rank.get(title, 1),
            )
        )

    merchant_titles: list[str] = []
    if merchants > 0:
        merchant_titles.append("Merchant")
    merchant_non_required = [title for title in MERCHANT_ROLE_TITLES if title != "Merchant"]
    merchant_titles.extend(
        _sample_without_replacement(
            rng=rng,
            candidates=merchant_non_required,
            count=max(min(merchants - len(merchant_titles), len(merchant_non_required)), 0),
        )
    )
    while len(merchant_titles) < merchants:
        if merchant_non_required:
            merchant_titles.append(rng.choice(merchant_non_required))
        else:
            merchant_titles.append("Merchant")
    for title in merchant_titles[:merchants]:
        # Merchants are solo operators; role titles are shown without rank.
        slots.append(RoomRoleAssignmentSnapshot(faction="Merchant", role_name=title, rank=1))

    while len(slots) < player_count:
        slots.append(RoomRoleAssignmentSnapshot(faction="Police", role_name="Detective", rank=7))

    return slots[:player_count]


def _sample_without_replacement(*, rng: random.Random, candidates: list[str], count: int) -> list[str]:
    if count <= 0 or not candidates:
        return []
    if count >= len(candidates):
        picked = list(candidates)
        rng.shuffle(picked)
        return picked
    return rng.sample(candidates, count)


def _stable_role_seed(room_id: str, joined_user_ids: list[str]) -> int:
    seed_text = f"{room_id}|{'|'.join(sorted(joined_user_ids))}"
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _starting_balance_for_role(role: RoomRoleAssignmentSnapshot, *, player_count: int) -> int:
    return getStartingMoney(player_count, role.role_name)


def minimum_launch_starting_balance(player_count: int = MIN_LAUNCH_PLAYERS) -> int:
    safe_player_count = max(MIN_LAUNCH_PLAYERS, min(int(player_count), 25))
    return sum(
        _starting_balance_for_role(role, player_count=safe_player_count)
        for role in _build_role_slots(safe_player_count, rng=random.Random(0))
    )


def _build_required_default_items() -> list[RoomItemSnapshot]:
    return [
        RoomItemSnapshot(
            classification=classification,
            display_name=ITEM_CLASSIFICATION_DISPLAY_NAMES.get(classification, classification),
            base_price=DEFAULT_ROOM_ITEM_BASE_PRICE,
            image_path=_default_image_path_for_classification(classification),
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


def _apply_launch_catalog_pricing(room: RoomDetailsSnapshot, *, participant_count: int) -> RoomDetailsSnapshot:
    if participant_count <= 0:
        return room

    total_money = participant_count * TOTAL_MONEY_PER_PLAYER
    target_price_by_bucket = {
        "gun_tier_1": _round_percentage_price_to_nearest_ten(total_money, "0.015"),
        "gun_tier_2": _round_percentage_price_to_nearest_ten(total_money, "0.035"),
        "gun_tier_3": _round_percentage_price_to_nearest_ten(total_money, "0.07"),
        "bulletproof_vest": _round_percentage_price_to_nearest_ten(total_money, "0.05"),
        "escape_from_jail": _round_percentage_price_to_nearest_ten(total_money, "0.05"),
        "knife": _round_percentage_price_to_nearest_ten(total_money, "0.12"),
    }

    priced_items: list[RoomItemSnapshot] = []
    for item in room.items:
        bucket = _classification_price_bucket(item.classification)
        target_price = target_price_by_bucket.get(bucket)
        if target_price is None:
            priced_items.append(item)
            continue
        if bucket == "knife":
            knife_number = _classification_ordinal(item.classification)
            if knife_number is not None and knife_number > 1:
                target_price = _round_percentage_price_to_nearest_ten(
                    total_money,
                    str(Decimal("0.12") * (Decimal("1.5") ** Decimal(knife_number - 1))),
                )
        if item.base_price != DEFAULT_ROOM_ITEM_BASE_PRICE:
            # Preserve explicit moderator price overrides.
            priced_items.append(item)
            continue
        priced_items.append(replace(item, base_price=target_price))

    return replace(room, items=priced_items)


def _round_percentage_price_to_nearest_ten(total_money: int, multiplier: str) -> int:
    raw_price = Decimal(str(total_money)) * Decimal(multiplier)
    rounded_tens = (raw_price / Decimal("10")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(rounded_tens * Decimal("10"))


def _default_image_path_for_classification(classification: str) -> str:
    bucket = _classification_price_bucket(classification)
    if bucket == "gun_tier_1":
        return "/static/items/defaults/default_gun_tier_1.jpg"
    if bucket == "gun_tier_2":
        return "/static/items/defaults/default_gun_tier_2.jpg"
    if bucket == "gun_tier_3":
        return "/static/items/defaults/default_gun_tier_3.jpg"
    if bucket == "knife":
        return "/static/items/defaults/default_knife.jpg"
    if bucket == "bulletproof_vest":
        return "/static/items/defaults/default_bulletproof_vest.png"
    if bucket == "escape_from_jail":
        return "/static/items/defaults/default_escape_from_jail.jpg"
    return f"/static/items/defaults/default_{classification}.svg"


def _classification_price_bucket(classification: str) -> str | None:
    if classification in {"gun_tier_1", "gun_tier_2", "gun_tier_3", "knife", "bulletproof_vest", "escape_from_jail"}:
        return classification
    if classification.startswith("gun_tier_1_"):
        return "gun_tier_1"
    if classification.startswith("gun_tier_2_"):
        return "gun_tier_2"
    if classification.startswith("gun_tier_3_"):
        return "gun_tier_3"
    if classification.startswith("knife_"):
        return "knife"
    return None


def _classification_ordinal(classification: str) -> int | None:
    if "_" not in classification:
        return None
    suffix = classification.rsplit("_", 1)[-1]
    if not suffix.isdigit():
        return None
    value = int(suffix)
    if value < 1:
        return None
    return value
