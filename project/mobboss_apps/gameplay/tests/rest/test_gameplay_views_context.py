import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.gameplay.ports.internal import (  # noqa: E402
    CatalogItemStateSnapshot,
    GameDetailsSnapshot,
    InventoryItemStateSnapshot,
    NotificationEventSnapshot,
    ParticipantPowerStateSnapshot,
    ParticipantStateSnapshot,
    PlayerTransactionSnapshot,
    TrialStateSnapshot,
)
from project.mobboss_apps.gameplay.views import activate_deputy_protective_custody, detail, exit_game  # noqa: E402
from project.mobboss_apps.rooms.ports.internal import RoomDetailsSnapshot  # noqa: E402


def _snapshot() -> GameDetailsSnapshot:
    return GameDetailsSnapshot(
        game_id="g-ctx",
        room_id="r-ctx",
        moderator_user_id="u_mod",
        status="in_progress",
        phase="information",
        round_number=1,
        version=1,
        launched_at_epoch_seconds=100,
        ended_at_epoch_seconds=None,
        participants=[
            ParticipantStateSnapshot(
                user_id="u_police",
                username="police",
                faction="Police",
                role_name="Chief of Police",
                rank=1,
                life_state="alive",
                money_balance=300,
            ),
            ParticipantStateSnapshot(
                user_id="u_mob",
                username="mob",
                faction="Mob",
                role_name="Mob Boss",
                rank=1,
                life_state="alive",
                money_balance=300,
            ),
        ],
        catalog=[
            CatalogItemStateSnapshot(
                classification="knife",
                display_name="Knife",
                base_price=100,
                image_path="/static/items/defaults/default_knife.svg",
                is_active=True,
            )
        ],
        pending_trial=None,
    )


class _StubGameplayInboundPort:
    def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
        return _snapshot()


class _StubContainer:
    def __init__(self) -> None:
        self.gameplay_inbound_port = _StubGameplayInboundPort()
        self.rooms_inbound_port = None
        self.room_state_poll_interval_seconds = 5
        self.room_dev_mode = False


class GameplayHtmlContextTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.container = _StubContainer()
        self.player = type("U", (), {"is_authenticated": True, "id": "u_police", "username": "police"})()
        self.moderator = type("U", (), {"is_authenticated": True, "id": "u_mod", "username": "moderator"})()

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_player_context_uses_sanitized_page_dto(self, mock_render, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-ctx")
        request.user = self.player

        response = detail(request, game_id="g-ctx")

        self.assertEqual(response.status_code, 200)
        self.assertIn("page", captured_context)
        self.assertNotIn("game", captured_context)
        page = captured_context["page"]
        self.assertFalse(page.is_moderator)
        self.assertIsNone(page.pending_trial)
        self.assertTrue(captured_context["show_player_wallet"])
        self.assertEqual(captured_context["player_money_balance"], 300)
        self.assertEqual(captured_context["player_inventory_items"], [])
        own_row = next(row for row in page.participant_rows if row.user_id == "u_police")
        other_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        self.assertEqual(own_row.role_label, "Faction: Police / Role: Chief of Police")
        self.assertEqual(other_row.role_label, "Hidden")
        self.assertTrue(captured_context["superpower_panel"]["show"])
        self.assertEqual(captured_context["superpower_panel"]["role_name"], "Chief of Police")

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_player_context_filters_expired_notifications(self, mock_render, mock_get_container, _mock_time) -> None:
        snapshot = replace(
            _snapshot(),
            notification_feed=[
                NotificationEventSnapshot(
                    event_id="event-old",
                    user_id="u_police",
                    message="Old",
                    created_at_epoch_seconds=879,
                ),
                NotificationEventSnapshot(
                    event_id="event-recent",
                    user_id="u_police",
                    message="Recent",
                    created_at_epoch_seconds=900,
                ),
                NotificationEventSnapshot(
                    event_id="event-other-user",
                    user_id="u_mob",
                    message="Other",
                    created_at_epoch_seconds=995,
                ),
            ],
        )

        class _NotificationStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return snapshot

        class _NotificationStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _NotificationStubGameplayInboundPort()
                self.rooms_inbound_port = None
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _NotificationStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-ctx")
        request.user = self.player

        response = detail(request, game_id="g-ctx")

        self.assertEqual(response.status_code, 200)
        viewer_notifications = captured_context["viewer_notifications"]
        self.assertEqual([event.event_id for event in viewer_notifications], ["event-recent"])

    @patch("project.mobboss_apps.gameplay.views.get_container")
    def test_exit_game_deletes_ended_room_for_moderator_and_clears_session(self, mock_get_container) -> None:
        ended_snapshot = GameDetailsSnapshot(
            game_id="g-ended",
            room_id="r-ended",
            moderator_user_id="u_mod",
            status="ended",
            phase="ended",
            round_number=3,
            version=9,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=200,
            participants=[],
            catalog=[],
            pending_trial=None,
        )

        class _ExitStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return ended_snapshot

        class _ExitStubRoomsInboundPort:
            def __init__(self) -> None:
                self.deleted: list[tuple[str, str]] = []

            def delete_room(self, command) -> None:
                self.deleted.append((command.room_id, command.requested_by_user_id))

        class _ExitStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _ExitStubGameplayInboundPort()
                self.rooms_inbound_port = _ExitStubRoomsInboundPort()

        container = _ExitStubContainer()
        mock_get_container.return_value = container
        request = self.factory.post("/games/g-ended/exit")
        request.user = self.moderator
        request.session = {"active_game_id": "g-ended", "active_room_id": "r-ended"}

        response = exit_game(request, game_id="g-ended")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")
        self.assertEqual(container.rooms_inbound_port.deleted, [("r-ended", "u_mod")])
        self.assertNotIn("active_game_id", request.session)
        self.assertNotIn("active_room_id", request.session)

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_moderator_context_exposes_moderator_page_dto(self, mock_render, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-ctx")
        request.user = self.moderator

        response = detail(request, game_id="g-ctx")

        self.assertEqual(response.status_code, 200)
        page = captured_context["page"]
        self.assertTrue(page.is_moderator)
        mob_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        self.assertEqual(mob_row.role_label, "Faction: Mob / Role: Mob Boss")
        self.assertEqual(captured_context["police_mob_kills_count"], 0)
        self.assertEqual(captured_context["police_mob_kills_allowed"], 0)
        self.assertFalse(captured_context["police_brutality_exceeded"])

    @patch("project.mobboss_apps.gameplay.views.messages.error")
    @patch("project.mobboss_apps.gameplay.views.messages.success")
    @patch("project.mobboss_apps.gameplay.views.get_container")
    def test_deputy_activation_uses_view_as_actor_in_dev_mode(self, mock_get_container, _mock_success, _mock_error) -> None:
        snapshot = GameDetailsSnapshot(
            game_id="g-deputy-action",
            room_id="r-deputy-action",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=3,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_deputy",
                    username="deputy",
                    faction="Police",
                    role_name="Deputy",
                    rank=2,
                    life_state="alive",
                    money_balance=200,
                ),
                ParticipantStateSnapshot(
                    user_id="u_target",
                    username="target",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=200,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _DeputyActionStubGameplayInboundPort:
            def __init__(self, active_snapshot: GameDetailsSnapshot) -> None:
                self._snapshot = active_snapshot
                self.command = None

            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return self._snapshot

            def activate_deputy_protective_custody(self, command):
                self.command = command
                return self._snapshot

        class _DeputyActionStubContainer:
            def __init__(self, gameplay_inbound_port) -> None:
                self.gameplay_inbound_port = gameplay_inbound_port
                self.room_dev_mode = True

        gameplay_inbound = _DeputyActionStubGameplayInboundPort(snapshot)
        mock_get_container.return_value = _DeputyActionStubContainer(gameplay_inbound)
        request = self.factory.post(
            "/games/g-deputy-action/activate-deputy-protective-custody",
            data={
                "as_user_id": "u_deputy",
                "target_user_id": "u_target",
                "expected_version": "3",
            },
        )
        request.user = self.moderator

        response = activate_deputy_protective_custody(request, game_id="g-deputy-action")

        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(gameplay_inbound.command)
        self.assertEqual(gameplay_inbound.command.actor_user_id, "u_deputy")
        self.assertEqual(gameplay_inbound.command.target_user_id, "u_target")

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_dead_player_context_uses_ghost_view_projection(self, mock_render, mock_get_container) -> None:
        ghost_snapshot = GameDetailsSnapshot(
            game_id="g-ghost",
            room_id="r-ghost",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="accused_selection",
            round_number=2,
            version=4,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_dead",
                    username="deadplayer",
                    faction="Police",
                    role_name="Cop",
                    rank=2,
                    life_state="dead",
                    money_balance=180,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob",
                    username="mob",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    life_state="alive",
                    money_balance=500,
                    power_state=ParticipantPowerStateSnapshot(
                        merchant_wholesale_order_used=False,
                    ),
                ),
            ],
            catalog=[
                CatalogItemStateSnapshot(
                    classification="gun_tier_1",
                    display_name="Handgun (Tier 1)",
                    base_price=150,
                    image_path="/static/items/defaults/default_gun_tier_1.svg",
                    is_active=True,
                )
            ],
            pending_trial=TrialStateSnapshot(
                murdered_user_id="u_dead",
                murderer_user_id="u_mob",
                accused_user_id=None,
                accused_selection_cursor=["u_mob"],
                accused_selection_deadline_epoch_seconds=1111,
                jury_user_ids=[],
                vote_deadline_epoch_seconds=None,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution=None,
            ),
            latest_jury_log_user_ids=["u_mob", "u_merchant"],
            total_mob_participants_at_start=1,
            police_mob_kills_count=0,
        )

        class _GhostStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return ghost_snapshot

        class _GhostStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _GhostStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _GhostStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-ghost")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_dead", "username": "deadplayer"})()

        response = detail(request, game_id="g-ghost")

        self.assertEqual(response.status_code, 200)
        page = captured_context["page"]
        self.assertFalse(page.is_moderator)
        self.assertTrue(page.is_ghost_view)
        self.assertIsNotNone(page.pending_trial)
        self.assertEqual(page.pending_trial.murdered_user_id, "u_dead")
        self.assertFalse(captured_context["show_player_wallet"])
        self.assertTrue(captured_context["ghost_view_enabled"])
        mob_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        merchant_row = next(row for row in page.participant_rows if row.user_id == "u_merchant")
        self.assertEqual(mob_row.role_label, "Faction: Mob / Role: Mob Boss")
        self.assertEqual(merchant_row.role_label, "Role: Merchant")
        self.assertEqual(captured_context["moderator_latest_jury_usernames"], [])

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_chief_of_police_context_includes_accused_selection_card(self, mock_render, mock_get_container) -> None:
        accused_snapshot = GameDetailsSnapshot(
            game_id="g-chief",
            room_id="r-chief",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="accused_selection",
            round_number=2,
            version=4,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_chief",
                    username="chief",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=200,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob",
                    username="mob",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=[],
            pending_trial=TrialStateSnapshot(
                murdered_user_id="u_dead",
                murderer_user_id="u_mob",
                accused_user_id=None,
                accused_selection_cursor=["u_chief"],
                accused_selection_deadline_epoch_seconds=1111,
                jury_user_ids=[],
                vote_deadline_epoch_seconds=None,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution=None,
            ),
        )

        class _ChiefStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return accused_snapshot

        class _ChiefStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _ChiefStubGameplayInboundPort()
                self.rooms_inbound_port = None
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _ChiefStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-chief")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_chief", "username": "chief"})()

        response = detail(request, game_id="g-chief")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_context["can_view_accused_selection"])
        self.assertTrue(captured_context["can_submit_accused_selection"])

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_jailed_felon_stays_out_of_ghost_view_until_escape_or_game_end(self, mock_render, mock_get_container, _mock_time) -> None:
        felon_snapshot = GameDetailsSnapshot(
            game_id="g-felon-view",
            room_id="r-felon-view",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=3,
            version=8,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_felon",
                    username="felon",
                    faction="Mob",
                    role_name="Felon",
                    rank=5,
                    life_state="jailed",
                    money_balance=100,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob",
                    username="mobboss",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police",
                    username="police",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=[],
            pending_trial=None,
            felon_escape_user_id="u_felon",
            felon_escape_expires_at_epoch_seconds=2800,
        )

        class _FelonStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return felon_snapshot

        class _FelonStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _FelonStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _FelonStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-felon-view")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_felon", "username": "felon"})()

        response = detail(request, game_id="g-felon-view")

        self.assertEqual(response.status_code, 200)
        page = captured_context["page"]
        self.assertFalse(page.is_ghost_view)
        self.assertTrue(captured_context["felon_escape_panel"]["show"])
        self.assertTrue(captured_context["felon_escape_panel"]["viewer_is_target"])
        other_row = next(row for row in page.participant_rows if row.user_id == "u_mob")
        self.assertEqual(other_row.role_label, "Hidden")

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_trial_result_notice_when_verdict_is_available(self, mock_render, mock_get_container) -> None:
        trial_snapshot = _snapshot()
        trial_snapshot = GameDetailsSnapshot(
            game_id=trial_snapshot.game_id,
            room_id=trial_snapshot.room_id,
            moderator_user_id=trial_snapshot.moderator_user_id,
            status=trial_snapshot.status,
            phase="boundary_resolution",
            round_number=trial_snapshot.round_number,
            version=trial_snapshot.version,
            launched_at_epoch_seconds=trial_snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=trial_snapshot.ended_at_epoch_seconds,
            participants=[
                trial_snapshot.participants[0],
                ParticipantStateSnapshot(
                    user_id="u_mob",
                    username="mob",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="jailed",
                    money_balance=300,
                ),
            ],
            catalog=trial_snapshot.catalog,
            pending_trial=TrialStateSnapshot(
                murdered_user_id="u_police",
                murderer_user_id=None,
                accused_user_id="u_mob",
                accused_selection_cursor=[],
                accused_selection_deadline_epoch_seconds=None,
                jury_user_ids=["u_police"],
                vote_deadline_epoch_seconds=1000,
                votes=[{"user_id": "u_police", "vote": "guilty"}],
                verdict="guilty",
                conviction_correct=True,
                resolution="vote_complete",
            ),
            latest_public_notice="mob was found guilty. They are now in jail.",
        )

        class _TrialStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return trial_snapshot

        class _TrialStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _TrialStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _TrialStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-ctx")
        request.user = self.player

        response = detail(request, game_id="g-ctx")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["trial_result_notice"], "mob was found guilty. They are now in jail.")

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_cop_superpower_status_when_active(self, mock_render, mock_get_container) -> None:
        cop_snapshot = GameDetailsSnapshot(
            game_id="g-cop",
            room_id="r-cop",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=2,
            version=7,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_cop",
                    username="cop",
                    faction="Police",
                    role_name="Cop",
                    rank=9,
                    life_state="alive",
                    money_balance=300,
                    inventory=[],
                    power_state=ParticipantPowerStateSnapshot(
                        cop_last_three_protection_used=True,
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob",
                    username="mob",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="dead",
                    money_balance=0,
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=[
                CatalogItemStateSnapshot(
                    classification="bulletproof_vest",
                    display_name="Bulletproof Vest",
                    base_price=50,
                    image_path="/static/items/defaults/default_bulletproof_vest.svg",
                    is_active=True,
                )
            ],
            pending_trial=None,
        )
        cop_snapshot = replace(
            cop_snapshot,
            participants=[
                replace(
                    cop_snapshot.participants[0],
                    inventory=[
                        InventoryItemStateSnapshot(
                            item_id="inv-vest",
                            classification="bulletproof_vest",
                            display_name="Bulletproof Vest",
                            image_path="/static/items/defaults/default_bulletproof_vest.svg",
                            acquisition_value=50,
                            resale_price=50,
                        )
                    ],
                ),
                cop_snapshot.participants[1],
                cop_snapshot.participants[2],
            ],
        )

        class _CopStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return cop_snapshot

        class _CopStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _CopStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _CopStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-cop")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_cop", "username": "cop"})()

        response = detail(request, game_id="g-cop")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["role_name"], "Cop")
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "Last 3 Protection")
        self.assertEqual(captured_context["superpower_panel"]["status_text"], "Status: Active")

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_gates_jury_vote_buttons_until_moderator_starts_voting(self, mock_render, mock_get_container) -> None:
        trial_snapshot = _snapshot()
        trial_snapshot = GameDetailsSnapshot(
            game_id=trial_snapshot.game_id,
            room_id=trial_snapshot.room_id,
            moderator_user_id=trial_snapshot.moderator_user_id,
            status=trial_snapshot.status,
            phase="trial_voting",
            round_number=trial_snapshot.round_number,
            version=trial_snapshot.version,
            launched_at_epoch_seconds=trial_snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=trial_snapshot.ended_at_epoch_seconds,
            participants=trial_snapshot.participants,
            catalog=trial_snapshot.catalog,
            pending_trial=TrialStateSnapshot(
                murdered_user_id="u_mob",
                murderer_user_id=None,
                accused_user_id="u_mob",
                accused_selection_cursor=[],
                accused_selection_deadline_epoch_seconds=None,
                jury_user_ids=["u_police"],
                vote_deadline_epoch_seconds=None,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution=None,
            ),
        )

        class _TrialStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return trial_snapshot

        class _TrialStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _TrialStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _TrialStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-ctx")
        request.user = self.player

        response = detail(request, game_id="g-ctx")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_context["jury_prompt"]["show"])
        self.assertTrue(captured_context["jury_prompt"]["waiting_for_moderator"])
        self.assertFalse(captured_context["jury_prompt"]["can_vote"])

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_actionable_superpower_panel_for_don(self, mock_render, mock_get_container) -> None:
        trial_snapshot = _snapshot()
        trial_snapshot = GameDetailsSnapshot(
            game_id=trial_snapshot.game_id,
            room_id=trial_snapshot.room_id,
            moderator_user_id=trial_snapshot.moderator_user_id,
            status=trial_snapshot.status,
            phase="information",
            round_number=trial_snapshot.round_number,
            version=trial_snapshot.version,
            launched_at_epoch_seconds=trial_snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=trial_snapshot.ended_at_epoch_seconds,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_don",
                    username="don",
                    faction="Mob",
                    role_name="Don",
                    rank=2,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police",
                    username="police",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob",
                    username="mob",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=trial_snapshot.catalog,
            pending_trial=None,
        )

        class _TrialStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return trial_snapshot

        class _TrialStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _TrialStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _TrialStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-ctx")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_don", "username": "don"})()

        response = detail(request, game_id="g-ctx")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_context["superpower_panel"]["show"])
        self.assertEqual(captured_context["superpower_panel"]["kind"], "don")
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "Intimidation")
        self.assertTrue(captured_context["superpower_panel"]["can_activate"])

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_explicit_passive_only_superpower_panel_for_merchant(self, mock_render, mock_get_container) -> None:
        merchant_snapshot = GameDetailsSnapshot(
            game_id="g-merchant",
            room_id="r-merchant",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=1,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_merchant",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    life_state="alive",
                    money_balance=500,
                    power_state=ParticipantPowerStateSnapshot(
                        merchant_wholesale_order_used=False,
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_police",
                    username="police",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob_1",
                    username="mob1",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob_2",
                    username="mob2",
                    faction="Mob",
                    role_name="Gangster",
                    rank=2,
                    life_state="alive",
                    money_balance=200,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police_2",
                    username="deputy",
                    faction="Police",
                    role_name="Deputy",
                    rank=2,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police_3",
                    username="detective",
                    faction="Police",
                    role_name="Detective",
                    rank=3,
                    life_state="alive",
                    money_balance=220,
                ),
                ParticipantStateSnapshot(
                    user_id="u_trade",
                    username="supplier",
                    faction="Merchant",
                    role_name="Supplier",
                    rank=1,
                    life_state="alive",
                    money_balance=180,
                ),
            ],
            catalog=[
                CatalogItemStateSnapshot(
                    classification="gun_tier_1",
                    display_name="Handgun (Tier 1)",
                    base_price=150,
                    image_path="/static/items/defaults/default_gun_tier_1.svg",
                    is_active=True,
                )
            ],
            pending_trial=None,
        )

        class _MerchantStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return merchant_snapshot

        class _MerchantStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _MerchantStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _MerchantStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-merchant")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_merchant", "username": "merchant"})()

        response = detail(request, game_id="g-merchant")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_context["superpower_panel"]["show"])
        self.assertEqual(captured_context["superpower_panel"]["kind"], "merchant")
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "Wholesale Order")
        self.assertEqual(captured_context["superpower_panel"]["status_text"], "Ready during information phase.")
        self.assertTrue(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(len(captured_context["superpower_panel"]["target_rows"]), 1)
        self.assertEqual(captured_context["superpower_panel"]["target_rows"][0]["classification"], "gun_tier_1")
        self.assertEqual(captured_context["superpower_panel"]["target_rows"][0]["discounted_price"], 110)
        self.assertEqual(
            captured_context["superpower_panel"]["implementation_state"],
            "Activated power is fully usable from this card.",
        )

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_supplier_acquire_panel(self, mock_render, mock_get_container) -> None:
        supplier_snapshot = GameDetailsSnapshot(
            game_id="g-supplier",
            room_id="r-supplier",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=1,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_supplier",
                    username="supplier",
                    faction="Merchant",
                    role_name="Supplier",
                    rank=1,
                    life_state="alive",
                    money_balance=180,
                    power_state=ParticipantPowerStateSnapshot(
                        supplier_acquire_used=False,
                        supplier_acquire_target_user_id=None,
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=2,
                    life_state="alive",
                    money_balance=220,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police",
                    username="police",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob_1",
                    username="mob1",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob_2",
                    username="mob2",
                    faction="Mob",
                    role_name="Enforcer",
                    rank=2,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police_2",
                    username="police2",
                    faction="Police",
                    role_name="Deputy",
                    rank=2,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant_2",
                    username="smuggler",
                    faction="Merchant",
                    role_name="Smuggler",
                    rank=3,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police_3",
                    username="police3",
                    faction="Police",
                    role_name="Detective",
                    rank=3,
                    life_state="alive",
                    money_balance=250,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _SupplierStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return supplier_snapshot

        class _SupplierStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _SupplierStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _SupplierStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-supplier")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_supplier", "username": "supplier"})()

        response = detail(request, game_id="g-supplier")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_context["superpower_panel"]["show"])
        self.assertEqual(captured_context["superpower_panel"]["kind"], "supplier")
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "Acquire")
        self.assertEqual(captured_context["superpower_panel"]["status_text"], "Ready during information phase.")
        self.assertTrue(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(len(captured_context["superpower_panel"]["target_rows"]), 7)
        self.assertEqual(
            captured_context["superpower_panel"]["implementation_state"],
            "Activated power is fully usable from this card.",
        )

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_secret_word_panel_for_mob_player(self, mock_render, mock_get_container) -> None:
        mob_snapshot = GameDetailsSnapshot(
            game_id="g-mob-secret",
            room_id="r-mob-secret",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=1,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_mob",
                    username="mob",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police",
                    username="police",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob_2",
                    username="mob2",
                    faction="Mob",
                    role_name="Enforcer",
                    rank=2,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police_2",
                    username="police2",
                    faction="Police",
                    role_name="Deputy",
                    rank=2,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police_3",
                    username="police3",
                    faction="Police",
                    role_name="Detective",
                    rank=3,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant_2",
                    username="merchant2",
                    faction="Merchant",
                    role_name="Smuggler",
                    rank=2,
                    life_state="alive",
                    money_balance=250,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _MobSecretGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return mob_snapshot

        class _MobSecretRoomsInboundPort:
            def get_room_details(self, room_id: str) -> RoomDetailsSnapshot:
                return RoomDetailsSnapshot(
                    room_id="r-mob-secret",
                    name="Room",
                    status="open",
                    moderator_user_id="u_mod",
                    opened_at_epoch_seconds=1,
                    members=[],
                    items=[],
                    secret_mob_word="RAVEN",
                )

        class _MobSecretContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _MobSecretGameplayInboundPort()
                self.rooms_inbound_port = _MobSecretRoomsInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _MobSecretContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-mob-secret")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_mob", "username": "mob"})()

        response = detail(request, game_id="g-mob-secret")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_context["mob_secret_word_panel"]["show"])
        self.assertEqual(captured_context["mob_secret_word_panel"]["secret_word"], "RAVEN")
        self.assertEqual(captured_context["mob_secret_word_panel"]["viewer_label"], "Mob Faction")

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_secret_word_panel_for_moderator(self, mock_render, mock_get_container) -> None:
        moderator_snapshot = _snapshot()
        moderator_snapshot = replace(
            moderator_snapshot,
            room_id="r-mod-secret",
            moderator_user_id="u_mod",
            participants=[
                *moderator_snapshot.participants,
                ParticipantStateSnapshot(
                    user_id="u_mob_2",
                    username="mob2",
                    faction="Mob",
                    role_name="Enforcer",
                    rank=2,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police_2",
                    username="police2",
                    faction="Police",
                    role_name="Deputy",
                    rank=2,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant_2",
                    username="merchant2",
                    faction="Merchant",
                    role_name="Smuggler",
                    rank=2,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police_3",
                    username="police3",
                    faction="Police",
                    role_name="Detective",
                    rank=3,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
        )

        class _ModeratorSecretGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return moderator_snapshot

        class _ModeratorSecretRoomsInboundPort:
            def get_room_details(self, room_id: str) -> RoomDetailsSnapshot:
                return RoomDetailsSnapshot(
                    room_id="r-mod-secret",
                    name="Room",
                    status="open",
                    moderator_user_id="u_mod",
                    opened_at_epoch_seconds=1,
                    members=[],
                    items=[],
                    secret_mob_word="COBRA",
                )

        class _ModeratorSecretContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _ModeratorSecretGameplayInboundPort()
                self.rooms_inbound_port = _ModeratorSecretRoomsInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _ModeratorSecretContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-mod-secret")
        request.user = self.moderator

        response = detail(request, game_id="g-mod-secret")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_context["mob_secret_word_panel"]["show"])
        self.assertEqual(captured_context["mob_secret_word_panel"]["secret_word"], "COBRA")
        self.assertEqual(captured_context["mob_secret_word_panel"]["viewer_label"], "Moderator")

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_hides_secret_word_for_moderator_viewing_as_non_mob_in_dev_mode(
        self, mock_render, mock_get_container
    ) -> None:
        dev_snapshot = GameDetailsSnapshot(
            game_id="g-dev-secret",
            room_id="r-dev-secret",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=1,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_mod_view",
                    username="policeview",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob",
                    username="mob",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police_2",
                    username="deputy",
                    faction="Police",
                    role_name="Deputy",
                    rank=2,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob_2",
                    username="mob2",
                    faction="Mob",
                    role_name="Enforcer",
                    rank=2,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_police_3",
                    username="detective",
                    faction="Police",
                    role_name="Detective",
                    rank=3,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_merchant_2",
                    username="smuggler",
                    faction="Merchant",
                    role_name="Smuggler",
                    rank=2,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _DevSecretGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return dev_snapshot

        class _DevSecretRoomsInboundPort:
            def get_room_details(self, room_id: str) -> RoomDetailsSnapshot:
                return RoomDetailsSnapshot(
                    room_id="r-dev-secret",
                    name="Room",
                    status="open",
                    moderator_user_id="u_mod",
                    opened_at_epoch_seconds=1,
                    members=[],
                    items=[],
                    secret_mob_word="VIPER",
                )

        class _DevSecretContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _DevSecretGameplayInboundPort()
                self.rooms_inbound_port = _DevSecretRoomsInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = True

        mock_get_container.return_value = _DevSecretContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-dev-secret?as_user_id=u_mod_view")
        request.user = self.moderator

        response = detail(request, game_id="g-dev-secret")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(captured_context["page"].is_moderator)
        self.assertFalse(captured_context["mob_secret_word_panel"]["show"])

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_automatic_arms_dealer_superpower_panel(self, mock_render, mock_get_container) -> None:
        arms_dealer_snapshot = GameDetailsSnapshot(
            game_id="g-arms",
            room_id="r-arms",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=1,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_arms",
                    username="armsdealer",
                    faction="Merchant",
                    role_name="Arms Dealer",
                    rank=1,
                    life_state="alive",
                    money_balance=400,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mod",
                    username="moderator",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_p2",
                    username="deputy",
                    faction="Police",
                    role_name="Deputy",
                    rank=2,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_p3",
                    username="detective",
                    faction="Police",
                    role_name="Detective",
                    rank=3,
                    life_state="alive",
                    money_balance=220,
                ),
                ParticipantStateSnapshot(
                    user_id="u_m1",
                    username="mobboss",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_m2",
                    username="gangster",
                    faction="Mob",
                    role_name="Gangster",
                    rank=2,
                    life_state="alive",
                    money_balance=200,
                ),
                ParticipantStateSnapshot(
                    user_id="u_t2",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=2,
                    life_state="alive",
                    money_balance=500,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _ArmsDealerStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return arms_dealer_snapshot

        class _ArmsDealerStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _ArmsDealerStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _ArmsDealerStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-arms")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_arms", "username": "armsdealer"})()

        response = detail(request, game_id="g-arms")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_context["superpower_panel"]["show"])
        self.assertEqual(captured_context["superpower_panel"]["kind"], "info")
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "Starting Gun Cache")
        self.assertEqual(
            captured_context["superpower_panel"]["status_text"],
            "Starting loadout is resolved automatically at game launch.",
        )
        self.assertIn(
            "One Tier 1 gun is removed from central supply and placed in your inventory automatically when the session starts.",
            captured_context["superpower_panel"]["details"],
        )
        self.assertEqual(
            captured_context["superpower_panel"]["implementation_state"],
            "Automatic start-of-game loadout is live. No manual activation button is needed.",
        )

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_actionable_superpower_panel_for_deputy(self, mock_render, mock_get_container) -> None:
        deputy_snapshot = GameDetailsSnapshot(
            game_id="g-deputy",
            room_id="r-deputy",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=1,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_deputy",
                    username="deputy",
                    faction="Police",
                    role_name="Deputy",
                    rank=2,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_chief",
                    username="chief",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _DeputyStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return deputy_snapshot

        class _DeputyStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _DeputyStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _DeputyStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-deputy")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_deputy", "username": "deputy"})()

        response = detail(request, game_id="g-deputy")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_context["superpower_panel"]["show"])
        self.assertEqual(captured_context["superpower_panel"]["kind"], "deputy")
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "Protective Custody")
        self.assertEqual(
            captured_context["superpower_panel"]["status_text"],
            "Ready during information phase.",
        )
        self.assertTrue(captured_context["superpower_panel"]["can_activate"])
        self.assertIn("Protected targets cannot be killed for 5 minutes; attempted murders still trigger trial flow.", captured_context["superpower_panel"]["details"])
        self.assertEqual(
            captured_context["superpower_panel"]["implementation_state"],
            "Activated power is fully usable from this card.",
        )

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_explicit_passive_only_superpower_panel_for_gangster(self, mock_render, mock_get_container) -> None:
        mob_snapshot = GameDetailsSnapshot(
            game_id="g-gangster",
            room_id="r-gangster",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=1,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_gangster",
                    username="gangster",
                    faction="Mob",
                    role_name="Gangster",
                    rank=4,
                    life_state="alive",
                    money_balance=50,
                ),
                ParticipantStateSnapshot(
                    user_id="u_boss",
                    username="boss",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=100,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _GangsterStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return mob_snapshot

        class _GangsterStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _GangsterStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _GangsterStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-gangster")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_gangster", "username": "gangster"})()

        response = detail(request, game_id="g-gangster")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_context["superpower_panel"]["show"])
        self.assertEqual(captured_context["superpower_panel"]["kind"], "gangster")
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "Tamper")
        self.assertEqual(
            captured_context["superpower_panel"]["status_text"],
            "Status: Active",
        )
        self.assertIn("Gangster gains a separate replacement vote with its own timer; if already on the jury, Gangster may vote twice.", captured_context["superpower_panel"]["details"])
        self.assertEqual(
            captured_context["superpower_panel"]["implementation_state"],
            "Activated power is fully usable from this card.",
        )

    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_enforcer_superpower_status_when_used(self, mock_render, mock_get_container) -> None:
        enforcer_snapshot = GameDetailsSnapshot(
            game_id="g-enforcer",
            room_id="r-enforcer",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=4,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_enforcer",
                    username="enforcer",
                    faction="Mob",
                    role_name="Enforcer",
                    rank=2,
                    life_state="alive",
                    money_balance=180,
                    power_state=ParticipantPowerStateSnapshot(enforcer_first_kill_bonus_used=True),
                ),
                ParticipantStateSnapshot(
                    user_id="u_mod",
                    username="moderator",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=100,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _EnforcerStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return enforcer_snapshot

        class _EnforcerStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _EnforcerStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _EnforcerStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-enforcer")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_enforcer", "username": "enforcer"})()

        response = detail(request, game_id="g-enforcer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["role_name"], "Enforcer")
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "First Kill Bonus")
        self.assertEqual(captured_context["superpower_panel"]["status_text"], "Status: Used")

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_actionable_made_man_panel(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        made_man_snapshot = GameDetailsSnapshot(
            game_id="g-made-man",
            room_id="r-made-man",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="trial_voting",
            round_number=2,
            version=9,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_made",
                    username="mademan",
                    faction="Mob",
                    role_name="Made Man",
                    rank=3,
                    life_state="alive",
                    money_balance=250,
                    power_state=ParticipantPowerStateSnapshot(
                        made_man_skip_middle_man_used=False,
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_mod",
                    username="moderator",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=[
                CatalogItemStateSnapshot(
                    classification="gun_tier_1",
                    display_name="Handgun (Tier 1)",
                    base_price=150,
                    image_path="/static/items/defaults/default_gun_tier_1.svg",
                    is_active=True,
                )
            ],
            pending_trial=None,
        )

        class _MadeManStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return made_man_snapshot

        class _MadeManStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _MadeManStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _MadeManStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-made-man")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_made", "username": "mademan"})()

        response = detail(request, game_id="g-made-man")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["kind"], "made_man")
        self.assertTrue(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "Skip Middle Man")

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_actionable_street_thug_panel(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        street_thug_snapshot = GameDetailsSnapshot(
            game_id="g-street-thug",
            room_id="r-street-thug",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="boundary_resolution",
            round_number=2,
            version=9,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_thug",
                    username="thug",
                    faction="Mob",
                    role_name="Street Thug",
                    rank=4,
                    life_state="alive",
                    money_balance=20,
                    power_state=ParticipantPowerStateSnapshot(
                        street_thug_steal_used=False,
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_target",
                    username="target",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    life_state="alive",
                    money_balance=250,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _StreetThugStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return street_thug_snapshot

        class _StreetThugStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _StreetThugStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _StreetThugStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-street-thug")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_thug", "username": "thug"})()

        response = detail(request, game_id="g-street-thug")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["kind"], "street_thug")
        self.assertTrue(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "Steal")
        self.assertEqual([row.username for row in captured_context["superpower_panel"]["target_rows"]], ["target"])

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_actionable_smuggler_panel(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        smuggler_snapshot = GameDetailsSnapshot(
            game_id="g-smuggler",
            room_id="r-smuggler",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=2,
            version=9,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_smuggler",
                    username="smuggler",
                    faction="Merchant",
                    role_name="Smuggler",
                    rank=1,
                    life_state="alive",
                    money_balance=400,
                    power_state=ParticipantPowerStateSnapshot(
                        smuggler_smuggle_used=False,
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_target",
                    username="target",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mod",
                    username="moderator",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_p2",
                    username="deputy",
                    faction="Police",
                    role_name="Deputy",
                    rank=2,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_p3",
                    username="detective",
                    faction="Police",
                    role_name="Detective",
                    rank=3,
                    life_state="alive",
                    money_balance=220,
                ),
                ParticipantStateSnapshot(
                    user_id="u_m2",
                    username="gangster",
                    faction="Mob",
                    role_name="Gangster",
                    rank=2,
                    life_state="alive",
                    money_balance=200,
                ),
                ParticipantStateSnapshot(
                    user_id="u_t2",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=2,
                    life_state="alive",
                    money_balance=500,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _SmugglerStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return smuggler_snapshot

        class _SmugglerStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _SmugglerStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _SmugglerStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-smuggler")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_smuggler", "username": "smuggler"})()

        response = detail(request, game_id="g-smuggler")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["kind"], "smuggler")
        self.assertTrue(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "Smuggle")
        self.assertEqual(
            [row.username for row in captured_context["superpower_panel"]["target_rows"]],
            ["deputy", "detective", "gangster", "merchant", "moderator", "target"],
        )

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_active_gun_runner_charisma_panel(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        gun_runner_snapshot = GameDetailsSnapshot(
            game_id="g-runner",
            room_id="r-runner",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=5,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_runner",
                    username="runner",
                    faction="Merchant",
                    role_name="Gun Runner",
                    rank=1,
                    life_state="alive",
                    money_balance=400,
                    power_state=ParticipantPowerStateSnapshot(
                        gun_runner_charisma_used=True,
                        gun_runner_charisma_expires_at_epoch_seconds=1180,
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_mod",
                    username="moderator",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_p2",
                    username="deputy",
                    faction="Police",
                    role_name="Deputy",
                    rank=2,
                    life_state="alive",
                    money_balance=250,
                ),
                ParticipantStateSnapshot(
                    user_id="u_p3",
                    username="detective",
                    faction="Police",
                    role_name="Detective",
                    rank=3,
                    life_state="alive",
                    money_balance=220,
                ),
                ParticipantStateSnapshot(
                    user_id="u_m1",
                    username="mobboss",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_t2",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=2,
                    life_state="alive",
                    money_balance=500,
                ),
                ParticipantStateSnapshot(
                    user_id="u_t3",
                    username="smuggler",
                    faction="Merchant",
                    role_name="Smuggler",
                    rank=3,
                    life_state="alive",
                    money_balance=400,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _GunRunnerStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return gun_runner_snapshot

        class _GunRunnerStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _GunRunnerStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _GunRunnerStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-runner")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_runner", "username": "runner"})()

        response = detail(request, game_id="g-runner")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["kind"], "gun_runner")
        self.assertFalse(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(captured_context["superpower_panel"]["ability_name"], "Charisma")
        self.assertEqual(captured_context["superpower_panel"]["charisma_state"]["visible_until_epoch_seconds"], 1180)

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_actionable_superpower_panel_for_sheriff(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        sheriff_snapshot = GameDetailsSnapshot(
            game_id="g-sheriff",
            room_id="r-sheriff",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="boundary_resolution",
            round_number=2,
            version=9,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_sheriff",
                    username="sheriff",
                    faction="Police",
                    role_name="Sheriff",
                    rank=2,
                    life_state="alive",
                    money_balance=250,
                    power_state=ParticipantPowerStateSnapshot(
                        sheriff_jury_log_views_used=1,
                        sheriff_jury_log_visible_until_epoch_seconds=1060,
                        sheriff_last_viewed_jury_user_ids=["u_chief", "u_mob"],
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_chief",
                    username="chief",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob",
                    username="mob",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=[],
            pending_trial=None,
            latest_jury_log_user_ids=["u_chief", "u_mob"],
        )

        class _SheriffStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return sheriff_snapshot

        class _SheriffStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _SheriffStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _SheriffStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-sheriff")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_sheriff", "username": "sheriff"})()

        response = detail(request, game_id="g-sheriff")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["kind"], "sheriff")
        self.assertEqual(captured_context["superpower_panel"]["remaining_uses"], 1)
        self.assertTrue(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(
            captured_context["superpower_panel"]["reveal_state"]["jury_usernames"],
            ["chief", "mob"],
        )

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_actionable_superpower_panel_for_captain(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        captain_snapshot = GameDetailsSnapshot(
            game_id="g-captain",
            room_id="r-captain",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="trial_voting",
            round_number=2,
            version=9,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_captain",
                    username="captain",
                    faction="Police",
                    role_name="Captain",
                    rank=3,
                    life_state="alive",
                    money_balance=250,
                    power_state=ParticipantPowerStateSnapshot(
                        captain_asset_freeze_used=False,
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_target",
                    username="target",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=[],
            pending_trial=None,
            asset_freeze_user_id="u_target",
            asset_freeze_by_user_id="u_captain",
            asset_freeze_expires_at_epoch_seconds=1600,
        )

        class _CaptainStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return captain_snapshot

        class _CaptainStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _CaptainStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _CaptainStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-captain")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_captain", "username": "captain"})()

        response = detail(request, game_id="g-captain")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["kind"], "captain")
        self.assertFalse(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(
            captured_context["superpower_panel"]["active_freeze"]["target_username"],
            "target",
        )
        self.assertTrue(captured_context["asset_freeze_panel"]["show"])

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_actionable_superpower_panel_for_lieutenant(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        lieutenant_snapshot = GameDetailsSnapshot(
            game_id="g-lieutenant",
            room_id="r-lieutenant",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="boundary_resolution",
            round_number=2,
            version=9,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_lieutenant",
                    username="lieutenant",
                    faction="Police",
                    role_name="Lieutenant",
                    rank=4,
                    life_state="alive",
                    money_balance=250,
                    power_state=ParticipantPowerStateSnapshot(
                        lieutenant_information_briefcase_used=True,
                        lieutenant_briefcase_visible_until_epoch_seconds=1060,
                        lieutenant_briefcase_alive_police_count=3,
                        lieutenant_briefcase_alive_mob_count=2,
                        lieutenant_briefcase_alive_merchant_count=1,
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_mob",
                    username="mob",
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

        class _LieutenantStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return lieutenant_snapshot

        class _LieutenantStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _LieutenantStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _LieutenantStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-lieutenant")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_lieutenant", "username": "lieutenant"})()

        response = detail(request, game_id="g-lieutenant")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["kind"], "lieutenant")
        self.assertFalse(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(captured_context["superpower_panel"]["reveal_state"]["alive_police_count"], 3)
        self.assertEqual(captured_context["superpower_panel"]["reveal_state"]["alive_mob_count"], 2)
        self.assertEqual(captured_context["superpower_panel"]["reveal_state"]["alive_merchant_count"], 1)

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_actionable_superpower_panel_for_sergeant(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        sergeant_snapshot = GameDetailsSnapshot(
            game_id="g-sergeant",
            room_id="r-sergeant",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=2,
            version=9,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_sergeant",
                    username="sergeant",
                    faction="Police",
                    role_name="Sergeant",
                    rank=5,
                    life_state="alive",
                    money_balance=250,
                    power_state=ParticipantPowerStateSnapshot(
                        sergeant_capture_used=False,
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_target",
                    username="target",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=[],
            pending_trial=None,
            sergeant_capture_user_id="u_target",
            sergeant_capture_by_user_id="u_sergeant",
            sergeant_capture_expires_at_epoch_seconds=1300,
        )

        class _SergeantStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return sergeant_snapshot

        class _SergeantStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _SergeantStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _SergeantStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-sergeant")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_sergeant", "username": "sergeant"})()

        response = detail(request, game_id="g-sergeant")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["kind"], "sergeant")
        self.assertFalse(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(captured_context["superpower_panel"]["active_capture"]["target_username"], "target")
        self.assertTrue(captured_context["sergeant_capture_panel"]["show"])

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_private_detective_investigation_reveal(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        detective_snapshot = GameDetailsSnapshot(
            game_id="g-detective",
            room_id="r-detective",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="boundary_resolution",
            round_number=2,
            version=9,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_detective",
                    username="detective",
                    faction="Police",
                    role_name="Detective",
                    rank=3,
                    life_state="alive",
                    money_balance=250,
                    power_state=ParticipantPowerStateSnapshot(
                        detective_investigation_used=True,
                        detective_investigation_visible_until_epoch_seconds=1060,
                        detective_investigation_target_user_id="u_target",
                        detective_last_viewed_transaction_total=2,
                        detective_last_viewed_transactions=[
                            PlayerTransactionSnapshot(
                                transaction_id="txn-1",
                                transaction_kind="money_gift",
                                sender_user_id="u_target",
                                recipient_user_id="u_other",
                                created_at_epoch_seconds=950,
                                money_amount=40,
                            ),
                            PlayerTransactionSnapshot(
                                transaction_id="txn-2",
                                transaction_kind="sale",
                                sender_user_id="u_other",
                                recipient_user_id="u_target",
                                created_at_epoch_seconds=980,
                                money_amount=125,
                                item_name="Knife",
                            ),
                        ],
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_target",
                    username="target",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="jailed",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_other",
                    username="other",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    life_state="alive",
                    money_balance=220,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _DetectiveStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return detective_snapshot

        class _DetectiveStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _DetectiveStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _DetectiveStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-detective")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_detective", "username": "detective"})()

        response = detail(request, game_id="g-detective")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["kind"], "detective")
        self.assertFalse(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(captured_context["superpower_panel"]["reveal_state"]["target_username"], "target")
        self.assertEqual(
            [row["transaction_type_label"] for row in captured_context["superpower_panel"]["reveal_state"]["transaction_rows"]],
            ["Money Gift", "Sale"],
        )
        self.assertTrue(captured_context["superpower_panel"]["reveal_state"]["has_fewer_than_three"])

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_labels_detective_stolen_item_history(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        detective_snapshot = GameDetailsSnapshot(
            game_id="g-detective-theft",
            room_id="r-detective-theft",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=1,
            version=3,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_detective",
                    username="detective",
                    faction="Police",
                    role_name="Detective",
                    rank=3,
                    life_state="alive",
                    money_balance=250,
                    power_state=ParticipantPowerStateSnapshot(
                        detective_investigation_used=True,
                        detective_investigation_visible_until_epoch_seconds=1060,
                        detective_investigation_target_user_id="u_target",
                        detective_last_viewed_transaction_total=1,
                        detective_last_viewed_transactions=[
                            PlayerTransactionSnapshot(
                                transaction_id="txn-theft",
                                transaction_kind="item_theft",
                                sender_user_id="u_target",
                                recipient_user_id="u_smuggler",
                                created_at_epoch_seconds=990,
                                item_name="Knife",
                            ),
                        ],
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_target",
                    username="target",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
                ParticipantStateSnapshot(
                    user_id="u_smuggler",
                    username="smuggler",
                    faction="Merchant",
                    role_name="Smuggler",
                    rank=1,
                    life_state="alive",
                    money_balance=220,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _DetectiveTheftStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return detective_snapshot

        class _DetectiveTheftStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _DetectiveTheftStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _DetectiveTheftStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-detective-theft")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_detective", "username": "detective"})()

        response = detail(request, game_id="g-detective-theft")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            captured_context["superpower_panel"]["reveal_state"]["transaction_rows"][0]["transaction_type_label"],
            "Stolen Item",
        )

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_private_inspector_record_inspection_reveal(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        inspector_snapshot = GameDetailsSnapshot(
            game_id="g-inspector",
            room_id="r-inspector",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="boundary_resolution",
            round_number=2,
            version=9,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_inspector",
                    username="inspector",
                    faction="Police",
                    role_name="Inspector",
                    rank=4,
                    life_state="alive",
                    money_balance=250,
                    power_state=ParticipantPowerStateSnapshot(
                        inspector_record_inspection_used=True,
                        inspector_record_visible_until_epoch_seconds=1060,
                        inspector_record_target_user_id="u_target",
                        inspector_last_viewed_role_name="Mob Boss",
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_target",
                    username="target",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="dead",
                    money_balance=300,
                ),
            ],
            catalog=[],
            pending_trial=None,
        )

        class _InspectorStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return inspector_snapshot

        class _InspectorStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _InspectorStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _InspectorStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-inspector")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_inspector", "username": "inspector"})()

        response = detail(request, game_id="g-inspector")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["kind"], "inspector")
        self.assertFalse(captured_context["superpower_panel"]["can_activate"])
        self.assertEqual(captured_context["superpower_panel"]["reveal_state"]["target_username"], "target")
        self.assertEqual(captured_context["superpower_panel"]["reveal_state"]["role_name"], "Mob Boss")

    @patch("project.mobboss_apps.gameplay.views.time.time", return_value=1000)
    @patch("project.mobboss_apps.gameplay.views.get_container")
    @patch("project.mobboss_apps.gameplay.views.render")
    def test_detail_context_includes_actionable_police_officer_confiscation_panel(
        self,
        mock_render,
        mock_get_container,
        _mock_time,
    ) -> None:
        officer_snapshot = GameDetailsSnapshot(
            game_id="g-officer",
            room_id="r-officer",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="accused_selection",
            round_number=2,
            version=9,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
                ParticipantStateSnapshot(
                    user_id="u_officer",
                    username="officer",
                    faction="Police",
                    role_name="Police Officer",
                    rank=6,
                    life_state="alive",
                    money_balance=250,
                    power_state=ParticipantPowerStateSnapshot(
                        police_officer_confiscation_used=False,
                        police_officer_confiscation_pending=False,
                    ),
                ),
                ParticipantStateSnapshot(
                    user_id="u_accused",
                    username="accused",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="alive",
                    money_balance=300,
                ),
            ],
            catalog=[],
            pending_trial=TrialStateSnapshot(
                murdered_user_id="u_dead",
                murderer_user_id="u_accused",
                accused_user_id="u_accused",
                accused_selection_cursor=[],
                accused_selection_deadline_epoch_seconds=None,
                jury_user_ids=[],
                vote_deadline_epoch_seconds=None,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution=None,
            ),
        )

        class _OfficerStubGameplayInboundPort:
            def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
                return officer_snapshot

        class _OfficerStubContainer:
            def __init__(self) -> None:
                self.gameplay_inbound_port = _OfficerStubGameplayInboundPort()
                self.room_state_poll_interval_seconds = 5
                self.room_dev_mode = False

        mock_get_container.return_value = _OfficerStubContainer()
        captured_context = {}

        def _fake_render(_request, _template_name, context):
            captured_context.update(context)
            return HttpResponse("ok")

        mock_render.side_effect = _fake_render
        request = self.factory.get("/games/g-officer")
        request.user = type("U", (), {"is_authenticated": True, "id": "u_officer", "username": "officer"})()

        response = detail(request, game_id="g-officer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_context["superpower_panel"]["kind"], "police_officer")
        self.assertTrue(captured_context["superpower_panel"]["can_activate"])
        self.assertFalse(captured_context["superpower_panel"]["pending"])


if __name__ == "__main__":
    unittest.main()
