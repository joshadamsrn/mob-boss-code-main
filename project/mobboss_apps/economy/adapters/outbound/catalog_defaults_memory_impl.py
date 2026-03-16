"""In-memory adapter for default economy catalog records."""

from project.mobboss_apps.economy.ports.internal import CatalogItemDefaultRecord, ItemClassification
from project.mobboss_apps.economy.ports.outbound import EconomyCatalogDefaultsOutboundPort


class MemoryEconomyCatalogDefaultsOutboundPortImpl(EconomyCatalogDefaultsOutboundPort):
    def load_default_catalog_items(self) -> list[CatalogItemDefaultRecord]:
        return [
            CatalogItemDefaultRecord(
                classification=ItemClassification.KNIFE,
                display_name="Knife",
                base_price=100,
                default_image_path="/static/items/defaults/default_knife.svg",
            ),
            CatalogItemDefaultRecord(
                classification=ItemClassification.GUN_TIER_1,
                display_name="Handgun (Tier 1)",
                base_price=100,
                default_image_path="/static/items/defaults/default_gun_tier_1.svg",
            ),
            CatalogItemDefaultRecord(
                classification=ItemClassification.GUN_TIER_2,
                display_name="Pistol (Tier 2)",
                base_price=100,
                default_image_path="/static/items/defaults/default_gun_tier_2.svg",
            ),
            CatalogItemDefaultRecord(
                classification=ItemClassification.GUN_TIER_3,
                display_name="Revolver (Tier 3)",
                base_price=100,
                default_image_path="/static/items/defaults/default_gun_tier_3.svg",
            ),
            CatalogItemDefaultRecord(
                classification=ItemClassification.BULLETPROOF_VEST,
                display_name="Bulletproof Vest",
                base_price=100,
                default_image_path="/static/items/defaults/default_bulletproof_vest.svg",
            ),
            CatalogItemDefaultRecord(
                classification=ItemClassification.ESCAPE_FROM_JAIL,
                display_name="Escape From Jail",
                base_price=100,
                default_image_path="/static/items/defaults/default_escape_from_jail.svg",
            ),
        ]

