import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.economy.adapters.outbound.catalog_defaults_json_file_impl import (  # noqa: E402
    JsonFileEconomyCatalogDefaultsOutboundPortImpl,
)
from project.mobboss_apps.economy.ports.internal import ItemClassification  # noqa: E402

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"


class JsonFileEconomyCatalogDefaultsAdapterTests(unittest.TestCase):
    def test_load_default_catalog_items_reads_fixture_json(self) -> None:
        adapter = JsonFileEconomyCatalogDefaultsOutboundPortImpl(
            defaults_json_path=FIXTURES_ROOT / "catalog_defaults_valid.json"
        )

        items = adapter.load_default_catalog_items()

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].classification, ItemClassification.KNIFE)
        self.assertEqual(items[0].display_name, "Knife")
        self.assertEqual(items[0].base_price, 100)
        self.assertEqual(items[1].classification, ItemClassification.GUN_TIER_1)
        self.assertEqual(items[1].base_price, 200)

    def test_load_default_catalog_items_rejects_invalid_classification(self) -> None:
        adapter = JsonFileEconomyCatalogDefaultsOutboundPortImpl(
            defaults_json_path=FIXTURES_ROOT / "catalog_defaults_invalid_classification.json"
        )

        with self.assertRaises(ValueError):
            adapter.load_default_catalog_items()


if __name__ == "__main__":
    unittest.main()
