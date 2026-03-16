"""Inbound ports: system stimulation contracts."""

from __future__ import annotations

from typing import Protocol

from .internal import (
    CatalogItemSnapshot,
    CreateCatalogItemCommand,
    ReplaceCatalogItemImageCommand,
    SeedCatalogDefaultsCommand,
    SetCatalogItemPriceCommand,
)


class EconomyInboundPort(Protocol):
    def seed_default_catalog(self, command: SeedCatalogDefaultsCommand) -> list[CatalogItemSnapshot]:
        ...

    def create_catalog_item(self, command: CreateCatalogItemCommand) -> CatalogItemSnapshot:
        ...

    def set_catalog_item_price(self, command: SetCatalogItemPriceCommand) -> CatalogItemSnapshot:
        ...

    def replace_catalog_item_image(self, command: ReplaceCatalogItemImageCommand) -> CatalogItemSnapshot:
        ...

    def list_catalog_items(self, game_id: str) -> list[CatalogItemSnapshot]:
        ...
