"""Internal ports: DTOs and data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ItemClassification(str, Enum):
    KNIFE = "knife"
    GUN_TIER_1 = "gun_tier_1"
    GUN_TIER_2 = "gun_tier_2"
    GUN_TIER_3 = "gun_tier_3"
    BULLETPROOF_VEST = "bulletproof_vest"
    ESCAPE_FROM_JAIL = "escape_from_jail"


@dataclass(frozen=True)
class CatalogItemDefaultRecord:
    classification: ItemClassification
    display_name: str
    base_price: int
    default_image_path: str


@dataclass(frozen=True)
class CatalogItemSnapshot:
    item_id: str
    game_id: str
    classification: ItemClassification
    display_name: str
    base_price: int
    image_path: str
    is_active: bool


@dataclass(frozen=True)
class CreateCatalogItemCommand:
    game_id: str
    classification: ItemClassification
    display_name: str
    base_price: int

    @classmethod
    def from_json(cls, payload: dict) -> "CreateCatalogItemCommand":
        return cls(
            game_id=str(payload["game_id"]).strip(),
            classification=ItemClassification(payload["classification"]),
            display_name=str(payload["display_name"]).strip(),
            base_price=int(payload["base_price"]),
        )


@dataclass(frozen=True)
class SetCatalogItemPriceCommand:
    game_id: str
    item_id: str
    moderator_user_id: str
    base_price: int

    @classmethod
    def from_json(cls, payload: dict) -> "SetCatalogItemPriceCommand":
        return cls(
            game_id=str(payload["game_id"]).strip(),
            item_id=str(payload["item_id"]).strip(),
            moderator_user_id=str(payload["moderator_user_id"]).strip(),
            base_price=int(payload["base_price"]),
        )


@dataclass(frozen=True)
class ReplaceCatalogItemImageCommand:
    game_id: str
    item_id: str
    moderator_user_id: str
    image_path: str

    @classmethod
    def from_json(cls, payload: dict) -> "ReplaceCatalogItemImageCommand":
        return cls(
            game_id=str(payload["game_id"]).strip(),
            item_id=str(payload["item_id"]).strip(),
            moderator_user_id=str(payload["moderator_user_id"]).strip(),
            image_path=str(payload["image_path"]).strip(),
        )


@dataclass(frozen=True)
class SeedCatalogDefaultsCommand:
    game_id: str
    moderator_user_id: str

    @classmethod
    def from_json(cls, payload: dict) -> "SeedCatalogDefaultsCommand":
        return cls(
            game_id=str(payload["game_id"]).strip(),
            moderator_user_id=str(payload["moderator_user_id"]).strip(),
        )
