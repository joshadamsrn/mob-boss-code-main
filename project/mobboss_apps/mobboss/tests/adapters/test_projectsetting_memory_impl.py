import sys
import unittest
from pathlib import Path

from django.test import SimpleTestCase, override_settings


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.mobboss.adapters.outbound.projectsetting_memory_impl import (  # noqa: E402
    MemoryProjectSettingOutboundPortImpl,
)


class ProjectSettingAdapterTests(SimpleTestCase):
    @override_settings(ROOM_DEV_MODE=False, ROOM_MIN_LAUNCH_PLAYERS=2)
    def test_non_dev_mode_enforces_minimum_launch_floor(self) -> None:
        adapter = MemoryProjectSettingOutboundPortImpl.build_default()
        room_settings = adapter.get_room_project_settings()

        self.assertFalse(room_settings.dev_mode)
        self.assertEqual(room_settings.minimum_launch_players, 7)

    @override_settings(ROOM_DEV_MODE=True, ROOM_MIN_LAUNCH_PLAYERS=2)
    def test_dev_mode_allows_lower_minimum_launch_players(self) -> None:
        adapter = MemoryProjectSettingOutboundPortImpl.build_default()
        room_settings = adapter.get_room_project_settings()

        self.assertTrue(room_settings.dev_mode)
        self.assertEqual(room_settings.minimum_launch_players, 2)

    @override_settings(ROOM_DEV_MODE="1", ROOM_MIN_LAUNCH_PLAYERS=3)
    def test_dev_mode_accepts_truthy_string_setting(self) -> None:
        adapter = MemoryProjectSettingOutboundPortImpl.build_default()
        room_settings = adapter.get_room_project_settings()

        self.assertTrue(room_settings.dev_mode)
        self.assertEqual(room_settings.minimum_launch_players, 3)


if __name__ == "__main__":
    unittest.main()
