import sys
import unittest
import os
from pathlib import Path

import django


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.mobboss_apps.mobboss.settings")
django.setup()

from project.mobboss_apps.iam.adapters.outbound.django_auth_impl import (  # noqa: E402
    DjangoIamOutboundPortImpl,
)
from project.mobboss_apps.iam.adapters.outbound.memory_impl import (  # noqa: E402
    MemoryIamOutboundPortImpl,
)
from project.mobboss_apps.iam.src.iam_service import IamService  # noqa: E402
from project.mobboss_apps.economy.adapters.outbound.catalog_defaults_json_file_impl import (  # noqa: E402
    JsonFileEconomyCatalogDefaultsOutboundPortImpl,
)
from project.mobboss_apps.economy.adapters.outbound.catalog_defaults_memory_impl import (  # noqa: E402
    MemoryEconomyCatalogDefaultsOutboundPortImpl,
)
from project.mobboss_apps.gameplay.adapters.outbound.memory_impl import (  # noqa: E402
    MemoryGameplayOutboundPortImpl,
)
from project.mobboss_apps.gameplay.adapters.outbound.sqlite_impl import (  # noqa: E402
    SqliteGameplayOutboundPortImpl,
)
from project.mobboss_apps.gameplay.src.game_service import GameplayService  # noqa: E402
from project.mobboss_apps.mobboss.adapters.outbound.credentials_memory_impl import (  # noqa: E402
    MemoryCredentialsOutboundPortImpl,
)
from project.mobboss_apps.mobboss.adapters.outbound.projectsetting_memory_impl import (  # noqa: E402
    MemoryProjectSettingOutboundPortImpl,
)
from project.mobboss_apps.mobboss.composition import get_container  # noqa: E402
from project.mobboss_apps.rooms.adapters.outbound.media.filesystem_impl import (  # noqa: E402
    FilesystemRoomItemMediaOutboundPortImpl,
)
from project.mobboss_apps.rooms.adapters.outbound.media.memory_impl import (  # noqa: E402
    MemoryRoomItemMediaOutboundPortImpl,
)
from project.mobboss_apps.rooms.adapters.outbound.memory_impl import (  # noqa: E402
    MemoryRoomsOutboundPortImpl,
)
from project.mobboss_apps.rooms.adapters.outbound.sqlite_impl import (  # noqa: E402
    SqliteRoomsOutboundPortImpl,
)
from project.mobboss_apps.rooms.src.room_service import RoomsService  # noqa: E402


class CompositionContainerTests(unittest.TestCase):
    def test_get_container_default_uses_default_adapters(self) -> None:
        container = get_container()

        self.assertEqual(container.mode, "default")
        self.assertTrue(container.database_url.startswith("sqlite:///"))
        self.assertEqual(container.weights.circulating_currency_per_player, 100)
        self.assertIsInstance(container.credentials_outbound_port, MemoryCredentialsOutboundPortImpl)
        self.assertIsInstance(container.projectsetting_outbound_port, MemoryProjectSettingOutboundPortImpl)
        self.assertIsInstance(
            container.economy_catalog_defaults_outbound_port,
            JsonFileEconomyCatalogDefaultsOutboundPortImpl,
        )
        self.assertIsInstance(container.gameplay_outbound_port, SqliteGameplayOutboundPortImpl)
        self.assertIsInstance(container.gameplay_inbound_port, GameplayService)
        self.assertIsInstance(container.iam_outbound_port, DjangoIamOutboundPortImpl)
        self.assertIsInstance(container.iam_inbound_port, IamService)
        self.assertIsInstance(container.rooms_outbound_port, SqliteRoomsOutboundPortImpl)
        self.assertIsInstance(container.rooms_inbound_port, RoomsService)
        self.assertIsInstance(container.room_item_media_outbound_port, FilesystemRoomItemMediaOutboundPortImpl)

        database_credentials = container.credentials_outbound_port.get_database_credentials()
        room_settings = container.projectsetting_outbound_port.get_room_project_settings()
        media_settings = container.projectsetting_outbound_port.get_media_project_settings()

        self.assertEqual(database_credentials.database_url, container.database_url)
        self.assertIsNotNone(media_settings.media_root)
        self.assertEqual(media_settings.media_url, "/media/")
        self.assertGreaterEqual(room_settings.minimum_launch_players, 1)
        self.assertGreaterEqual(room_settings.state_poll_interval_seconds, 5)
        self.assertGreaterEqual(room_settings.auto_shuffle_interval_seconds, 10)
        self.assertEqual(room_settings.minimum_launch_players, container.room_min_launch_players)
        self.assertEqual(room_settings.dev_mode, container.room_dev_mode)

    def test_get_container_unittest_uses_memory_adapters(self) -> None:
        container = get_container(mode="unittest")

        self.assertEqual(container.mode, "unittest")
        self.assertEqual(container.database_url, "sqlite://:memory:")
        self.assertIsInstance(container.credentials_outbound_port, MemoryCredentialsOutboundPortImpl)
        self.assertIsInstance(container.projectsetting_outbound_port, MemoryProjectSettingOutboundPortImpl)
        self.assertIsInstance(
            container.economy_catalog_defaults_outbound_port,
            MemoryEconomyCatalogDefaultsOutboundPortImpl,
        )
        self.assertIsInstance(container.gameplay_outbound_port, MemoryGameplayOutboundPortImpl)
        self.assertIsInstance(container.gameplay_inbound_port, GameplayService)
        self.assertIsInstance(container.iam_outbound_port, MemoryIamOutboundPortImpl)
        self.assertIsInstance(container.iam_inbound_port, IamService)
        self.assertIsInstance(container.rooms_outbound_port, MemoryRoomsOutboundPortImpl)
        self.assertIsInstance(container.rooms_inbound_port, RoomsService)
        self.assertIsInstance(container.room_item_media_outbound_port, MemoryRoomItemMediaOutboundPortImpl)

        database_credentials = container.credentials_outbound_port.get_database_credentials()
        room_settings = container.projectsetting_outbound_port.get_room_project_settings()
        media_settings = container.projectsetting_outbound_port.get_media_project_settings()

        self.assertEqual(database_credentials.database_url, "sqlite://:memory:")
        self.assertIsNone(media_settings.media_root)
        self.assertEqual(media_settings.media_url, "/media/")
        self.assertEqual(room_settings.minimum_launch_players, 1)
        self.assertTrue(room_settings.dev_mode)
        self.assertEqual(room_settings.state_poll_interval_seconds, 5)
        self.assertEqual(room_settings.auto_shuffle_interval_seconds, 10)


if __name__ == "__main__":
    unittest.main()
