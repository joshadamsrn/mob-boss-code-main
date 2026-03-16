"""Outbound ports: external resource contracts."""

from __future__ import annotations

from typing import Protocol

from .internal import CatalogItemDefaultRecord, CatalogItemSnapshot


class EconomyOutboundPort(Protocol):
    def save_catalog_item(self, item: CatalogItemSnapshot) -> None:
        ...

    def get_catalog_item(self, game_id: str, item_id: str) -> CatalogItemSnapshot | None:
        ...

    def list_catalog_items(self, game_id: str) -> list[CatalogItemSnapshot]:
        ...


class EconomyCatalogDefaultsOutboundPort(Protocol):
    def load_default_catalog_items(self) -> list[CatalogItemDefaultRecord]:
        ...
