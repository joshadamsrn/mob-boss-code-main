"""Request DTOs used by inbound HTTP adapters as an anti-corruption layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import cast

from project.mobboss_apps.rooms.ports.internal import (
    FACTION_NAMES,
    ApprovedItemClassification,
    AssignRoomRoleCommand,
    CreateRoomCommand,
    DeactivateRoomItemCommand,
    DeleteRoomCommand,
    JoinRoomCommand,
    LeaveRoomCommand,
    LaunchGameFromRoomCommand,
    SetMobSecretWordCommand,
    SetMemberBalanceCommand,
    SetRoomReadinessCommand,
    ShuffleRoomRolesCommand,
    UpsertRoomItemCommand,
    is_supported_item_classification,
)


@dataclass(frozen=True)
class RoomIdRequestDTO:
    room_id: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RoomIdRequestDTO":
        return cls(room_id=_require_non_empty(payload, "room_id"))


@dataclass(frozen=True)
class RoomsIndexRequestDTO:
    method: str
    user_id: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RoomsIndexRequestDTO":
        method = _parse_method(payload.get("method"), key="method")
        return cls(method=method, user_id=_require_non_empty(payload, "user_id"))


@dataclass(frozen=True)
class CreateRoomRequestDTO:
    name: str
    creator_user_id: str
    creator_username: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CreateRoomRequestDTO":
        return cls(
            name=_require_non_empty(payload, "name"),
            creator_user_id=_require_non_empty(payload, "creator_user_id"),
            creator_username=_string(payload, "creator_username"),
        )

    def to_command(self) -> CreateRoomCommand:
        return CreateRoomCommand(
            name=self.name,
            creator_user_id=self.creator_user_id,
            creator_username=self.creator_username,
        )


@dataclass(frozen=True)
class JoinRoomRequestDTO:
    room_id: str
    user_id: str
    username: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "JoinRoomRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            user_id=_require_non_empty(payload, "user_id"),
            username=_string(payload, "username"),
        )

    def to_command(self) -> JoinRoomCommand:
        return JoinRoomCommand(room_id=self.room_id, user_id=self.user_id, username=self.username)


@dataclass(frozen=True)
class LeaveRoomRequestDTO:
    room_id: str
    user_id: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LeaveRoomRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            user_id=_require_non_empty(payload, "user_id"),
        )

    def to_command(self) -> LeaveRoomCommand:
        return LeaveRoomCommand(room_id=self.room_id, user_id=self.user_id)


@dataclass(frozen=True)
class SetRoomReadinessRequestDTO:
    room_id: str
    requested_by_user_id: str
    user_id: str
    is_ready: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SetRoomReadinessRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            requested_by_user_id=_require_non_empty(payload, "requested_by_user_id"),
            user_id=_require_non_empty(payload, "user_id"),
            is_ready=_parse_bool(payload.get("is_ready"), key="is_ready"),
        )

    def to_command(self) -> SetRoomReadinessCommand:
        return SetRoomReadinessCommand(
            room_id=self.room_id,
            requested_by_user_id=self.requested_by_user_id,
            user_id=self.user_id,
            is_ready=self.is_ready,
        )


@dataclass(frozen=True)
class AssignRoomRoleRequestDTO:
    room_id: str
    moderator_user_id: str
    target_user_id: str
    faction: str
    role_name: str
    rank: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AssignRoomRoleRequestDTO":
        faction = _require_non_empty(payload, "faction")
        if faction not in FACTION_NAMES:
            raise ValueError(f"Unsupported faction: {faction!r}")

        rank = _parse_int(payload.get("rank"), key="rank")
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

    def to_command(self) -> AssignRoomRoleCommand:
        return AssignRoomRoleCommand(
            room_id=self.room_id,
            moderator_user_id=self.moderator_user_id,
            target_user_id=self.target_user_id,
            faction=cast(Any, self.faction),
            role_name=self.role_name,
            rank=self.rank,
        )


@dataclass(frozen=True)
class SetMemberBalanceRequestDTO:
    room_id: str
    moderator_user_id: str
    target_user_id: str
    starting_balance: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SetMemberBalanceRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            starting_balance=_parse_int(payload.get("starting_balance"), key="starting_balance"),
        )

    def to_command(self) -> SetMemberBalanceCommand:
        return SetMemberBalanceCommand(
            room_id=self.room_id,
            moderator_user_id=self.moderator_user_id,
            target_user_id=self.target_user_id,
            starting_balance=self.starting_balance,
        )


@dataclass(frozen=True)
class UpsertRoomItemRequestDTO:
    room_id: str
    moderator_user_id: str
    classification: ApprovedItemClassification
    display_name: str
    base_price: int
    image_path: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "UpsertRoomItemRequestDTO":
        classification = _parse_item_classification(payload.get("classification"), key="classification")
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            classification=classification,
            display_name=_require_non_empty(payload, "display_name"),
            base_price=_parse_int(payload.get("base_price"), key="base_price"),
            image_path=_string(payload, "image_path"),
        )

    def to_command(self) -> UpsertRoomItemCommand:
        return UpsertRoomItemCommand(
            room_id=self.room_id,
            moderator_user_id=self.moderator_user_id,
            classification=self.classification,
            display_name=self.display_name,
            base_price=self.base_price,
            image_path=self.image_path,
        )


@dataclass(frozen=True)
class CatalogItemImageRequestDTO:
    room_id: str
    moderator_user_id: str
    classification: ApprovedItemClassification
    image_path: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CatalogItemImageRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            classification=_parse_item_classification(payload.get("classification"), key="classification"),
            image_path=_require_non_empty(payload, "image_path"),
        )

    def to_upsert_item_request(self, *, display_name: str, base_price: int) -> UpsertRoomItemRequestDTO:
        return UpsertRoomItemRequestDTO(
            room_id=self.room_id,
            moderator_user_id=self.moderator_user_id,
            classification=self.classification,
            display_name=display_name,
            base_price=base_price,
            image_path=self.image_path,
        )


@dataclass(frozen=True)
class DeactivateRoomItemRequestDTO:
    room_id: str
    moderator_user_id: str
    classification: ApprovedItemClassification

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DeactivateRoomItemRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            classification=_parse_item_classification(payload.get("classification"), key="classification"),
        )

    def to_command(self) -> DeactivateRoomItemCommand:
        return DeactivateRoomItemCommand(
            room_id=self.room_id,
            moderator_user_id=self.moderator_user_id,
            classification=self.classification,
        )


@dataclass(frozen=True)
class SetMobSecretWordRequestDTO:
    room_id: str
    moderator_user_id: str
    secret_mob_word: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SetMobSecretWordRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            secret_mob_word=_require_non_empty(payload, "secret_mob_word"),
        )

    def to_command(self) -> SetMobSecretWordCommand:
        return SetMobSecretWordCommand(
            room_id=self.room_id,
            moderator_user_id=self.moderator_user_id,
            secret_mob_word=self.secret_mob_word,
        )


@dataclass(frozen=True)
class LaunchGameFromRoomRequestDTO:
    room_id: str
    requested_by_user_id: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LaunchGameFromRoomRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            requested_by_user_id=_require_non_empty(payload, "requested_by_user_id"),
        )

    def to_command(self) -> LaunchGameFromRoomCommand:
        return LaunchGameFromRoomCommand(
            room_id=self.room_id,
            requested_by_user_id=self.requested_by_user_id,
        )


@dataclass(frozen=True)
class DeleteRoomRequestDTO:
    room_id: str
    requested_by_user_id: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DeleteRoomRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            requested_by_user_id=_require_non_empty(payload, "requested_by_user_id"),
        )

    def to_command(self) -> DeleteRoomCommand:
        return DeleteRoomCommand(
            room_id=self.room_id,
            requested_by_user_id=self.requested_by_user_id,
        )


@dataclass(frozen=True)
class ShuffleRoomRolesRequestDTO:
    room_id: str
    moderator_user_id: str
    seed: int | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ShuffleRoomRolesRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            seed=_optional_int(payload.get("seed"), key="seed"),
        )

    def to_command(self) -> ShuffleRoomRolesCommand:
        return ShuffleRoomRolesCommand(
            room_id=self.room_id,
            moderator_user_id=self.moderator_user_id,
            seed=self.seed,
        )


@dataclass(frozen=True)
class RoomDetailRequestDTO:
    room_id: str
    user_id: str
    username: str
    autojoin_requested: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RoomDetailRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            user_id=_require_non_empty(payload, "user_id"),
            username=_string(payload, "username"),
            autojoin_requested=_parse_bool(payload.get("autojoin"), key="autojoin", default=False),
        )


@dataclass(frozen=True)
class ShuffleRolesPageRequestDTO:
    room_id: str
    moderator_user_id: str
    seed: int | None
    is_silent: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ShuffleRolesPageRequestDTO":
        return cls(
            room_id=_require_non_empty(payload, "room_id"),
            moderator_user_id=_require_non_empty(payload, "moderator_user_id"),
            seed=_optional_int(payload.get("seed"), key="seed"),
            is_silent=_parse_bool(payload.get("is_silent"), key="is_silent", default=False),
        )

    def to_command(self) -> ShuffleRoomRolesCommand:
        return ShuffleRoomRolesCommand(
            room_id=self.room_id,
            moderator_user_id=self.moderator_user_id,
            seed=self.seed,
        )


def _string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _require_non_empty(payload: dict[str, Any], key: str) -> str:
    value = _string(payload, key)
    if not value:
        raise ValueError(f"Field '{key}' must be non-empty.")
    return value


def _parse_item_classification(raw: Any, *, key: str) -> ApprovedItemClassification:
    value = str(raw if raw is not None else "").strip()
    if not is_supported_item_classification(value):
        raise ValueError(f"Unsupported item classification: {value!r}")
    return cast(ApprovedItemClassification, value)


def _parse_int(raw: Any, *, key: str) -> int:
    if raw is None:
        raise ValueError(f"Field '{key}' must be an integer.")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field '{key}' must be an integer.") from exc


def _optional_int(raw: Any, *, key: str) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    return _parse_int(raw, key=key)


def _parse_bool(raw: Any, *, key: str, default: bool | None = None) -> bool:
    if raw is None:
        if default is None:
            raise ValueError(f"Field '{key}' must be a boolean.")
        return default
    if isinstance(raw, bool):
        return raw

    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Field '{key}' must be a boolean.")


def _parse_method(raw: Any, *, key: str) -> str:
    value = str(raw if raw is not None else "").strip().upper()
    if value not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise ValueError(f"Field '{key}' has unsupported HTTP method: {value!r}")
    return value
