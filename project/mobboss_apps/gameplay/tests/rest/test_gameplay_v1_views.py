import sys
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.gameplay.ports.internal import (  # noqa: E402
    GameDetailsSnapshot,
    GiftOfferSnapshot,
    InventoryItemStateSnapshot,
    MoneyGiftOfferSnapshot,
    NotificationEventSnapshot,
    ParticipantStateSnapshot,
    SaleOfferSnapshot,
    TrialStateSnapshot,
)
from project.mobboss_apps.gameplay.v1_views import (  # noqa: E402
    AdvanceAccusedSelectionTimeoutView,
    BuyFromSupplyView,
    GiveMoneyView,
    GameDetailView,
    OfferGiftItemView,
    ReportDeathView,
    RespondGiftOfferView,
    RespondMoneyGiftOfferView,
    RespondSaleOfferView,
    SellInventoryItemView,
    SellInventoryToSupplyView,
    SetInventoryResalePriceView,
)
from project.mobboss_apps.mobboss.exceptions import ConflictProblem  # noqa: E402


def _game_snapshot() -> GameDetailsSnapshot:
    return GameDetailsSnapshot(
        game_id="g-1",
        room_id="r-1",
        moderator_user_id="u_mod",
        status="in_progress",
        phase="information",
        round_number=1,
        version=1,
        launched_at_epoch_seconds=100,
        ended_at_epoch_seconds=None,
        participants=[
            ParticipantStateSnapshot(
                user_id="u_p1",
                username="p1",
                faction="Police",
                role_name="Chief of Police",
                rank=1,
                life_state="alive",
                money_balance=300,
            ),
            ParticipantStateSnapshot(
                user_id="u_p2",
                username="p2",
                faction="Mob",
                role_name="Mob Boss",
                rank=1,
                life_state="alive",
                money_balance=300,
            ),
        ],
        catalog=[],
        pending_trial=None,
    )


class _StubGameplayInboundPort:
    def __init__(self, snapshot: GameDetailsSnapshot) -> None:
        self.snapshot = snapshot
        self.report_commands = []
        self.buy_commands = []
        self.resale_commands = []
        self.sell_commands = []
        self.sell_to_supply_commands = []
        self.sale_response_commands = []
        self.gift_offer_commands = []
        self.gift_response_commands = []
        self.give_money_commands = []
        self.respond_money_gift_offer_commands = []

    def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
        return self.snapshot

    def report_death(self, command) -> GameDetailsSnapshot:
        self.report_commands.append(command)
        self.snapshot = GameDetailsSnapshot(
            game_id=self.snapshot.game_id,
            room_id=self.snapshot.room_id,
            moderator_user_id=self.snapshot.moderator_user_id,
            status=self.snapshot.status,
            phase="accused_selection",
            round_number=self.snapshot.round_number,
            version=self.snapshot.version + 1,
            launched_at_epoch_seconds=self.snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=self.snapshot.ended_at_epoch_seconds,
            participants=[
                self.snapshot.participants[0],
                ParticipantStateSnapshot(
                    user_id="u_p2",
                    username="p2",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="dead",
                    money_balance=300,
                ),
            ],
            catalog=self.snapshot.catalog,
            pending_trial=TrialStateSnapshot(
                murdered_user_id=command.murdered_user_id,
                murderer_user_id=None,
                accused_user_id=None,
                accused_selection_cursor=["u_p1"],
                accused_selection_deadline_epoch_seconds=None,
                jury_user_ids=[],
                vote_deadline_epoch_seconds=None,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution=None,
            ),
        )
        return self.snapshot

    def advance_accused_selection_timeout(self, command) -> GameDetailsSnapshot:
        if command.requested_by_user_id != "u_mod":
            raise PermissionError("Only moderator can advance accused-selection timeout.")
        self.report_commands.append(command)
        self.snapshot = GameDetailsSnapshot(
            game_id=self.snapshot.game_id,
            room_id=self.snapshot.room_id,
            moderator_user_id=self.snapshot.moderator_user_id,
            status=self.snapshot.status,
            phase="boundary_resolution",
            round_number=self.snapshot.round_number,
            version=self.snapshot.version + 1,
            launched_at_epoch_seconds=self.snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=self.snapshot.ended_at_epoch_seconds,
            participants=self.snapshot.participants,
            catalog=self.snapshot.catalog,
            pending_trial=TrialStateSnapshot(
                murdered_user_id="u_p2",
                murderer_user_id=None,
                accused_user_id=None,
                accused_selection_cursor=[],
                accused_selection_deadline_epoch_seconds=None,
                jury_user_ids=[],
                vote_deadline_epoch_seconds=None,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution="no_conviction",
            ),
        )
        return self.snapshot

    def buy_from_supply(self, command) -> GameDetailsSnapshot:
        self.buy_commands.append(command)
        return self.snapshot

    def set_inventory_resale_price(self, command) -> GameDetailsSnapshot:
        self.resale_commands.append(command)
        return self.snapshot

    def sell_inventory_item(self, command) -> GameDetailsSnapshot:
        self.sell_commands.append(command)
        return self.snapshot

    def sell_inventory_to_supply(self, command) -> GameDetailsSnapshot:
        self.sell_to_supply_commands.append(command)
        return self.snapshot

    def respond_sale_offer(self, command) -> GameDetailsSnapshot:
        self.sale_response_commands.append(command)
        return self.snapshot

    def offer_gift_item(self, command) -> GameDetailsSnapshot:
        self.gift_offer_commands.append(command)
        return self.snapshot

    def respond_gift_offer(self, command) -> GameDetailsSnapshot:
        self.gift_response_commands.append(command)
        return self.snapshot

    def give_money(self, command) -> GameDetailsSnapshot:
        self.give_money_commands.append(command)
        return self.snapshot

    def respond_money_gift_offer(self, command) -> GameDetailsSnapshot:
        self.respond_money_gift_offer_commands.append(command)
        return self.snapshot


class _StubContainer:
    def __init__(self, gameplay_inbound_port: _StubGameplayInboundPort) -> None:
        self.gameplay_inbound_port = gameplay_inbound_port


class GameplayV1ViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.snapshot = _game_snapshot()
        self.gameplay = _StubGameplayInboundPort(self.snapshot)
        self.container = _StubContainer(self.gameplay)
        self.moderator = type("U", (), {"is_authenticated": True, "id": "u_mod", "username": "moderator"})()
        self.player = type("U", (), {"is_authenticated": True, "id": "u_p1", "username": "p1"})()

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_game_detail_moderator_sees_full_participant_roles(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.get("/gameplay/v1/games/g-1")
        request.user = self.moderator

        response = GameDetailView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        self.assertEqual(payload["game_id"], "g-1")
        self.assertEqual(payload["participants"][0]["faction"], "Police")
        self.assertEqual(payload["participants"][1]["role_name"], "Mob Boss")
        self.assertEqual(payload["participants"][0]["money_balance"], 300)
        self.assertIn("inventory", payload["participants"][0])
        self.assertIn("is_juror", payload["participants"][0])
        self.assertIsNone(payload["current_police_leader_user_id"])
        self.assertIsNone(payload["current_mob_leader_user_id"])
        self.assertEqual(payload["police_mob_kills_count"], 0)
        self.assertEqual(payload["police_mob_kills_allowed"], 0)
        self.assertFalse(payload["police_brutality_exceeded"])

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_game_detail_player_sees_only_self_role_details(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.get("/gameplay/v1/games/g-1")
        request.user = self.player

        response = GameDetailView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        first = next(participant for participant in payload["participants"] if participant["user_id"] == "u_p1")
        second = next(participant for participant in payload["participants"] if participant["user_id"] == "u_p2")
        self.assertEqual(first["faction"], "Police")
        self.assertEqual(first["money_balance"], 300)
        self.assertNotIn("faction", second)
        self.assertNotIn("role_name", second)
        self.assertNotIn("money_balance", second)
        self.assertIsNone(payload["police_mob_kills_count"])
        self.assertIsNone(payload["police_mob_kills_allowed"])
        self.assertIsNone(payload["police_brutality_exceeded"])
        self.assertFalse(payload["can_submit_accused_selection"])
        self.assertFalse(payload["can_submit_jury_vote"])
        self.assertFalse(payload["can_submit_tamper_vote"])

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_game_detail_includes_offer_usernames(self, mock_get_container) -> None:
        self.gameplay.snapshot = GameDetailsSnapshot(
            game_id="g-1",
            room_id="r-1",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=1,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_p1",
                    username="p1",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_p2",
                    username="p2",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=[],
            pending_trial=None,
            pending_gift_offers=[
                GiftOfferSnapshot(
                    gift_offer_id="gift-1",
                    giver_user_id="u_p2",
                    receiver_user_id="u_p1",
                    inventory_item_id="inv-1",
                    item_display_name="Knife",
                    created_at_epoch_seconds=200,
                )
            ],
            pending_money_gift_offers=[
                MoneyGiftOfferSnapshot(
                    money_gift_offer_id="money-1",
                    giver_user_id="u_p2",
                    receiver_user_id="u_p1",
                    amount=40,
                    created_at_epoch_seconds=201,
                )
            ],
            pending_sale_offers=[
                SaleOfferSnapshot(
                    sale_offer_id="sale-1",
                    seller_user_id="u_p2",
                    buyer_user_id="u_p1",
                    inventory_item_id="inv-2",
                    item_display_name="Vest",
                    sale_price=80,
                    created_at_epoch_seconds=202,
                )
            ],
        )
        mock_get_container.return_value = self.container
        request = self.factory.get("/gameplay/v1/games/g-1")
        request.user = self.player

        response = GameDetailView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        self.assertEqual(payload["pending_gift_offers"][0]["giver_username"], "p2")
        self.assertEqual(payload["pending_gift_offers"][0]["receiver_username"], "p1")
        self.assertEqual(payload["pending_money_gift_offers"][0]["giver_username"], "p2")
        self.assertEqual(payload["pending_sale_offers"][0]["seller_username"], "p2")
        self.assertEqual(payload["pending_sale_offers"][0]["buyer_username"], "p1")

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_game_detail_normalizes_legacy_inventory_default_image_paths(self, mock_get_container) -> None:
        self.snapshot = GameDetailsSnapshot(
            game_id=self.snapshot.game_id,
            room_id=self.snapshot.room_id,
            moderator_user_id=self.snapshot.moderator_user_id,
            status=self.snapshot.status,
            phase=self.snapshot.phase,
            round_number=self.snapshot.round_number,
            version=self.snapshot.version,
            launched_at_epoch_seconds=self.snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=self.snapshot.ended_at_epoch_seconds,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_p1",
                    username="p1",
                    faction="Merchant",
                    role_name="Arms Dealer",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                    inventory=[
                        InventoryItemStateSnapshot(
                            item_id="inv-1",
                            classification="gun_tier_1",
                            display_name="Handgun (Tier 1)",
                            image_path="/static/items/defaults/default_gun_tier_1.svg",
                            acquisition_value=150,
                            resale_price=150,
                        )
                    ],
                ),
                self.snapshot.participants[1],
            ],
            catalog=self.snapshot.catalog,
            pending_trial=self.snapshot.pending_trial,
        )
        self.gameplay.snapshot = self.snapshot
        mock_get_container.return_value = self.container
        request = self.factory.get("/gameplay/v1/games/g-1")
        request.user = self.player

        response = GameDetailView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        self.assertEqual(
            payload["participants"][0]["inventory"][0]["image_path"],
            "/static/items/defaults/default_gun_tier_1.jpg",
        )

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_game_detail_player_payload_includes_accused_selection_eligibility(self, mock_get_container) -> None:
        self.snapshot = GameDetailsSnapshot(
            game_id=self.snapshot.game_id,
            room_id=self.snapshot.room_id,
            moderator_user_id=self.snapshot.moderator_user_id,
            status="in_progress",
            phase="accused_selection",
            round_number=self.snapshot.round_number,
            version=self.snapshot.version + 1,
            launched_at_epoch_seconds=self.snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=self.snapshot.ended_at_epoch_seconds,
            participants=self.snapshot.participants,
            catalog=self.snapshot.catalog,
            pending_trial=TrialStateSnapshot(
                murdered_user_id="u_p2",
                murderer_user_id="u_x",
                accused_user_id=None,
                accused_selection_cursor=["u_p1"],
                accused_selection_deadline_epoch_seconds=None,
                jury_user_ids=[],
                vote_deadline_epoch_seconds=None,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution=None,
            ),
            notification_feed=[
                NotificationEventSnapshot(
                    event_id="event-acting-chief",
                    user_id="u_p1",
                    message="You are now the Acting Chief of Police.",
                    created_at_epoch_seconds=100,
                ),
                NotificationEventSnapshot(
                    event_id="event-murder",
                    user_id="u_p1",
                    message="A murder was reported. Report to the court house immediately.",
                    created_at_epoch_seconds=101,
                ),
            ],
        )
        self.gameplay.snapshot = self.snapshot
        mock_get_container.return_value = self.container
        request = self.factory.get("/gameplay/v1/games/g-1")
        request.user = self.player

        response = GameDetailView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        self.assertTrue(payload["can_submit_accused_selection"])
        self.assertFalse(payload["can_submit_jury_vote"])
        self.assertFalse(payload["can_submit_tamper_vote"])

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_game_detail_player_payload_allows_silenced_juror_to_vote(self, mock_get_container) -> None:
        self.snapshot = GameDetailsSnapshot(
            game_id=self.snapshot.game_id,
            room_id=self.snapshot.room_id,
            moderator_user_id=self.snapshot.moderator_user_id,
            status="in_progress",
            phase="trial_voting",
            round_number=self.snapshot.round_number,
            version=self.snapshot.version + 1,
            launched_at_epoch_seconds=self.snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=self.snapshot.ended_at_epoch_seconds,
            participants=self.snapshot.participants,
            catalog=self.snapshot.catalog,
            pending_trial=TrialStateSnapshot(
                murdered_user_id="u_p2",
                murderer_user_id="u_x",
                accused_user_id="u_p2",
                accused_selection_cursor=[],
                accused_selection_deadline_epoch_seconds=None,
                jury_user_ids=["u_p1"],
                vote_deadline_epoch_seconds=1234,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution=None,
                silenced_user_ids=["u_p1"],
            ),
        )
        self.gameplay.snapshot = self.snapshot
        mock_get_container.return_value = self.container
        request = self.factory.get("/gameplay/v1/games/g-1")
        request.user = self.player

        response = GameDetailView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        self.assertTrue(payload["can_submit_jury_vote"])

    @patch("project.mobboss_apps.gameplay.v1_views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_game_detail_filters_expired_viewer_notifications(self, mock_get_container, _mock_time) -> None:
        self.snapshot = GameDetailsSnapshot(
            game_id=self.snapshot.game_id,
            room_id=self.snapshot.room_id,
            moderator_user_id=self.snapshot.moderator_user_id,
            status=self.snapshot.status,
            phase=self.snapshot.phase,
            round_number=self.snapshot.round_number,
            version=self.snapshot.version,
            launched_at_epoch_seconds=self.snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=self.snapshot.ended_at_epoch_seconds,
            participants=self.snapshot.participants,
            catalog=self.snapshot.catalog,
            pending_trial=self.snapshot.pending_trial,
            notification_feed=[
                NotificationEventSnapshot(
                    event_id="event-old",
                    user_id="u_p1",
                    message="Old",
                    created_at_epoch_seconds=879,
                ),
                NotificationEventSnapshot(
                    event_id="event-recent",
                    user_id="u_p1",
                    message="Recent",
                    created_at_epoch_seconds=900,
                ),
                NotificationEventSnapshot(
                    event_id="event-other-user",
                    user_id="u_p2",
                    message="Other",
                    created_at_epoch_seconds=995,
                ),
            ],
        )
        self.gameplay.snapshot = self.snapshot
        mock_get_container.return_value = self.container
        request = self.factory.get("/gameplay/v1/games/g-1")
        request.user = self.player

        response = GameDetailView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        self.assertEqual(
            [event["event_id"] for event in payload["viewer_notifications"]],
            ["event-recent"],
        )

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_game_detail_player_sees_all_roles_after_game_has_ended(self, mock_get_container) -> None:
        self.snapshot = GameDetailsSnapshot(
            game_id="g-1",
            room_id="r-1",
            moderator_user_id="u_mod",
            status="ended",
            phase="ended",
            round_number=1,
            version=2,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=150,
            participants=self.snapshot.participants,
            catalog=[],
            pending_trial=None,
            winning_faction="Police",
        )
        self.gameplay.snapshot = self.snapshot
        mock_get_container.return_value = self.container
        request = self.factory.get("/gameplay/v1/games/g-1")
        request.user = self.player

        response = GameDetailView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        first = next(participant for participant in payload["participants"] if participant["user_id"] == "u_p1")
        second = next(participant for participant in payload["participants"] if participant["user_id"] == "u_p2")
        self.assertEqual(first["faction"], "Police")
        self.assertEqual(second["faction"], "Mob")
        self.assertEqual(second["role_name"], "Mob Boss")
        self.assertEqual(second["money_balance"], 300)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_game_detail_moderator_sees_juror_and_attribution_fields(self, mock_get_container) -> None:
        self.snapshot = GameDetailsSnapshot(
            game_id=self.snapshot.game_id,
            room_id=self.snapshot.room_id,
            moderator_user_id=self.snapshot.moderator_user_id,
            status=self.snapshot.status,
            phase="trial_voting",
            round_number=self.snapshot.round_number,
            version=self.snapshot.version,
            launched_at_epoch_seconds=self.snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=self.snapshot.ended_at_epoch_seconds,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_p1",
                    username="p1",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_p2",
                    username="p2",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="dead",
                    money_balance=0,
                    murdered_by_user_id="u_p1",
                ),
            ],
            catalog=self.snapshot.catalog,
            pending_trial=TrialStateSnapshot(
                murdered_user_id="u_p2",
                murderer_user_id="u_p1",
                accused_user_id="u_p2",
                accused_selection_cursor=[],
                accused_selection_deadline_epoch_seconds=None,
                jury_user_ids=["u_p1"],
                vote_deadline_epoch_seconds=1234,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution=None,
            ),
        )
        self.gameplay.snapshot = self.snapshot
        mock_get_container.return_value = self.container
        request = self.factory.get("/gameplay/v1/games/g-1")
        request.user = self.moderator

        response = GameDetailView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        police = next(participant for participant in payload["participants"] if participant["user_id"] == "u_p1")
        mob = next(participant for participant in payload["participants"] if participant["user_id"] == "u_p2")
        self.assertTrue(police["is_juror"])
        self.assertEqual(mob["murdered_by_username"], "p1")

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_report_death_requires_moderator(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/report-death",
            data='{"murdered_user_id":"u_p2","attack_classification":"knife","expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = ReportDeathView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self.gameplay.report_commands), 0)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_report_death_allows_self_report_with_selected_murderer(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/report-death",
            data='{"murdered_user_id":"u_p1","murderer_user_id":"u_p2","attack_classification":"gun_tier_1","expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = ReportDeathView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.gameplay.report_commands), 1)
        self.assertEqual(self.gameplay.report_commands[0].reported_by_user_id, "u_p1")
        self.assertEqual(self.gameplay.report_commands[0].murderer_user_id, "u_p2")
        self.assertEqual(self.gameplay.report_commands[0].attack_classification, "gun_tier_1")

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_report_death_updates_game_when_requested_by_moderator(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/report-death",
            data='{"murdered_user_id":"u_p2","attack_classification":"knife","expected_version":1}',
            content_type="application/json",
        )
        request.user = self.moderator

        response = ReportDeathView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        self.assertEqual(payload["phase"], "accused_selection")
        self.assertEqual(payload["version"], 2)
        self.assertEqual(len(self.gameplay.report_commands), 1)
        self.assertEqual(self.gameplay.report_commands[0].expected_version, 1)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_report_death_requires_expected_version(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/report-death",
            data='{"murdered_user_id":"u_p2"}',
            content_type="application/json",
        )
        request.user = self.moderator

        response = ReportDeathView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.gameplay.report_commands), 0)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_advance_accused_timeout_requires_expected_version(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/advance-accused-selection-timeout",
            data="{}",
            content_type="application/json",
        )
        request.user = self.moderator

        response = AdvanceAccusedSelectionTimeoutView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 422)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_advance_accused_timeout_updates_state_for_moderator(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/advance-accused-selection-timeout",
            data='{"expected_version":1}',
            content_type="application/json",
        )
        request.user = self.moderator

        response = AdvanceAccusedSelectionTimeoutView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        self.assertEqual(payload["phase"], "boundary_resolution")
        self.assertEqual(payload["version"], 2)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_advance_accused_timeout_forbidden_for_non_moderator(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/advance-accused-selection-timeout",
            data='{"expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = AdvanceAccusedSelectionTimeoutView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 403)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_report_death_returns_409_when_service_detects_version_conflict(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/report-death",
            data='{"murdered_user_id":"u_p2","attack_classification":"knife","expected_version":1}',
            content_type="application/json",
        )
        request.user = self.moderator

        with patch.object(
            self.gameplay,
            "report_death",
            side_effect=ConflictProblem(
                "stale version",
                code="version_conflict",
                extensions={"expected_version": 1, "current_version": 2},
            ),
        ):
            response = ReportDeathView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(payload["code"], "version_conflict")
        self.assertEqual(payload["expected_version"], 1)
        self.assertEqual(payload["current_version"], 2)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_advance_timeout_returns_409_when_service_detects_version_conflict(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/advance-accused-selection-timeout",
            data='{"expected_version":1}',
            content_type="application/json",
        )
        request.user = self.moderator

        with patch.object(
            self.gameplay,
            "advance_accused_selection_timeout",
            side_effect=ConflictProblem(
                "stale version",
                code="version_conflict",
                extensions={"expected_version": 3, "current_version": 4},
            ),
        ):
            response = AdvanceAccusedSelectionTimeoutView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(payload["code"], "version_conflict")
        self.assertEqual(payload["expected_version"], 3)
        self.assertEqual(payload["current_version"], 4)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_buy_from_supply_uses_authenticated_user(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/buy-from-supply",
            data='{"classification":"knife","expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = BuyFromSupplyView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.gameplay.buy_commands), 1)
        self.assertEqual(self.gameplay.buy_commands[0].buyer_user_id, "u_p1")
        self.assertEqual(self.gameplay.buy_commands[0].classification, "knife")

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_set_inventory_resale_price_uses_authenticated_user(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/set-inventory-resale-price",
            data='{"inventory_item_id":"inv-1","resale_price":220,"expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = SetInventoryResalePriceView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.gameplay.resale_commands), 1)
        self.assertEqual(self.gameplay.resale_commands[0].seller_user_id, "u_p1")
        self.assertEqual(self.gameplay.resale_commands[0].inventory_item_id, "inv-1")
        self.assertEqual(self.gameplay.resale_commands[0].resale_price, 220)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_sell_inventory_item_uses_authenticated_user(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/sell-inventory-item",
            data='{"buyer_user_id":"u_p2","inventory_item_id":"inv-1","expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = SellInventoryItemView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.gameplay.sell_commands), 1)
        self.assertEqual(self.gameplay.sell_commands[0].seller_user_id, "u_p1")
        self.assertEqual(self.gameplay.sell_commands[0].buyer_user_id, "u_p2")
        self.assertEqual(self.gameplay.sell_commands[0].inventory_item_id, "inv-1")

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_sell_inventory_to_supply_uses_authenticated_user(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/sell-inventory-to-supply",
            data='{"inventory_item_id":"inv-1","expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = SellInventoryToSupplyView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.gameplay.sell_to_supply_commands), 1)
        self.assertEqual(self.gameplay.sell_to_supply_commands[0].seller_user_id, "u_p1")
        self.assertEqual(self.gameplay.sell_to_supply_commands[0].inventory_item_id, "inv-1")

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_offer_gift_item_uses_authenticated_user(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/offer-gift-item",
            data='{"receiver_user_id":"u_p2","inventory_item_id":"inv-1","expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = OfferGiftItemView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.gameplay.gift_offer_commands), 1)
        self.assertEqual(self.gameplay.gift_offer_commands[0].giver_user_id, "u_p1")
        self.assertEqual(self.gameplay.gift_offer_commands[0].receiver_user_id, "u_p2")
        self.assertEqual(self.gameplay.gift_offer_commands[0].inventory_item_id, "inv-1")

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_give_money_uses_authenticated_user(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/give-money",
            data='{"receiver_user_id":"u_p2","amount":40,"expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = GiveMoneyView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.gameplay.give_money_commands), 1)
        self.assertEqual(self.gameplay.give_money_commands[0].giver_user_id, "u_p1")
        self.assertEqual(self.gameplay.give_money_commands[0].receiver_user_id, "u_p2")
        self.assertEqual(self.gameplay.give_money_commands[0].amount, 40)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_respond_money_gift_offer_uses_authenticated_user(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/respond-money-gift-offer",
            data='{"money_gift_offer_id":"money-gift-1","accept":true,"expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = RespondMoneyGiftOfferView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.gameplay.respond_money_gift_offer_commands), 1)
        self.assertEqual(self.gameplay.respond_money_gift_offer_commands[0].receiver_user_id, "u_p1")
        self.assertEqual(self.gameplay.respond_money_gift_offer_commands[0].money_gift_offer_id, "money-gift-1")
        self.assertTrue(self.gameplay.respond_money_gift_offer_commands[0].accept)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_respond_sale_offer_uses_authenticated_user(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/respond-sale-offer",
            data='{"sale_offer_id":"sale-1","accept":true,"expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = RespondSaleOfferView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.gameplay.sale_response_commands), 1)
        self.assertEqual(self.gameplay.sale_response_commands[0].buyer_user_id, "u_p1")
        self.assertEqual(self.gameplay.sale_response_commands[0].sale_offer_id, "sale-1")
        self.assertTrue(self.gameplay.sale_response_commands[0].accept)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_respond_gift_offer_uses_authenticated_user(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/respond-gift-offer",
            data='{"gift_offer_id":"gift-1","accept":true,"expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = RespondGiftOfferView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.gameplay.gift_response_commands), 1)
        self.assertEqual(self.gameplay.gift_response_commands[0].receiver_user_id, "u_p1")
        self.assertEqual(self.gameplay.gift_response_commands[0].gift_offer_id, "gift-1")
        self.assertTrue(self.gameplay.gift_response_commands[0].accept)


if __name__ == "__main__":
    unittest.main()
