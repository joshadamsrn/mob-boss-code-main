import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.rooms.v1_views import AssignRoleView, ReadinessView, RoomsCollectionView  # noqa: E402

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"


def _load_fixture_text(name: str) -> str:
    return (FIXTURES_ROOT / name).read_text(encoding="utf-8")


class _StubRoomsInboundPort:
    def create_room(self, command):  # pragma: no cover - defensive
        raise AssertionError("create_room should not be called for invalid payloads.")

    def set_room_readiness(self, command):  # pragma: no cover - defensive
        raise AssertionError("set_room_readiness should not be called for invalid payloads.")

    def assign_room_role(self, command):  # pragma: no cover - defensive
        raise AssertionError("assign_room_role should not be called when dev mode is disabled.")


class _StubContainer:
    def __init__(self) -> None:
        self.rooms_inbound_port = _StubRoomsInboundPort()
        self.room_dev_mode = False


class RoomsV1RestValidationTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = type(
            "StubUser",
            (),
            {"is_authenticated": True, "id": "u_mod", "username": "moderator"},
        )()

    @patch("project.mobboss_apps.rooms.v1_views.get_container", return_value=_StubContainer())
    def test_create_room_requires_name(self, _mock_get_container) -> None:
        request = self.factory.post(
            "/rooms/v1/",
            data=_load_fixture_text("create_room_missing_name.json"),
            content_type="application/json",
        )
        request.user = self.user

        response = RoomsCollectionView.as_view()(request)

        self.assertEqual(response.status_code, 422)

    @patch("project.mobboss_apps.rooms.v1_views.get_container", return_value=_StubContainer())
    def test_readiness_requires_boolean(self, _mock_get_container) -> None:
        request = self.factory.post(
            "/rooms/v1/r-1/readiness",
            data=_load_fixture_text("readiness_invalid_boolean.json"),
            content_type="application/json",
        )
        request.user = self.user

        response = ReadinessView.as_view()(request, room_id="r-1")

        self.assertEqual(response.status_code, 422)

    @patch("project.mobboss_apps.rooms.v1_views.get_container", return_value=_StubContainer())
    def test_assign_role_requires_dev_mode(self, _mock_get_container) -> None:
        request = self.factory.post(
            "/rooms/v1/r-1/roles/assign",
            data='{"target_user_id":"u_1","role_name":"Deputy","faction":"Police","rank":2}',
            content_type="application/json",
        )
        request.user = self.user

        response = AssignRoleView.as_view()(request, room_id="r-1")

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
