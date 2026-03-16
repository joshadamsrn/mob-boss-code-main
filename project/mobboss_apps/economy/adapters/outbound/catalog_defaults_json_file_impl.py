"""JSON-file adapter for default economy catalog records."""

from __future__ import annotations

import json
from pathlib import Path

from project.mobboss_apps.economy.ports.internal import CatalogItemDefaultRecord, ItemClassification
from project.mobboss_apps.economy.ports.outbound import EconomyCatalogDefaultsOutboundPort


class JsonFileEconomyCatalogDefaultsOutboundPortImpl(EconomyCatalogDefaultsOutboundPort):
    def __init__(self, defaults_json_path: str | Path) -> None:
        self._defaults_json_path = Path(defaults_json_path)

    def load_default_catalog_items(self) -> list[CatalogItemDefaultRecord]:
        with self._defaults_json_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        raw_items = payload.get("items", [])
        defaults: list[CatalogItemDefaultRecord] = []
        for raw in raw_items:
            defaults.append(
                CatalogItemDefaultRecord(
                    classification=ItemClassification(raw["classification"]),
                    display_name=str(raw["display_name"]),
                    base_price=int(raw["base_price"]),
                    default_image_path=str(raw["default_image_path"]),
                )
            )
        return defaults

