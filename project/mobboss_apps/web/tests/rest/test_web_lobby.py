import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.rooms.ports.internal import RoomDetailsSnapshot, RoomSnapshot  # noqa: E402
from project.mobboss_apps.web.views import (  # noqa: E402
    advance_accused_timeout,
    how_to_play,
    index,
    moderator_add_funds,
    moderator_report_death,
    moderator_transfer_funds,
    moderator_transfer_inventory_item,
    options,
)


class _StubRoomsInboundPort:
    def list_active_rooms(self):
        return [
            RoomSnapshot(
                room_id="r-full",
                name="Full Room",
                status="lobby",
                moderator_user_id="u_mod",
                member_count=25,
            )
        ]


class _StubContainer:
    def __init__(self) -> None:
        self.rooms_inbound_port = _StubRoomsInboundPort()


class WebLobbyViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = type("StubUser", (), {"is_authenticated": True, "id": "u_1", "username": "player1"})()
        self.paid_user = type(
            "StubPaidUser",
            (),
            {"is_authenticated": True, "id": "u_mod", "username": "moderator", "has_moderator_access": True},
        )()

    @patch("project.mobboss_apps.web.views.get_container", return_value=_StubContainer())
    def test_lobby_shows_room_full_badge_for_full_lobby_room(self, _mock_get_container) -> None:
        request = self.factory.get("/")
        request.user = self.user

        response = index(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Room Full")

    @patch("project.mobboss_apps.web.views.get_container", return_value=_StubContainer())
    def test_lobby_renders_inline_create_room_form(self, _mock_get_container) -> None:
        request = self.factory.get("/")
        request.user = self.user

        response = index(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<form method="post" action="/rooms/create"', html=False)
        self.assertContains(response, "Create Room")

    @patch("project.mobboss_apps.web.views.get_container", return_value=_StubContainer())
    def test_lobby_prompts_for_permission_code_when_user_lacks_moderator_access(self, _mock_get_container) -> None:
        request = self.factory.get("/")
        request.user = self.user

        response = index(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="moderator_access_code"', html=False)
        self.assertContains(response, "Permission Code")

    @patch("project.mobboss_apps.web.views.get_container", return_value=_StubContainer())
    def test_lobby_hides_permission_code_when_user_already_has_moderator_access(self, _mock_get_container) -> None:
        request = self.factory.get("/")
        request.user = self.paid_user

        response = index(request)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="moderator_access_code"', html=False)

    @patch("project.mobboss_apps.web.views.get_container", return_value=_StubContainer())
    def test_lobby_renders_how_to_play_link(self, _mock_get_container) -> None:
        request = self.factory.get("/")
        request.user = self.user

        response = index(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/how-to-play/"', html=False)
        self.assertContains(response, "How to Play Mob Boss")


class _StubRoomsInboundForOptions:
    def __init__(self, *, moderator_user_id: str, launched_game_id: str | None = "g-1") -> None:
        self._moderator_user_id = moderator_user_id
        self._launched_game_id = launched_game_id

    def list_active_rooms(self):
        return [
            RoomSnapshot(
                room_id="r-1",
                name="Active Room",
                status="in_progress",
                moderator_user_id=self._moderator_user_id,
                member_count=7,
            )
        ]

    def get_room_details(self, _room_id: str):
        return RoomDetailsSnapshot(
            room_id="r-1",
            name="Active Room",
            status="in_progress",
            moderator_user_id=self._moderator_user_id,
            opened_at_epoch_seconds=1,
            members=[],
            items=[],
            launched_game_id=self._launched_game_id,
            secret_mob_word="",
        )


class _StubGameplayInboundForOptions:
    def __init__(self, *, status: str = "in_progress") -> None:
        self.advanced_commands = []
        self.reported_deaths = []
        self.moderator_add_funds_commands = []
        self.moderator_transfer_funds_commands = []
        self.moderator_transfer_inventory_item_commands = []
        self.status = status

    def get_game_details(self, _game_id: str):
        return SimpleNamespace(
            game_id="g-1",
            version=5,
            status=self.status,
            phase="accused_selection",
            pending_trial=SimpleNamespace(accused_selection_deadline_epoch_seconds=100),
            participants=[
                SimpleNamespace(
                    user_id="u_p1",
                    username="player1",
                    life_state="alive",
                    inventory=[SimpleNamespace(item_id="inv-1", display_name="Knife")],
                    money_balance=300,
                ),
                SimpleNamespace(
                    user_id="u_p2",
                    username="player2",
                    life_state="alive",
                    inventory=[],
                    money_balance=300,
                ),
            ],
        )

    def advance_accused_selection_timeout(self, command):
        self.advanced_commands.append(command)

    def report_death(self, command):
        self.reported_deaths.append(command)

    def moderator_add_funds(self, command):
        self.moderator_add_funds_commands.append(command)

    def moderator_transfer_funds(self, command):
        self.moderator_transfer_funds_commands.append(command)

    def moderator_transfer_inventory_item(self, command):
        self.moderator_transfer_inventory_item_commands.append(command)


class _StubContainerForOptions:
    def __init__(
        self,
        *,
        moderator_user_id: str,
        launched_game_id: str | None = "g-1",
        gameplay_status: str = "in_progress",
    ) -> None:
        self.rooms_inbound_port = _StubRoomsInboundForOptions(
            moderator_user_id=moderator_user_id,
            launched_game_id=launched_game_id,
        )
        self.gameplay_inbound_port = _StubGameplayInboundForOptions(status=gameplay_status)


class WebOptionsViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.moderator = type("StubUser", (), {"is_authenticated": True, "id": "u_mod", "username": "moderator"})()
        self.player = type("StubUser", (), {"is_authenticated": True, "id": "u_p1", "username": "player1"})()

    @patch("project.mobboss_apps.web.views.get_container")
    def test_options_shows_moderator_controls_for_active_moderator(self, mock_get_container) -> None:
        mock_get_container.return_value = _StubContainerForOptions(moderator_user_id="u_mod")
        request = self.factory.get("/options/")
        request.user = self.moderator

        response = options(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Moderator Report Death")
        self.assertContains(response, "Transfer Funds")
        self.assertContains(response, "Transfer Item")

    @patch("project.mobboss_apps.web.views.get_container")
    def test_options_hides_moderator_controls_for_non_moderator_user(self, mock_get_container) -> None:
        mock_get_container.return_value = _StubContainerForOptions(moderator_user_id="u_mod")
        request = self.factory.get("/options/")
        request.user = self.player

        response = options(request)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Kill Game")

    @patch("project.mobboss_apps.web.views.get_container")
    def test_options_shows_return_to_lobby_for_ended_active_game(self, mock_get_container) -> None:
        mock_get_container.return_value = _StubContainerForOptions(
            moderator_user_id="u_mod",
            gameplay_status="ended",
        )
        request = self.factory.get("/options/")
        request.user = self.moderator
        request.session = {"active_game_id": "g-1"}

        response = options(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/"', html=False)
        self.assertContains(response, "Return to Lobby")
        self.assertNotContains(response, "Return to Game")

    @patch("project.mobboss_apps.web.views.messages.success")
    @patch("project.mobboss_apps.web.views.messages.error")
    @patch("project.mobboss_apps.web.views.get_container")
    def test_advance_accused_timeout_endpoint_calls_gameplay_port(
        self, mock_get_container, _mock_error, _mock_success
    ) -> None:
        container = _StubContainerForOptions(moderator_user_id="u_mod")
        mock_get_container.return_value = container
        request = self.factory.post("/options/advance-accused-timeout")
        request.user = self.moderator

        response = advance_accused_timeout(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/options/")
        self.assertEqual(len(container.gameplay_inbound_port.advanced_commands), 1)
        command = container.gameplay_inbound_port.advanced_commands[0]
        self.assertEqual(command.game_id, "g-1")
        self.assertEqual(command.requested_by_user_id, "u_mod")
        self.assertEqual(command.expected_version, 5)

    @patch("project.mobboss_apps.web.views.messages.success")
    @patch("project.mobboss_apps.web.views.messages.error")
    @patch("project.mobboss_apps.web.views.get_container")
    def test_moderator_report_death_endpoint_calls_gameplay_port(
        self, mock_get_container, _mock_error, _mock_success
    ) -> None:
        container = _StubContainerForOptions(moderator_user_id="u_mod")
        mock_get_container.return_value = container
        request = self.factory.post(
            "/options/moderator-report-death",
            {
                "murdered_user_id": "u_p1",
                "murderer_user_id": "u_p2",
                "attack_classification": "knife",
            },
        )
        request.user = self.moderator

        response = moderator_report_death(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/options/")
        self.assertEqual(len(container.gameplay_inbound_port.reported_deaths), 1)
        command = container.gameplay_inbound_port.reported_deaths[0]
        self.assertEqual(command.game_id, "g-1")
        self.assertEqual(command.murdered_user_id, "u_p1")
        self.assertEqual(command.murderer_user_id, "u_p2")
        self.assertEqual(command.attack_classification, "knife")
        self.assertEqual(command.reported_by_user_id, "u_mod")

    @patch("project.mobboss_apps.web.views.messages.success")
    @patch("project.mobboss_apps.web.views.messages.error")
    @patch("project.mobboss_apps.web.views.get_container")
    def test_moderator_add_funds_endpoint_calls_gameplay_port(
        self, mock_get_container, _mock_error, _mock_success
    ) -> None:
        container = _StubContainerForOptions(moderator_user_id="u_mod")
        mock_get_container.return_value = container
        request = self.factory.post(
            "/options/moderator-add-funds",
            {
                "recipient_user_id": "u_p2",
                "amount": "80",
            },
        )
        request.user = self.moderator

        response = moderator_add_funds(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/options/")
        self.assertEqual(len(container.gameplay_inbound_port.moderator_add_funds_commands), 1)
        command = container.gameplay_inbound_port.moderator_add_funds_commands[0]
        self.assertEqual(command.recipient_user_id, "u_p2")
        self.assertEqual(command.amount, 80)
        self.assertEqual(command.requested_by_user_id, "u_mod")

    @patch("project.mobboss_apps.web.views.messages.success")
    @patch("project.mobboss_apps.web.views.messages.error")
    @patch("project.mobboss_apps.web.views.get_container")
    def test_moderator_transfer_funds_endpoint_calls_gameplay_port(
        self, mock_get_container, _mock_error, _mock_success
    ) -> None:
        container = _StubContainerForOptions(moderator_user_id="u_mod")
        mock_get_container.return_value = container
        request = self.factory.post(
            "/options/moderator-transfer-funds",
            {
                "from_user_id": "u_p1",
                "to_user_id": "u_p2",
                "amount": "50",
            },
        )
        request.user = self.moderator

        response = moderator_transfer_funds(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/options/")
        self.assertEqual(len(container.gameplay_inbound_port.moderator_transfer_funds_commands), 1)
        command = container.gameplay_inbound_port.moderator_transfer_funds_commands[0]
        self.assertEqual(command.from_user_id, "u_p1")
        self.assertEqual(command.to_user_id, "u_p2")
        self.assertEqual(command.amount, 50)
        self.assertEqual(command.requested_by_user_id, "u_mod")

    @patch("project.mobboss_apps.web.views.messages.success")
    @patch("project.mobboss_apps.web.views.messages.error")
    @patch("project.mobboss_apps.web.views.get_container")
    def test_moderator_transfer_inventory_item_endpoint_calls_gameplay_port(
        self, mock_get_container, _mock_error, _mock_success
    ) -> None:
        container = _StubContainerForOptions(moderator_user_id="u_mod")
        mock_get_container.return_value = container
        request = self.factory.post(
            "/options/moderator-transfer-inventory-item",
            {
                "from_user_id": "u_p1",
                "to_user_id": "u_p2",
                "inventory_item_id": "inv-1",
            },
        )
        request.user = self.moderator

        response = moderator_transfer_inventory_item(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/options/")
        self.assertEqual(len(container.gameplay_inbound_port.moderator_transfer_inventory_item_commands), 1)
        command = container.gameplay_inbound_port.moderator_transfer_inventory_item_commands[0]
        self.assertEqual(command.from_user_id, "u_p1")
        self.assertEqual(command.to_user_id, "u_p2")
        self.assertEqual(command.inventory_item_id, "inv-1")
        self.assertEqual(command.requested_by_user_id, "u_mod")


class WebHowToPlayViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.moderator = type("StubUser", (), {"is_authenticated": True, "id": "u_mod", "username": "moderator"})()

    @patch("project.mobboss_apps.web.views.get_container")
    def test_how_to_play_shows_mobile_friendly_copy(self, mock_get_container) -> None:
        mock_get_container.return_value = _StubContainerForOptions(moderator_user_id="u_mod")
        request = self.factory.get("/how-to-play/")
        request.user = self.moderator
        request.session = {}

        response = how_to_play(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How to Play Mob Boss")
        self.assertContains(response, "A game of secrecy, strategy, money, and survival.")
        self.assertContains(response, "Mob players also share a secret word")
        self.assertContains(response, "Trust carefully.")

    @patch("project.mobboss_apps.web.views.get_container")
    def test_how_to_play_returns_to_active_game_when_game_is_in_progress(self, mock_get_container) -> None:
        mock_get_container.return_value = _StubContainerForOptions(moderator_user_id="u_mod")
        request = self.factory.get("/how-to-play/")
        request.user = self.moderator
        request.session = {"active_game_id": "g-1"}

        response = how_to_play(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/games/g-1/"', html=False)
        self.assertContains(response, "Return to Game")


if __name__ == "__main__":
    unittest.main()
