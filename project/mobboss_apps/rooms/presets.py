"""Helpers for moderator-owned central supply presets."""

from __future__ import annotations

from dataclasses import dataclass

from rooms.models import RoomSupplyPreset
from project.mobboss_apps.rooms.ports.internal import RoomItemSnapshot, is_supported_item_classification

MAX_ROOM_SUPPLY_PRESETS = 10


@dataclass(frozen=True)
class GeneratedSupplyRow:
    classification: str
    display_name: str
    base_price: int
    image_path: str


def list_room_supply_presets_for_user(user: object) -> list[dict[str, object]]:
    if not getattr(user, "is_authenticated", False):
        return []
    try:
        presets = RoomSupplyPreset.objects.filter(user_id=getattr(user, "id", None)).order_by("name", "id")
        return [serialize_room_supply_preset(preset) for preset in presets]
    except Exception:
        return []


def get_room_supply_preset_for_user(user: object, preset_id: int) -> RoomSupplyPreset:
    if not getattr(user, "is_authenticated", False):
        raise PermissionError("Only authenticated moderators can manage presets.")
    return RoomSupplyPreset.objects.get(user_id=getattr(user, "id", None), id=int(preset_id))


def serialize_room_supply_preset(preset: RoomSupplyPreset) -> dict[str, object]:
    payload = preset.payload if isinstance(preset.payload, dict) else {}
    rows = preset_rows_from_payload(payload)
    return {
        "id": preset.id,
        "name": preset.name,
        "updated_at": preset.updated_at.isoformat() if preset.updated_at is not None else "",
        "counts": payload.get("counts", build_counts_from_rows(rows)),
        "rows": [row.__dict__ for row in rows],
    }


def normalize_generated_supply_rows(raw_rows: list[dict[str, object]]) -> list[GeneratedSupplyRow]:
    normalized: list[GeneratedSupplyRow] = []
    seen_classifications: set[str] = set()
    for raw_row in raw_rows:
        classification = str(raw_row.get("classification", "")).strip()
        if not is_supported_item_classification(classification):
            raise ValueError(f"Unsupported item classification: {classification!r}")
        if classification in seen_classifications:
            raise ValueError(f"Duplicate generated catalog item: {classification!r}")
        seen_classifications.add(classification)

        display_name = str(raw_row.get("display_name", raw_row.get("displayName", ""))).strip()
        if not display_name:
            raise ValueError("Generated catalog item name is required.")

        try:
            base_price = int(raw_row.get("base_price", raw_row.get("price", 0)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid base price for {classification!r}.") from exc
        base_price = _round_to_nearest_ten(base_price)
        if base_price < 0:
            raise ValueError("Catalog item base price must be >= 0.")

        image_path = str(raw_row.get("image_path", raw_row.get("imagePath", ""))).strip()
        normalized.append(
            GeneratedSupplyRow(
                classification=classification,
                display_name=display_name,
                base_price=base_price,
                image_path=image_path or default_image_path_for_classification(classification),
            )
        )
    return normalized


def build_preset_payload_from_rows(rows: list[GeneratedSupplyRow]) -> dict[str, object]:
    return {
        "version": 1,
        "counts": build_counts_from_rows(rows),
        "rows": [row.__dict__ for row in rows],
    }


def build_preset_payload_from_room_items(items: list[RoomItemSnapshot]) -> dict[str, object]:
    active_items = [item for item in items if item.is_active]
    rows = [
        GeneratedSupplyRow(
            classification=item.classification,
            display_name=item.display_name,
            base_price=int(item.base_price),
            image_path=str(item.image_path or "").strip() or default_image_path_for_classification(item.classification),
        )
        for item in active_items
    ]
    return build_preset_payload_from_rows(rows)


def preset_rows_from_payload(payload: dict[str, object]) -> list[GeneratedSupplyRow]:
    raw_rows = payload.get("rows", [])
    if not isinstance(raw_rows, list):
        return []
    filtered_rows = [row for row in raw_rows if isinstance(row, dict)]
    return normalize_generated_supply_rows(filtered_rows)


def build_room_items_from_rows(rows: list[GeneratedSupplyRow]) -> list[RoomItemSnapshot]:
    return [
        RoomItemSnapshot(
            classification=row.classification,
            display_name=row.display_name,
            base_price=row.base_price,
            image_path=row.image_path or default_image_path_for_classification(row.classification),
            is_active=True,
        )
        for row in rows
    ]


def build_counts_from_rows(rows: list[GeneratedSupplyRow]) -> dict[str, int]:
    counts = {
        "tier_1_gun_count": 0,
        "tier_2_gun_count": 0,
        "tier_3_gun_count": 0,
        "knife_count": 0,
    }
    for row in rows:
        bucket = _classification_bucket(row.classification)
        if bucket == "gun_tier_1":
            counts["tier_1_gun_count"] += 1
        elif bucket == "gun_tier_2":
            counts["tier_2_gun_count"] += 1
        elif bucket == "gun_tier_3":
            counts["tier_3_gun_count"] += 1
        elif bucket == "knife":
            counts["knife_count"] += 1
    return counts


def default_image_path_for_classification(classification: str) -> str:
    bucket = _classification_bucket(classification)
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


def _classification_bucket(classification: str) -> str | None:
    normalized = str(classification).strip()
    if normalized in {"gun_tier_1", "gun_tier_2", "gun_tier_3", "knife", "bulletproof_vest", "escape_from_jail"}:
        return normalized
    if normalized.startswith("gun_tier_1_"):
        return "gun_tier_1"
    if normalized.startswith("gun_tier_2_"):
        return "gun_tier_2"
    if normalized.startswith("gun_tier_3_"):
        return "gun_tier_3"
    if normalized.startswith("knife_"):
        return "knife"
    return None


def _round_to_nearest_ten(value: int) -> int:
    remainder = value % 10
    if remainder >= 5:
        return value + (10 - remainder)
    return value - remainder
