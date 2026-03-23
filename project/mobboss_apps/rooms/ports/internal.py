"""Internal ports: DTOs and data contracts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

RoomStatus = Literal["lobby", "in_progress", "ended"]
MembershipStatus = Literal["joined", "left", "kicked"]
FactionName = Literal["Police", "Mob", "Merchant"]
ApprovedItemClassification = str
ITEM_CLASSIFICATIONS: tuple[dict[str, str], ...] = (
    {"code": "knife", "display_name": "Knife"},
    {"code": "gun_tier_1", "display_name": "Handgun (Tier 1)"},
    {"code": "gun_tier_2", "display_name": "Pistol (Tier 2)"},
    {"code": "gun_tier_3", "display_name": "Revolver (Tier 3)"},
    {"code": "bulletproof_vest", "display_name": "Bulletproof Vest"},
    {"code": "escape_from_jail", "display_name": "Escape From Jail"},
)
APPROVED_ITEM_CLASSIFICATIONS: set[str] = {item["code"] for item in ITEM_CLASSIFICATIONS}
ITEM_CLASSIFICATION_DISPLAY_NAMES: dict[str, str] = {
    item["code"]: item["display_name"] for item in ITEM_CLASSIFICATIONS
}
MIN_REQUIRED_ROOM_ITEMS = 0
REQUIRED_ROOM_ITEM_CLASSIFICATIONS: tuple[str, ...] = ()
FACTION_NAMES: set[str] = {"Police", "Mob", "Merchant"}
_DYNAMIC_GUN_CLASSIFICATION_PATTERN = re.compile(r"^gun_tier_[123]_[1-9]\d*$")
_DYNAMIC_KNIFE_CLASSIFICATION_PATTERN = re.compile(r"^knife_[1-9]\d*$")


def is_supported_item_classification(value: str) -> bool:
    normalized = str(value).strip()
    if normalized in APPROVED_ITEM_CLASSIFICATIONS:
        return True
    if _DYNAMIC_GUN_CLASSIFICATION_PATTERN.match(normalized):
        return True
    if _DYNAMIC_KNIFE_CLASSIFICATION_PATTERN.match(normalized):
        return True
    return False


@dataclass(frozen=True)
class CreateRoomCommand:
    name: str
    creator_user_id: str
    creator_username: str = ""

    @classmethod
    def from_json(cls, payload: dict) -> "CreateRoomCommand":
        return cls(
            name=_require_non_empty(payload, "name"),
            creator_user_id=_require_non_empty(payload, "creator_user_id"),
            creator_username=str(payload.get("creator_username", "")).strip(),
        )


@dataclass(frozen=True)
class JoinRoomCommand:
    room_id: str
    user_id: str
    username: str = ""

    @classmethod
    def from_json(cls, payload: dict) -> "JoinRoomCommand":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            user_id=_require_non_empty(payload, "user_id"),
            username=str(payload.get("username", "")).strip(),
        )


@dataclass(frozen=True)
class LeaveRoomCommand:
    room_id: str
    user_id: str

    @classmethod
    def from_json(cls, payload: dict) -> "LeaveRoomCommand":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            user_id=_require_non_empty(payload, "user_id"),
        )


@dataclass(frozen=True)
class SetRoomReadinessCommand:
    room_id: str
    requested_by_user_id: str
    user_id: str
    is_ready: bool

    @classmethod
    def from_json(cls, payload: dict) -> "SetRoomReadinessCommand":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            requested_by_user_id=_require_non_empty(payload, "requested_by_user_id"),
            user_id=_require_non_empty(payload, "user_id"),
            is_ready=bool(payload["is_ready"]),
        )


@dataclass(frozen=True)
class AssignRoomRoleCommand:
    room_id: str
    moderator_user_id: str
    target_user_id: str
    faction: FactionName
    role_name: str
    rank: int

    @classmethod
    def from_json(cls, payload: dict) -> "AssignRoomRoleCommand":
        faction = payload["faction"]
        if faction not in FACTION_NAMES:
            raise ValueError(f"Unsupported faction: {faction!r}")
        rank = int(payload["rank"])
        if rank < 1:
            raise ValueError("Rank must be >= 1.")
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            faction=faction,
            role_name=_require_non_empty(payload, "role_name"),
            rank=rank,
        )


@dataclass(frozen=True)
class SetMemberBalanceCommand:
    room_id: str
    moderator_user_id: str
    target_user_id: str
    starting_balance: int

    @classmethod
    def from_json(cls, payload: dict) -> "SetMemberBalanceCommand":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            starting_balance=int(payload["starting_balance"]),
        )


@dataclass(frozen=True)
class UpsertRoomItemCommand:
    room_id: str
    moderator_user_id: str
    classification: ApprovedItemClassification
    display_name: str
    base_price: int
    image_path: str = ""

    @classmethod
    def from_json(cls, payload: dict) -> "UpsertRoomItemCommand":
        classification = payload["classification"]
        if not is_supported_item_classification(classification):
            raise ValueError(f"Unsupported item classification: {classification!r}")
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            classification=classification,
            display_name=_require_non_empty(payload, "display_name"),
            base_price=int(payload["base_price"]),
            image_path=str(payload.get("image_path", "")).strip(),
        )


@dataclass(frozen=True)
class DeactivateRoomItemCommand:
    room_id: str
    moderator_user_id: str
    classification: ApprovedItemClassification

    @classmethod
    def from_json(cls, payload: dict) -> "DeactivateRoomItemCommand":
        classification = payload["classification"]
        if not is_supported_item_classification(classification):
            raise ValueError(f"Unsupported item classification: {classification!r}")
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            classification=classification,
        )


@dataclass(frozen=True)
class SetMobSecretWordCommand:
    room_id: str
    moderator_user_id: str
    secret_mob_word: str

    @classmethod
    def from_json(cls, payload: dict) -> "SetMobSecretWordCommand":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            secret_mob_word=_require_non_empty(payload, "secret_mob_word"),
        )


@dataclass(frozen=True)
class LaunchGameFromRoomCommand:
    room_id: str
    requested_by_user_id: str

    @classmethod
    def from_json(cls, payload: dict) -> "LaunchGameFromRoomCommand":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            requested_by_user_id=_require_non_empty(payload, "requested_by_user_id"),
        )


@dataclass(frozen=True)
class DeleteRoomCommand:
    room_id: str
    requested_by_user_id: str

    @classmethod
    def from_json(cls, payload: dict) -> "DeleteRoomCommand":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            requested_by_user_id=_require_non_empty(payload, "requested_by_user_id"),
        )


@dataclass(frozen=True)
class ShuffleRoomRolesCommand:
    room_id: str
    moderator_user_id: str
    seed: int | None = None

    @classmethod
    def from_json(cls, payload: dict) -> "ShuffleRoomRolesCommand":
        raw_seed = payload.get("seed")
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            seed=int(raw_seed) if raw_seed is not None else None,
        )


@dataclass(frozen=True)
class RoomRoleAssignmentSnapshot:
    faction: FactionName
    role_name: str
    rank: int


@dataclass(frozen=True)
class RoomMemberSnapshot:
    user_id: str
    username: str
    membership_status: MembershipStatus
    is_ready: bool
    starting_balance: int
    assigned_role: RoomRoleAssignmentSnapshot | None


@dataclass(frozen=True)
class RoomItemSnapshot:
    classification: ApprovedItemClassification
    display_name: str
    base_price: int
    image_path: str
    is_active: bool


@dataclass(frozen=True)
class RoomSnapshot:
    room_id: str
    name: str
    status: RoomStatus
    moderator_user_id: str
    member_count: int


@dataclass(frozen=True)
class RoomDetailsSnapshot:
    room_id: str
    name: str
    status: RoomStatus
    moderator_user_id: str
    opened_at_epoch_seconds: int
    members: list[RoomMemberSnapshot]
    items: list[RoomItemSnapshot]
    launched_game_id: str | None = None
    secret_mob_word: str = ""


def _require_non_empty(payload: dict, key: str) -> str:
    raw = str(payload[key]).strip()
    if not raw:
        raise ValueError(f"Field '{key}' must be non-empty.")
    return raw
