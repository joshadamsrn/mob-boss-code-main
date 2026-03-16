"""Default item catalog helpers for economy seeding and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from project.mobboss_apps.economy.ports.outbound import EconomyCatalogDefaultsOutboundPort

ItemClassification = Literal[
    "knife",
    "gun_tier_1",
    "gun_tier_2",
    "gun_tier_3",
    "bulletproof_vest",
    "escape_from_jail",
]

ALLOWED_ITEM_CLASSIFICATIONS: tuple[ItemClassification, ...] = (
    "knife",
    "gun_tier_1",
    "gun_tier_2",
    "gun_tier_3",
    "bulletproof_vest",
    "escape_from_jail",
)


@dataclass(frozen=True)
class CatalogItemDefault:
    classification: ItemClassification
    display_name: str
    base_price: int
    default_image_path: str


def load_default_catalog_items(defaults_outbound_port: EconomyCatalogDefaultsOutboundPort) -> list[CatalogItemDefault]:
    """Load and validate canonical defaults from an outbound adapter."""

    raw_items = defaults_outbound_port.load_default_catalog_items()
    defaults: list[CatalogItemDefault] = []

    for raw in raw_items:
        classification = str(raw.classification)
        if classification not in ALLOWED_ITEM_CLASSIFICATIONS:
            raise ValueError(f"Unsupported item classification in defaults adapter: {classification!r}")

        defaults.append(
            CatalogItemDefault(
                classification=classification,
                display_name=raw.display_name,
                base_price=int(raw.base_price),
                default_image_path=raw.default_image_path,
            )
        )

    return defaults

