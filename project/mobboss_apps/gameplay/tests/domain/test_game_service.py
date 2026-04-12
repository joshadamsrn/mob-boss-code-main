import sys
import unittest
import json
from dataclasses import replace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"

from project.mobboss_apps.gameplay.adapters.outbound.memory_impl import (  # noqa: E402
    MemoryGameplayOutboundPortImpl,
)
from project.mobboss_apps.gameplay.ports.room_lifecycle_outbound import (  # noqa: E402
    GameplayRoomLifecycleOutboundPort,
)
from project.mobboss_apps.gameplay.ports.internal import (  # noqa: E402
    ActivateDetectiveInvestigationCommand,
    ActivateGangsterTamperCommand,
    ActivateInspectorRecordInspectionCommand,
    ActivateStreetThugStealCommand,
    ActivateSmugglerSmuggleCommand,
    ActivateGunRunnerCharismaCommand,
    ActivateSupplierAcquireCommand,
    ActivateMerchantWholesaleOrderCommand,
    ActivateMadeManSkipMiddleManCommand,
    ActivatePoliceOfficerConfiscationCommand,
    ActivateSergeantCaptureCommand,
    ActivateLieutenantInformationBriefcaseCommand,
    ActivateCaptainAssetFreezeCommand,
    ActivateSheriffViewJuryLogCommand,
    ActivateDeputyProtectiveCustodyCommand,
    ActivateDonSilenceCommand,
    ActivateKingpinReduceClockCommand,
    ActivateUnderBossJuryOverrideCommand,
    BuyFromSupplyCommand,
    GiveMoneyCommand,
    InventoryItemStateSnapshot,
    MarkModeratorChatReadCommand,
    ModeratorAddFundsCommand,
    ModeratorChatThreadSnapshot,
    ModeratorTransferFundsCommand,
    ModeratorTransferInventoryItemCommand,
    OfferGiftItemCommand,
    RespondMoneyGiftOfferCommand,
    RespondGiftOfferCommand,
    RespondSaleOfferCommand,
    SendModeratorChatMessageCommand,
    KillGameCommand,
    AllowTrialVotingCommand,
    AdvanceAccusedSelectionTimeoutCommand,
    GameDetailsSnapshot,
    ParticipantStateSnapshot,
    ReportDeathCommand,
    SellInventoryItemCommand,
    SellInventoryToSupplyCommand,
    SetInventoryResalePriceCommand,
    LedgerStateSnapshot,
    LedgerEntrySnapshot,
    StartSessionCatalogItemInput,
    StartSessionFromRoomCommand,
    StartSessionParticipantInput,
    SubmitAccusedSelectionCommand,
    SubmitTrialVoteCommand,
    TrialStateSnapshot,
)
from project.mobboss_apps.gameplay.src.game_service import GameplayService, _select_trial_jury_user_ids  # noqa: E402
from project.mobboss_apps.mobboss.exceptions import ConflictProblem  # noqa: E402


class _StubRoomLifecycleOutboundPort(GameplayRoomLifecycleOutboundPort):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def mark_room_ended_for_game(self, *, room_id: str, game_id: str) -> None:
        self.calls.append((room_id, game_id))


def _load_json_fixture(name: str) -> dict:
    return json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))


def _build_start_session_command(name: str) -> StartSessionFromRoomCommand:
    payload = _load_json_fixture(name)
    return StartSessionFromRoomCommand(
        room_id=str(payload["room_id"]),
        moderator_user_id=str(payload["moderator_user_id"]),
        launched_at_epoch_seconds=int(payload["launched_at_epoch_seconds"]),
        participants=[
            StartSessionParticipantInput(
                user_id=str(participant["user_id"]),
                username=str(participant["username"]),
                faction=str(participant["faction"]),
                role_name=str(participant["role_name"]),
                rank=int(participant["rank"]),
                starting_balance=int(participant["starting_balance"]),
            )
            for participant in payload.get("participants", [])
        ],
        catalog=[
            StartSessionCatalogItemInput(
                classification=str(item["classification"]),
                display_name=str(item["display_name"]),
                base_price=int(item["base_price"]),
                image_path=str(item["image_path"]),
                is_active=bool(item["is_active"]),
            )
            for item in payload.get("catalog", [])
        ],
    )


class GameplayServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = MemoryGameplayOutboundPortImpl()
        self.room_lifecycle = _StubRoomLifecycleOutboundPort()
        self.now_epoch_seconds = 1000
        self.service = GameplayService(
            repository=self.repository,
            now_epoch_seconds_provider=lambda: self.now_epoch_seconds,
            room_lifecycle_outbound_port=self.room_lifecycle,
            efj_bribe_recipient_selector=lambda eligible: sorted(
                eligible,
                key=lambda participant: (participant.rank, participant.username.lower(), participant.user_id),
            )[0],
        )

    def test_start_session_from_room_bootstraps_information_phase_snapshot(self) -> None:
        command = _build_start_session_command("start_session_information.json")

        snapshot = self.service.start_session_from_room(command)

        self.assertTrue(snapshot.game_id.startswith("r-1-g"))
        self.assertEqual(snapshot.room_id, "r-1")
        self.assertEqual(snapshot.status, "in_progress")
        self.assertEqual(snapshot.phase, "information")
        self.assertEqual(snapshot.round_number, 1)
        self.assertEqual(snapshot.version, 1)
        self.assertEqual(snapshot.launched_at_epoch_seconds, 111)
        self.assertEqual(snapshot.ledger.circulating_currency_baseline, 600)
        self.assertEqual(snapshot.ledger.entries, [])
        self.assertIsNotNone(snapshot.ledger.checksum)
        self.assertEqual(len(snapshot.participants), 2)
        self.assertTrue(all(participant.life_state == "alive" for participant in snapshot.participants))
        self.assertEqual(snapshot.participants[0].money_balance, 300)
        self.assertEqual(snapshot.catalog[0].classification, "knife")

        fetched = self.service.get_game_details(snapshot.game_id)
        self.assertEqual(fetched.game_id, snapshot.game_id)

    def test_start_session_creates_one_moderator_chat_thread_per_player(self) -> None:
        snapshot = self.service.start_session_from_room(_build_start_session_command("start_session_information.json"))

        self.assertEqual(
            [thread.player_user_id for thread in snapshot.moderator_chat_threads],
            [participant.user_id for participant in snapshot.participants],
        )
        self.assertTrue(all(thread.messages == [] for thread in snapshot.moderator_chat_threads))
        self.assertEqual(snapshot.moderator_chat_version, 0)

    def test_player_can_send_private_message_to_moderator(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_information.json"))
        player = started.participants[0]

        updated = self.service.send_moderator_chat_message(
            SendModeratorChatMessageCommand(
                game_id=started.game_id,
                sender_user_id=player.user_id,
                thread_user_id=player.user_id,
                message_text="Need clarification from moderator",
                expected_version=started.moderator_chat_version,
            )
        )

        thread = next(thread for thread in updated.moderator_chat_threads if thread.player_user_id == player.user_id)
        self.assertEqual(updated.moderator_chat_version, 1)
        self.assertEqual(len(thread.messages), 1)
        self.assertEqual(thread.messages[0].sender_user_id, player.user_id)
        self.assertEqual(thread.unread_for_moderator_count, 1)
        self.assertEqual(thread.unread_for_player_count, 0)

    def test_player_cannot_send_message_into_another_players_thread(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_information.json"))
        player = started.participants[0]
        other_player = started.participants[1]

        with self.assertRaises(PermissionError):
            self.service.send_moderator_chat_message(
                SendModeratorChatMessageCommand(
                    game_id=started.game_id,
                    sender_user_id=player.user_id,
                    thread_user_id=other_player.user_id,
                    message_text="This should fail",
                    expected_version=started.moderator_chat_version,
                )
            )

    def test_moderator_can_mark_selected_thread_read(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_information.json"))
        player = started.participants[0]
        with_player_message = self.service.send_moderator_chat_message(
            SendModeratorChatMessageCommand(
                game_id=started.game_id,
                sender_user_id=player.user_id,
                thread_user_id=player.user_id,
                message_text="Private update",
                expected_version=started.moderator_chat_version,
            )
        )

        updated = self.service.mark_moderator_chat_read(
            MarkModeratorChatReadCommand(
                game_id=started.game_id,
                viewer_user_id=started.moderator_user_id,
                thread_user_id=player.user_id,
                expected_version=with_player_message.moderator_chat_version,
            )
        )

        thread = next(thread for thread in updated.moderator_chat_threads if thread.player_user_id == player.user_id)
        self.assertEqual(thread.unread_for_moderator_count, 0)
        self.assertEqual(thread.messages[0].body, "Private update")

    def test_trial_jury_selection_uses_all_eligible_players_when_three_or_fewer(self) -> None:
        participants = [
            ParticipantStateSnapshot(
                user_id=f"u_{index}",
                username=f"player{index}",
                faction="Police",
                role_name="Cop",
                rank=index,
                life_state="alive",
                money_balance=100,
            )
            for index in range(4)
        ]

        jury_user_ids = _select_trial_jury_user_ids(
            participants,
            accused_user_id="u_0",
            randomization_salt="jury-test",
        )

        self.assertEqual(len(jury_user_ids), 3)
        self.assertCountEqual(jury_user_ids, ["u_1", "u_2", "u_3"])

    def test_trial_jury_selection_uses_configured_alive_player_brackets(self) -> None:
        expected_sizes = {
            4: 3,
            8: 3,
            9: 5,
            15: 5,
            16: 7,
            20: 7,
            21: 9,
            25: 9,
        }

        for eligible_count, expected_size in expected_sizes.items():
            with self.subTest(eligible_count=eligible_count):
                participants = [
                    ParticipantStateSnapshot(
                        user_id=f"u_{index}",
                        username=f"player{index}",
                        faction="Police",
                        role_name="Cop",
                        rank=index,
                        life_state="alive",
                        money_balance=100,
                    )
                    for index in range(eligible_count + 1)
                ]

                jury_user_ids = _select_trial_jury_user_ids(
                    participants,
                    accused_user_id="u_0",
                    randomization_salt=f"jury-test-{eligible_count}",
                )

                self.assertEqual(len(jury_user_ids), expected_size)
                self.assertNotIn("u_0", jury_user_ids)

    def test_start_session_sets_last_progress_timestamp(self) -> None:
        command = _build_start_session_command("start_session_information.json")

        snapshot = self.service.start_session_from_room(command)

        self.assertEqual(snapshot.last_progressed_at_epoch_seconds, command.launched_at_epoch_seconds)

    def test_get_game_details_auto_ends_session_after_24_hours_of_inactivity(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))
        self.now_epoch_seconds = started.launched_at_epoch_seconds + (24 * 60 * 60) + 1

        updated = self.service.get_game_details(started.game_id)

        self.assertEqual(updated.status, "ended")
        self.assertEqual(updated.phase, "ended")
        self.assertEqual(updated.ended_at_epoch_seconds, self.now_epoch_seconds)
        self.assertEqual(updated.last_progressed_at_epoch_seconds, self.now_epoch_seconds)
        self.assertEqual(updated.latest_public_notice, "Game automatically ended after 24 hours of inactivity.")
        self.assertEqual(self.room_lifecycle.calls, [("r-2", started.game_id)])

    def test_arms_dealer_starts_with_one_tier_one_gun_taken_from_supply(self) -> None:
        snapshot = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-arms-dealer",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_arms", "armsdealer", "Merchant", "Arms Dealer", 1, 400),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    )
                ],
            )
        )

        arms_dealer = next(participant for participant in snapshot.participants if participant.user_id == "u_arms")
        gun_catalog_item = next(item for item in snapshot.catalog if item.classification == "gun_tier_1")
        self.assertEqual(len(arms_dealer.inventory), 1)
        self.assertEqual(arms_dealer.inventory[0].classification, "gun_tier_1")
        self.assertEqual(arms_dealer.inventory[0].acquisition_value, 150)
        self.assertEqual(arms_dealer.inventory[0].image_path, "/static/items/defaults/default_gun_tier_1.jpg")
        self.assertFalse(gun_catalog_item.is_active)
        self.assertTrue(
            any(
                event.user_id == "u_arms"
                and "started the game with a Tier 1 gun" in event.message
                for event in snapshot.notification_feed
            )
        )

    def test_report_death_moves_session_to_accused_selection_when_police_alive(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-accused-selection",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=222,
                participants=[
                    StartSessionParticipantInput("u_police", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_gang", "gang", "Mob", "Gangster", 3, 120),
                ],
                catalog=[],
            )
        )

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=1,
            )
        )

        murdered = next(participant for participant in updated.participants if participant.user_id == "u_mob")
        self.assertEqual(murdered.life_state, "dead")
        self.assertEqual(updated.phase, "accused_selection")
        self.assertEqual(updated.version, 2)
        self.assertIsNotNone(updated.pending_trial)
        self.assertEqual(updated.pending_trial.accused_selection_cursor, ["u_police"])
        self.assertIsNone(updated.pending_trial.accused_selection_deadline_epoch_seconds)
        self.assertIsNone(updated.pending_trial.resolution)
        self.assertEqual(
            updated.latest_public_notice,
            "MOB WAS MURDERED WITH KNIFE - REPORT IMMEDIATELY TO COURT HOUSE",
        )
        self.assertEqual(self.room_lifecycle.calls, [])

    def test_report_death_ends_game_and_syncs_linked_room_lifecycle(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_police",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=1,
            )
        )

        self.assertEqual(updated.status, "ended")
        self.assertEqual(updated.phase, "ended")
        self.assertEqual(updated.ended_at_epoch_seconds, 1000)
        self.assertEqual(self.room_lifecycle.calls, [("r-2", started.game_id)])

    def test_report_death_ends_game_immediately_when_last_mob_is_killed(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-last-mob",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[],
            )
        )

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                murderer_user_id="u_chief",
                attack_classification="knife",
                expected_version=started.version,
            )
        )

        self.assertEqual(updated.status, "ended")
        self.assertEqual(updated.phase, "ended")
        self.assertEqual(updated.winning_faction, "Police")
        self.assertIsNone(updated.pending_trial)
        self.assertEqual(updated.winning_user_id, None)

    def test_report_death_notifies_new_acting_chief_before_accused_selection(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-acting-chief",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 2, 250),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_gang", "gang", "Mob", "Gangster", 3, 120),
                ],
                catalog=[],
            )
        )

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_chief",
                murderer_user_id="u_mob",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )

        self.assertEqual(updated.phase, "accused_selection")
        self.assertEqual(updated.pending_trial.accused_selection_cursor, ["u_deputy"])
        self.assertTrue(
            any(
                event.user_id == "u_deputy" and event.message == "You are now the Acting Chief of Police."
                for event in updated.notification_feed
            )
        )

    def test_guilty_verdict_notifies_new_acting_mob_boss(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-acting-mob",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 2, 180),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_gang", "gang", "Mob", "Gangster", 3, 120),
                ],
                catalog=[],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_detective",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_chief",
                accused_user_id="u_mob",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        after_first_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_start_voting.game_id,
                voter_user_id=after_start_voting.pending_trial.jury_user_ids[0],
                vote="guilty",
                expected_version=after_start_voting.version,
            )
        )
        resolved = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_first_vote.game_id,
                voter_user_id=after_start_voting.pending_trial.jury_user_ids[1],
                vote="guilty",
                expected_version=after_first_vote.version,
            )
        )

        self.assertTrue(
            any(
                event.user_id == "u_gang" and event.message == "You are now the Acting Mob Boss."
                for event in resolved.notification_feed
            )
        )

    def test_report_death_without_alive_police_ends_game_when_mob_controls_remaining_players(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_no_police.json"))

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_merchant",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=1,
            )
        )

        self.assertEqual(updated.phase, "ended")
        self.assertEqual(updated.status, "ended")
        self.assertEqual(updated.winning_faction, "Mob")
        self.assertIsNone(updated.pending_trial)

    def test_report_death_rejects_stale_expected_version(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.report_death(
                ReportDeathCommand(
                    game_id=started.game_id,
                    murdered_user_id="u_mob",
                    reported_by_user_id="u_mod",
                    attack_classification="knife",
                    expected_version=started.version + 1,
                )
            )
        self.assertEqual(exc_ctx.exception.code, "version_conflict")
        self.assertEqual(
            exc_ctx.exception.extensions,
            {"expected_version": started.version + 1, "current_version": started.version},
        )

    def test_report_death_requires_moderator_reporter(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        with self.assertRaises(PermissionError):
            self.service.report_death(
                ReportDeathCommand(
                    game_id=started.game_id,
                    murdered_user_id="u_mob",
                    reported_by_user_id="u_police",
                    attack_classification="knife",
                    expected_version=started.version,
                )
            )

    def test_report_death_rejects_when_trial_already_pending(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))
        after_first = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )

        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.report_death(
                ReportDeathCommand(
                    game_id=after_first.game_id,
                    murdered_user_id="u_police",
                    reported_by_user_id="u_mod",
                    attack_classification="knife",
                    expected_version=after_first.version,
                )
            )
        self.assertEqual(exc_ctx.exception.code, "invalid_state")

    def test_self_reported_death_transfers_inventory_to_selected_murderer(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-self-report",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_mod",
                        username="moderator",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_hobo",
                        username="hobo",
                        faction="Mob",
                        role_name="Knife Hobo",
                        rank=2,
                        starting_balance=180,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_killer",
                        username="killer",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=100,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_hobo",
                reported_by_user_id="u_hobo",
                attack_classification="knife",
                murderer_user_id="u_killer",
                expected_version=started.version,
            )
        )

        murdered = next(participant for participant in updated.participants if participant.user_id == "u_hobo")
        killer = next(participant for participant in updated.participants if participant.user_id == "u_killer")

        self.assertEqual(murdered.life_state, "dead")
        self.assertEqual(len(murdered.inventory), 0)
        self.assertEqual(murdered.money_balance, 0)
        self.assertEqual(len(killer.inventory), 1)
        self.assertEqual(killer.inventory[0].classification, "knife")
        self.assertEqual(killer.money_balance, 480)
        self.assertEqual(len(updated.ledger.entries), 1)
        self.assertEqual(updated.ledger.entries[0].entry_kind, "murder_transfer")
        self.assertEqual(updated.ledger.entries[0].amount, 180)
        self.assertIsNotNone(updated.pending_trial)
        self.assertEqual(updated.pending_trial.murderer_user_id, "u_killer")

    def test_self_reported_death_requires_selected_murderer(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        with self.assertRaises(ValueError):
            self.service.report_death(
                ReportDeathCommand(
                    game_id=started.game_id,
                    murdered_user_id="u_mob",
                    reported_by_user_id="u_mob",
                    attack_classification="knife",
                    expected_version=started.version,
                )
            )

    def test_gunshot_vest_block_consumes_vest_routes_value_to_attacker_and_starts_trial(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-vest-block",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mod",
                        username="moderator",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_target",
                        username="target",
                        faction="Police",
                        role_name="Deputy",
                        rank=2,
                        starting_balance=250,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_attacker",
                        username="attacker",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="bulletproof_vest",
                        display_name="Bulletproof Vest",
                        base_price=50,
                        image_path="/static/items/defaults/default_bulletproof_vest.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="bulletproof_vest",
                expected_version=started.version,
            )
        )
        vest_item_id = next(
            participant for participant in after_buy.participants if participant.user_id == "u_merchant"
        ).inventory[0].item_id
        after_offer = self.service.offer_gift_item(
            OfferGiftItemCommand(
                game_id=after_buy.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_target",
                inventory_item_id=vest_item_id,
                expected_version=after_buy.version,
            )
        )
        after_accept = self.service.respond_gift_offer(
            RespondGiftOfferCommand(
                game_id=after_offer.game_id,
                receiver_user_id="u_target",
                gift_offer_id=after_offer.pending_gift_offers[0].gift_offer_id,
                accept=True,
                expected_version=after_offer.version,
            )
        )

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=after_accept.game_id,
                murdered_user_id="u_target",
                reported_by_user_id="u_mod",
                murderer_user_id="u_attacker",
                attack_classification="gun_tier_1",
                expected_version=after_accept.version,
            )
        )

        target = next(participant for participant in updated.participants if participant.user_id == "u_target")
        attacker = next(participant for participant in updated.participants if participant.user_id == "u_attacker")
        self.assertEqual(updated.phase, "accused_selection")
        self.assertIsNotNone(updated.pending_trial)
        self.assertEqual(updated.pending_trial.accused_selection_cursor, ["u_mod"])
        self.assertEqual(target.life_state, "alive")
        self.assertEqual(len(target.inventory), 0)
        self.assertEqual(target.money_balance, 250)
        self.assertEqual(attacker.money_balance, 350)
        self.assertEqual(updated.latest_public_notice, "ATTEMPTED MURDER ON TARGET WITH HANDGUN (TIER 1) - REPORT IMMEDIATELY TO COURT HOUSE")
        self.assertEqual(updated.latest_private_notice_user_id, "u_target")
        self.assertEqual(
            updated.latest_private_notice_message,
            "The murder attempt failed because your bulletproof vest stopped the shot.",
        )
        self.assertEqual(len(updated.ledger.entries), 2)
        self.assertEqual(updated.ledger.entries[-1].entry_kind, "vest_block_transfer")
        self.assertEqual(updated.ledger.entries[-1].amount, 50)
        self.assertEqual(updated.ledger.entries[-1].from_holder_id, "central_supply")
        self.assertEqual(updated.ledger.entries[-1].to_holder_id, "u_attacker")

    def test_knife_attack_does_not_trigger_bulletproof_vest(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-vest-knife",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mod",
                        username="moderator",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_target",
                        username="target",
                        faction="Police",
                        role_name="Deputy",
                        rank=2,
                        starting_balance=250,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_attacker",
                        username="attacker",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="bulletproof_vest",
                        display_name="Bulletproof Vest",
                        base_price=50,
                        image_path="/static/items/defaults/default_bulletproof_vest.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="bulletproof_vest",
                expected_version=started.version,
            )
        )
        vest_item_id = next(
            participant for participant in after_buy.participants if participant.user_id == "u_merchant"
        ).inventory[0].item_id
        after_offer = self.service.offer_gift_item(
            OfferGiftItemCommand(
                game_id=after_buy.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_target",
                inventory_item_id=vest_item_id,
                expected_version=after_buy.version,
            )
        )
        after_accept = self.service.respond_gift_offer(
            RespondGiftOfferCommand(
                game_id=after_offer.game_id,
                receiver_user_id="u_target",
                gift_offer_id=after_offer.pending_gift_offers[0].gift_offer_id,
                accept=True,
                expected_version=after_offer.version,
            )
        )

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=after_accept.game_id,
                murdered_user_id="u_target",
                reported_by_user_id="u_mod",
                murderer_user_id="u_attacker",
                attack_classification="knife",
                expected_version=after_accept.version,
            )
        )

        target = next(participant for participant in updated.participants if participant.user_id == "u_target")
        self.assertEqual(updated.phase, "accused_selection")
        self.assertIsNotNone(updated.pending_trial)
        self.assertEqual(target.life_state, "dead")
        self.assertEqual(len(target.inventory), 0)
        self.assertEqual(target.money_balance, 0)
        self.assertEqual(updated.pending_trial.murderer_user_id, "u_attacker")

    def test_cop_last_three_protection_auto_grants_system_vest_once(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-cop-last-three",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_cop", "cop", "Police", "Cop", 9, 300),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 100),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="bulletproof_vest",
                        display_name="Bulletproof Vest",
                        base_price=50,
                        image_path="/static/items/defaults/default_bulletproof_vest.svg",
                        is_active=True,
                    ),
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    ),
                ],
            )
        )

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_merchant",
                reported_by_user_id="u_mod",
                murderer_user_id="u_mob",
                attack_classification="gun_tier_1",
                expected_version=started.version,
            )
        )

        cop = next(participant for participant in updated.participants if participant.user_id == "u_cop")
        vest_items = [item for item in cop.inventory if item.classification == "bulletproof_vest"]
        self.assertTrue(cop.power_state.cop_last_three_protection_used)
        self.assertEqual(len(vest_items), 1)
        self.assertTrue(any(event.user_id == "u_cop" and "bulletproof vest" in event.message.lower() for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_mod" and "last three alive" in event.message.lower() for event in updated.notification_feed))

    def test_cop_last_three_protection_marks_used_without_adding_duplicate_vest(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-cop-existing-vest",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_cop", "cop", "Police", "Cop", 9, 300),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 500),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="bulletproof_vest",
                        display_name="Bulletproof Vest",
                        base_price=50,
                        image_path="/static/items/defaults/default_bulletproof_vest.svg",
                        is_active=True,
                    ),
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    ),
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="bulletproof_vest",
                expected_version=started.version,
            )
        )
        vest_item_id = next(
            participant for participant in after_buy.participants if participant.user_id == "u_merchant"
        ).inventory[0].item_id
        after_offer = self.service.offer_gift_item(
            OfferGiftItemCommand(
                game_id=after_buy.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_cop",
                inventory_item_id=vest_item_id,
                expected_version=after_buy.version,
            )
        )
        after_accept = self.service.respond_gift_offer(
            RespondGiftOfferCommand(
                game_id=after_offer.game_id,
                receiver_user_id="u_cop",
                gift_offer_id=after_offer.pending_gift_offers[0].gift_offer_id,
                accept=True,
                expected_version=after_offer.version,
            )
        )

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=after_accept.game_id,
                murdered_user_id="u_merchant",
                reported_by_user_id="u_mod",
                murderer_user_id="u_mob",
                attack_classification="gun_tier_1",
                expected_version=after_accept.version,
            )
        )

        cop = next(participant for participant in updated.participants if participant.user_id == "u_cop")
        vest_items = [item for item in cop.inventory if item.classification == "bulletproof_vest"]
        self.assertTrue(cop.power_state.cop_last_three_protection_used)
        self.assertEqual(len(vest_items), 1)

    def test_vest_blocked_attempted_murder_starts_accused_selection_for_acting_chief(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-vest-attempted-murder",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_cop", "cop", "Police", "Cop", 9, 300),
                    StartSessionParticipantInput("u_officer", "officer", "Police", "Police Officer", 9, 300),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="bulletproof_vest",
                        display_name="Bulletproof Vest",
                        base_price=50,
                        image_path="/static/items/defaults/default_bulletproof_vest.svg",
                        is_active=True,
                    ),
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    ),
                ],
            )
        )
        prepared = replace(
            started,
            participants=[
                replace(participant, life_state="dead")
                if participant.user_id == "u_chief"
                else replace(
                    participant,
                    inventory=[
                        InventoryItemStateSnapshot(
                            item_id="vest-cop",
                            classification="bulletproof_vest",
                            display_name="Bulletproof Vest",
                            image_path="/static/items/defaults/default_bulletproof_vest.svg",
                            acquisition_value=50,
                            resale_price=0,
                        )
                    ],
                )
                if participant.user_id == "u_cop"
                else participant
                for participant in started.participants
            ],
            current_police_leader_user_id="u_officer",
            version=started.version + 1,
        )
        self.repository.save_game_session(prepared)
        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=prepared.game_id,
                murdered_user_id="u_cop",
                reported_by_user_id="u_mod",
                murderer_user_id="u_mob",
                attack_classification="gun_tier_1",
                expected_version=prepared.version,
            )
        )

        cop = next(participant for participant in updated.participants if participant.user_id == "u_cop")
        officer = next(participant for participant in updated.participants if participant.user_id == "u_officer")
        self.assertEqual(updated.phase, "accused_selection")
        self.assertIsNotNone(updated.pending_trial)
        self.assertEqual(updated.pending_trial.accused_selection_cursor, ["u_officer"])
        self.assertEqual(
            updated.latest_public_notice,
            "ATTEMPTED MURDER ON COP WITH HANDGUN (TIER 1) - REPORT IMMEDIATELY TO COURT HOUSE",
        )
        self.assertEqual(updated.latest_private_notice_user_id, "u_cop")
        self.assertEqual(
            updated.latest_private_notice_message,
            "The murder attempt failed because your bulletproof vest stopped the shot.",
        )
        self.assertEqual(cop.life_state, "alive")
        self.assertEqual(officer.life_state, "alive")

    def test_cop_last_three_protection_triggers_when_guilty_verdict_reduces_alive_count_to_three(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-cop-verdict-trigger",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_cop", "cop", "Police", "Cop", 9, 300),
                    StartSessionParticipantInput("u_mob_boss", "boss", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_gangster", "gangster", "Mob", "Gangster", 2, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 300),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="bulletproof_vest",
                        display_name="Bulletproof Vest",
                        base_price=50,
                        image_path="/static/items/defaults/default_bulletproof_vest.svg",
                        is_active=True,
                    ),
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    ),
                ],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_merchant",
                reported_by_user_id="u_mod",
                murderer_user_id="u_mob_boss",
                attack_classification="gun_tier_1",
                expected_version=started.version,
            )
        )
        self.assertFalse(
            next(participant for participant in after_report.participants if participant.user_id == "u_cop")
            .power_state
            .cop_last_three_protection_used
        )

        after_accusal = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_mod",
                accused_user_id="u_mob_boss",
                expected_version=after_report.version,
            )
        )
        after_voting_open = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_accusal.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_accusal.version,
            )
        )
        after_vote_1 = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_voting_open.game_id,
                voter_user_id="u_cop",
                vote="guilty",
                expected_version=after_voting_open.version,
            )
        )
        after_vote_2 = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_vote_1.game_id,
                voter_user_id="u_gangster",
                vote="guilty",
                expected_version=after_vote_1.version,
            )
        )
        updated = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_vote_2.game_id,
                voter_user_id="u_mod",
                vote="guilty",
                expected_version=after_vote_2.version,
            )
        )

        cop = next(participant for participant in updated.participants if participant.user_id == "u_cop")
        vest_items = [item for item in cop.inventory if item.classification == "bulletproof_vest"]
        accused = next(participant for participant in updated.participants if participant.user_id == "u_mob_boss")
        self.assertEqual(accused.life_state, "jailed")
        self.assertTrue(cop.power_state.cop_last_three_protection_used)
        self.assertEqual(len(vest_items), 1)

    def test_enforcer_first_kill_bonus_awards_rounded_system_money_once(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-enforcer-bonus",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_enforcer", "enforcer", "Mob", "Enforcer", 2, 200),
                    StartSessionParticipantInput("u_target", "target", "Police", "Deputy", 2, 75),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    )
                ],
            )
        )

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_target",
                reported_by_user_id="u_mod",
                murderer_user_id="u_enforcer",
                attack_classification="gun_tier_1",
                expected_version=started.version,
            )
        )

        enforcer = next(participant for participant in updated.participants if participant.user_id == "u_enforcer")
        self.assertTrue(enforcer.power_state.enforcer_first_kill_bonus_used)
        self.assertEqual(enforcer.money_balance, 315)
        self.assertTrue(any(event.user_id == "u_enforcer" and "$40" in event.message for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_mod" and "$40" in event.message for event in updated.notification_feed))

    def test_enforcer_first_kill_bonus_is_consumed_on_zero_cash_kill(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-enforcer-zero",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_enforcer", "enforcer", "Mob", "Enforcer", 2, 200),
                    StartSessionParticipantInput("u_target", "target", "Police", "Deputy", 2, 0),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    )
                ],
            )
        )

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_target",
                reported_by_user_id="u_mod",
                murderer_user_id="u_enforcer",
                attack_classification="gun_tier_1",
                expected_version=started.version,
            )
        )

        enforcer = next(participant for participant in updated.participants if participant.user_id == "u_enforcer")
        self.assertTrue(enforcer.power_state.enforcer_first_kill_bonus_used)
        self.assertEqual(enforcer.money_balance, 200)
        self.assertTrue(any(event.user_id == "u_enforcer" and "$0" in event.message for event in updated.notification_feed))

    def test_enforcer_first_kill_bonus_does_not_trigger_when_already_used(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-enforcer-used",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_enforcer", "enforcer", "Mob", "Enforcer", 2, 200),
                    StartSessionParticipantInput("u_target", "target", "Police", "Deputy", 2, 50),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    )
                ],
            )
        )
        preused = replace(
            started,
            participants=[
                replace(
                    participant,
                    power_state=replace(participant.power_state, enforcer_first_kill_bonus_used=True),
                )
                if participant.user_id == "u_enforcer"
                else participant
                for participant in started.participants
            ],
        )
        self.repository.save_game_session(preused)

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=preused.game_id,
                murdered_user_id="u_target",
                reported_by_user_id="u_mod",
                murderer_user_id="u_enforcer",
                attack_classification="gun_tier_1",
                expected_version=preused.version,
            )
        )

        enforcer = next(participant for participant in updated.participants if participant.user_id == "u_enforcer")
        self.assertEqual(enforcer.money_balance, 250)

    def test_merchant_can_buy_one_active_supply_item_at_discount_once(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-merchant-wholesale",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 400),
                    StartSessionParticipantInput("u_other", "othermerchant", "Merchant", "Smuggler", 2, 400),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    )
                ],
            )
        )

        updated = self.service.activate_merchant_wholesale_order(
            ActivateMerchantWholesaleOrderCommand(
                game_id=started.game_id,
                actor_user_id="u_merchant",
                classification="gun_tier_1",
                expected_version=started.version,
            )
        )

        merchant = next(participant for participant in updated.participants if participant.user_id == "u_merchant")
        catalog_item = next(item for item in updated.catalog if item.classification == "gun_tier_1")
        self.assertTrue(merchant.power_state.merchant_wholesale_order_used)
        self.assertEqual(merchant.money_balance, 290)
        self.assertEqual(len(merchant.inventory), 1)
        self.assertEqual(merchant.inventory[0].classification, "gun_tier_1")
        self.assertEqual(merchant.inventory[0].acquisition_value, 110)
        self.assertFalse(catalog_item.is_active)
        self.assertTrue(
            any(
                entry.entry_kind == "central_supply_purchase"
                and entry.amount == 110
                and entry.from_holder_id == "u_merchant"
                and entry.to_holder_id == "central_supply"
                and "Wholesale Order purchase" in (entry.note or "")
                for entry in updated.ledger.entries
            )
        )
        self.assertTrue(
            any(event.user_id == "u_merchant" and "Wholesale Order" in event.message for event in updated.notification_feed)
        )

    def test_merchant_wholesale_order_is_not_consumed_on_insufficient_funds(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-merchant-wholesale-funds",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 100),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    )
                ],
            )
        )

        with self.assertRaises(ConflictProblem):
            self.service.activate_merchant_wholesale_order(
                ActivateMerchantWholesaleOrderCommand(
                    game_id=started.game_id,
                    actor_user_id="u_merchant",
                    classification="gun_tier_1",
                    expected_version=started.version,
                )
            )

        current = self.service.get_game_details(started.game_id)
        merchant = next(participant for participant in current.participants if participant.user_id == "u_merchant")
        self.assertFalse(merchant.power_state.merchant_wholesale_order_used)

    def test_made_man_can_buy_one_active_supply_item_directly_once(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-made-man",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_made", "mademan", "Mob", "Made Man", 3, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 400),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    )
                ],
            )
        )

        updated = self.service.activate_made_man_skip_middle_man(
            ActivateMadeManSkipMiddleManCommand(
                game_id=started.game_id,
                actor_user_id="u_made",
                classification="gun_tier_1",
                expected_version=started.version,
            )
        )

        made_man = next(participant for participant in updated.participants if participant.user_id == "u_made")
        catalog_item = next(item for item in updated.catalog if item.classification == "gun_tier_1")
        self.assertTrue(made_man.power_state.made_man_skip_middle_man_used)
        self.assertEqual(made_man.money_balance, 150)
        self.assertEqual(len(made_man.inventory), 1)
        self.assertEqual(made_man.inventory[0].classification, "gun_tier_1")
        self.assertFalse(catalog_item.is_active)
        self.assertTrue(any(event.user_id == "u_made" and "Skip Middle Man" in event.message for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_mod" and "burglarized" in event.message for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_merchant" and "burglarized" in event.message for event in updated.notification_feed))

    def test_made_man_power_is_not_consumed_on_insufficient_funds(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-made-man-funds",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_made", "mademan", "Mob", "Made Man", 3, 50),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="gun_tier_1",
                        display_name="Handgun (Tier 1)",
                        base_price=150,
                        image_path="/static/items/defaults/default_gun_tier_1.svg",
                        is_active=True,
                    )
                ],
            )
        )

        with self.assertRaises(ConflictProblem):
            self.service.activate_made_man_skip_middle_man(
                ActivateMadeManSkipMiddleManCommand(
                    game_id=started.game_id,
                    actor_user_id="u_made",
                    classification="gun_tier_1",
                    expected_version=started.version,
                )
            )

        current = self.service.get_game_details(started.game_id)
        made_man = next(participant for participant in current.participants if participant.user_id == "u_made")
        self.assertFalse(made_man.power_state.made_man_skip_middle_man_used)

    def test_street_thug_can_steal_100_dollars_once(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-street-thug",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_thug", "thug", "Mob", "Street Thug", 4, 20),
                    StartSessionParticipantInput("u_target", "target", "Merchant", "Merchant", 1, 250),
                ],
                catalog=[],
            )
        )

        updated = self.service.activate_street_thug_steal(
            ActivateStreetThugStealCommand(
                game_id=started.game_id,
                actor_user_id="u_thug",
                target_user_id="u_target",
                expected_version=started.version,
            )
        )

        street_thug = next(participant for participant in updated.participants if participant.user_id == "u_thug")
        target = next(participant for participant in updated.participants if participant.user_id == "u_target")
        self.assertTrue(street_thug.power_state.street_thug_steal_used)
        self.assertEqual(street_thug.money_balance, 120)
        self.assertEqual(target.money_balance, 150)
        self.assertTrue(
            any(
                entry.entry_kind == "street_thug_steal"
                and entry.amount == 100
                and entry.from_holder_id == "u_target"
                and entry.to_holder_id == "u_thug"
                for entry in updated.ledger.entries
            )
        )
        self.assertTrue(any(event.user_id == "u_thug" and "stole $100" in event.message for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_target" and "mugged" in event.message for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_mod" and "thug mugged target" in event.message for event in updated.notification_feed))

    def test_smuggler_can_steal_random_eligible_item_once_during_information(self) -> None:
        service = GameplayService(
            repository=self.repository,
            now_epoch_seconds_provider=lambda: self.now_epoch_seconds,
            room_lifecycle_outbound_port=self.room_lifecycle,
            efj_bribe_recipient_selector=lambda eligible: sorted(
                eligible,
                key=lambda participant: (participant.rank, participant.username.lower(), participant.user_id),
            )[0],
            smuggler_item_selector=lambda items: sorted(items, key=lambda item: item.display_name)[0],
        )
        started = service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-smuggler",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_smuggler", "smuggler", "Merchant", "Smuggler", 1, 400),
                    StartSessionParticipantInput("u_target", "target", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 3, 200),
                ],
                catalog=[],
            )
        )
        target_item = InventoryItemStateSnapshot(
            item_id="inv-target-1",
            classification="knife",
            display_name="Knife",
            image_path="/static/items/defaults/default_knife.svg",
            acquisition_value=100,
            resale_price=130,
        )
        target_snapshot = replace(
            started,
            participants=[
                replace(participant, inventory=[target_item]) if participant.user_id == "u_target" else participant
                for participant in started.participants
            ],
        )
        self.repository.save_game_session(target_snapshot)

        updated = service.activate_smuggler_smuggle(
            ActivateSmugglerSmuggleCommand(
                game_id=target_snapshot.game_id,
                actor_user_id="u_smuggler",
                target_user_id="u_target",
                expected_version=target_snapshot.version,
            )
        )

        smuggler = next(participant for participant in updated.participants if participant.user_id == "u_smuggler")
        target = next(participant for participant in updated.participants if participant.user_id == "u_target")
        self.assertTrue(smuggler.power_state.smuggler_smuggle_used)
        self.assertEqual(len(smuggler.inventory), 1)
        self.assertEqual(smuggler.inventory[0].item_id, "inv-target-1")
        self.assertEqual(smuggler.inventory[0].resale_price, 130)
        self.assertEqual(target.inventory, [])
        self.assertTrue(any(event.user_id == "u_target" and "burglarized" in event.message for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_smuggler" and "smuggled Knife" in event.message for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_mod" and "Knife was stolen" in event.message for event in updated.notification_feed))
        self.assertEqual(updated.player_transactions[-1].transaction_kind, "item_theft")
        self.assertEqual(updated.player_transactions[-1].item_name, "Knife")

        investigated = service.activate_detective_investigation(
            ActivateDetectiveInvestigationCommand(
                game_id=updated.game_id,
                actor_user_id="u_detective",
                target_user_id="u_target",
                expected_version=updated.version,
            )
        )
        detective = next(participant for participant in investigated.participants if participant.user_id == "u_detective")
        self.assertEqual(detective.power_state.detective_last_viewed_transaction_total, 1)
        self.assertEqual(detective.power_state.detective_last_viewed_transactions[0].transaction_kind, "item_theft")

    def test_smuggler_power_is_consumed_when_target_has_no_eligible_items(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-smuggler-empty",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_smuggler", "smuggler", "Merchant", "Smuggler", 1, 400),
                    StartSessionParticipantInput("u_target", "target", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[],
            )
        )

        updated = self.service.activate_smuggler_smuggle(
            ActivateSmugglerSmuggleCommand(
                game_id=started.game_id,
                actor_user_id="u_smuggler",
                target_user_id="u_target",
                expected_version=started.version,
            )
        )

        smuggler = next(participant for participant in updated.participants if participant.user_id == "u_smuggler")
        target = next(participant for participant in updated.participants if participant.user_id == "u_target")
        self.assertTrue(smuggler.power_state.smuggler_smuggle_used)
        self.assertEqual(smuggler.inventory, [])
        self.assertEqual(target.inventory, [])
        self.assertEqual(updated.player_transactions, [])

    def test_gun_runner_charisma_pays_system_bonus_on_accepted_sales_during_active_window(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-gun-runner",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_runner", "runner", "Merchant", "Gun Runner", 1, 500),
                    StartSessionParticipantInput("u_buyer", "buyer", "Police", "Chief of Police", 1, 400),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_runner",
                classification="knife",
                expected_version=started.version,
            )
        )
        runner = next(participant for participant in after_buy.participants if participant.user_id == "u_runner")
        inventory_item_id = runner.inventory[0].item_id
        after_price = self.service.set_inventory_resale_price(
            SetInventoryResalePriceCommand(
                game_id=after_buy.game_id,
                seller_user_id="u_runner",
                inventory_item_id=inventory_item_id,
                resale_price=130,
                expected_version=after_buy.version,
            )
        )
        after_charisma = self.service.activate_gun_runner_charisma(
            ActivateGunRunnerCharismaCommand(
                game_id=after_price.game_id,
                actor_user_id="u_runner",
                expected_version=after_price.version,
            )
        )
        self.assertTrue(
            next(participant for participant in after_charisma.participants if participant.user_id == "u_runner")
            .power_state
            .gun_runner_charisma_used
        )

        after_sale_offer = self.service.sell_inventory_item(
            SellInventoryItemCommand(
                game_id=after_charisma.game_id,
                seller_user_id="u_runner",
                buyer_user_id="u_buyer",
                inventory_item_id=inventory_item_id,
                expected_version=after_charisma.version,
            )
        )
        after_sale_accept = self.service.respond_sale_offer(
            RespondSaleOfferCommand(
                game_id=after_sale_offer.game_id,
                buyer_user_id="u_buyer",
                sale_offer_id=after_sale_offer.pending_sale_offers[0].sale_offer_id,
                accept=True,
                expected_version=after_sale_offer.version,
            )
        )

        runner_after_sale = next(participant for participant in after_sale_accept.participants if participant.user_id == "u_runner")
        self.assertEqual(runner_after_sale.money_balance, 550)
        self.assertTrue(
            any(
                entry.entry_kind == "gun_runner_charisma_bonus"
                and entry.amount == 40
                and entry.from_holder_id == "central_supply"
                and entry.to_holder_id == "u_runner"
                for entry in after_sale_accept.ledger.entries
            )
        )
        self.assertTrue(any(event.user_id == "u_runner" and "extra $40 bonus" in event.message for event in after_sale_accept.notification_feed))
        self.assertTrue(any(event.user_id == "u_mod" and "paid $40" in event.message for event in after_sale_accept.notification_feed))

    def test_gun_runner_charisma_does_not_pay_bonus_after_timer_expires(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-gun-runner-expired",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_runner", "runner", "Merchant", "Gun Runner", 1, 500),
                    StartSessionParticipantInput("u_buyer", "buyer", "Police", "Chief of Police", 1, 400),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_runner",
                classification="knife",
                expected_version=started.version,
            )
        )
        inventory_item_id = next(participant for participant in after_buy.participants if participant.user_id == "u_runner").inventory[0].item_id
        after_price = self.service.set_inventory_resale_price(
            SetInventoryResalePriceCommand(
                game_id=after_buy.game_id,
                seller_user_id="u_runner",
                inventory_item_id=inventory_item_id,
                resale_price=130,
                expected_version=after_buy.version,
            )
        )
        after_charisma = self.service.activate_gun_runner_charisma(
            ActivateGunRunnerCharismaCommand(
                game_id=after_price.game_id,
                actor_user_id="u_runner",
                expected_version=after_price.version,
            )
        )
        self.now_epoch_seconds = 2000

        after_sale_offer = self.service.sell_inventory_item(
            SellInventoryItemCommand(
                game_id=after_charisma.game_id,
                seller_user_id="u_runner",
                buyer_user_id="u_buyer",
                inventory_item_id=inventory_item_id,
                expected_version=after_charisma.version,
            )
        )
        after_sale_accept = self.service.respond_sale_offer(
            RespondSaleOfferCommand(
                game_id=after_sale_offer.game_id,
                buyer_user_id="u_buyer",
                sale_offer_id=after_sale_offer.pending_sale_offers[0].sale_offer_id,
                accept=True,
                expected_version=after_sale_offer.version,
            )
        )

        runner_after_sale = next(participant for participant in after_sale_accept.participants if participant.user_id == "u_runner")
        self.assertEqual(runner_after_sale.money_balance, 510)
        self.assertFalse(any(entry.entry_kind == "gun_runner_charisma_bonus" for entry in after_sale_accept.ledger.entries))

    def test_supplier_acquire_redirects_half_of_next_targeted_merchant_sale(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-supplier",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_supplier", "supplier", "Merchant", "Supplier", 1, 200),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 2, 400),
                    StartSessionParticipantInput("u_buyer", "buyer", "Police", "Chief of Police", 1, 400),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        merchant = next(participant for participant in after_buy.participants if participant.user_id == "u_merchant")
        inventory_item_id = merchant.inventory[0].item_id
        after_price = self.service.set_inventory_resale_price(
            SetInventoryResalePriceCommand(
                game_id=after_buy.game_id,
                seller_user_id="u_merchant",
                inventory_item_id=inventory_item_id,
                resale_price=130,
                expected_version=after_buy.version,
            )
        )
        after_acquire = self.service.activate_supplier_acquire(
            ActivateSupplierAcquireCommand(
                game_id=after_price.game_id,
                actor_user_id="u_supplier",
                target_user_id="u_merchant",
                expected_version=after_price.version,
            )
        )

        supplier = next(participant for participant in after_acquire.participants if participant.user_id == "u_supplier")
        self.assertTrue(supplier.power_state.supplier_acquire_used)
        self.assertEqual(supplier.power_state.supplier_acquire_target_user_id, "u_merchant")

        after_sale_offer = self.service.sell_inventory_item(
            SellInventoryItemCommand(
                game_id=after_acquire.game_id,
                seller_user_id="u_merchant",
                buyer_user_id="u_buyer",
                inventory_item_id=inventory_item_id,
                expected_version=after_acquire.version,
            )
        )
        after_sale_accept = self.service.respond_sale_offer(
            RespondSaleOfferCommand(
                game_id=after_sale_offer.game_id,
                buyer_user_id="u_buyer",
                sale_offer_id=after_sale_offer.pending_sale_offers[0].sale_offer_id,
                accept=True,
                expected_version=after_sale_offer.version,
            )
        )

        supplier_after_sale = next(participant for participant in after_sale_accept.participants if participant.user_id == "u_supplier")
        merchant_after_sale = next(participant for participant in after_sale_accept.participants if participant.user_id == "u_merchant")
        self.assertEqual(supplier_after_sale.money_balance, 270)
        self.assertEqual(merchant_after_sale.money_balance, 340)
        self.assertIsNone(supplier_after_sale.power_state.supplier_acquire_target_user_id)
        self.assertTrue(
            any(
                entry.entry_kind == "supplier_acquire_cut"
                and entry.amount == 70
                and entry.from_holder_id == "u_merchant"
                and entry.to_holder_id == "u_supplier"
                for entry in after_sale_accept.ledger.entries
            )
        )
        self.assertTrue(
            any(event.user_id == "u_supplier" and "Acquire stole $70" in event.message for event in after_sale_accept.notification_feed)
        )
        self.assertTrue(
            any(
                event.user_id == "u_merchant"
                and event.message == "Acquire power was used. $70 from your transaction was redirected to another player."
                for event in after_sale_accept.notification_feed
            )
        )
        self.assertTrue(
            any(event.user_id == "u_mod" and "Acquire stole $70" in event.message for event in after_sale_accept.notification_feed)
        )

    def test_supplier_acquire_consumes_on_wrong_guess(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-supplier-fail",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_supplier", "supplier", "Merchant", "Supplier", 1, 200),
                    StartSessionParticipantInput("u_police", "police", "Police", "Chief of Police", 1, 400),
                ],
                catalog=[],
            )
        )

        updated = self.service.activate_supplier_acquire(
            ActivateSupplierAcquireCommand(
                game_id=started.game_id,
                actor_user_id="u_supplier",
                target_user_id="u_police",
                expected_version=started.version,
            )
        )

        supplier = next(participant for participant in updated.participants if participant.user_id == "u_supplier")
        self.assertTrue(supplier.power_state.supplier_acquire_used)
        self.assertIsNone(supplier.power_state.supplier_acquire_target_user_id)
        self.assertTrue(
            any(event.user_id == "u_supplier" and "Acquire failed" in event.message for event in updated.notification_feed)
        )
        self.assertTrue(
            any(event.user_id == "u_mod" and "guess was wrong" in event.message for event in updated.notification_feed)
        )

    def test_supplier_acquire_cancels_when_supplier_is_frozen(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-supplier-freeze",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_supplier", "supplier", "Merchant", "Supplier", 1, 200),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 2, 400),
                    StartSessionParticipantInput("u_captain", "captain", "Police", "Captain", 2, 300),
                ],
                catalog=[],
            )
        )
        after_acquire = self.service.activate_supplier_acquire(
            ActivateSupplierAcquireCommand(
                game_id=started.game_id,
                actor_user_id="u_supplier",
                target_user_id="u_merchant",
                expected_version=started.version,
            )
        )

        updated = self.service.activate_captain_asset_freeze(
            ActivateCaptainAssetFreezeCommand(
                game_id=after_acquire.game_id,
                actor_user_id="u_captain",
                target_user_id="u_supplier",
                expected_version=after_acquire.version,
            )
        )

        supplier = next(participant for participant in updated.participants if participant.user_id == "u_supplier")
        self.assertTrue(supplier.power_state.supplier_acquire_used)
        self.assertIsNone(supplier.power_state.supplier_acquire_target_user_id)
        self.assertTrue(
            any(
                event.user_id == "u_supplier"
                and "Acquire was canceled because your accounts are frozen." in event.message
                for event in updated.notification_feed
            )
        )
        self.assertTrue(
            any(
                event.user_id == "u_mod"
                and "Acquire was canceled because the Supplier is frozen." in event.message
                for event in updated.notification_feed
            )
        )

    def test_street_thug_power_is_consumed_when_target_has_less_than_100(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-street-thug-short",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_thug", "thug", "Mob", "Street Thug", 4, 20),
                    StartSessionParticipantInput("u_target", "target", "Merchant", "Merchant", 1, 90),
                ],
                catalog=[],
            )
        )

        updated = self.service.activate_street_thug_steal(
            ActivateStreetThugStealCommand(
                game_id=started.game_id,
                actor_user_id="u_thug",
                target_user_id="u_target",
                expected_version=started.version,
            )
        )

        street_thug = next(participant for participant in updated.participants if participant.user_id == "u_thug")
        target = next(participant for participant in updated.participants if participant.user_id == "u_target")
        self.assertTrue(street_thug.power_state.street_thug_steal_used)
        self.assertEqual(street_thug.money_balance, 20)
        self.assertEqual(target.money_balance, 90)
        self.assertFalse(any(entry.entry_kind == "street_thug_steal" for entry in updated.ledger.entries))
        self.assertTrue(any(event.user_id == "u_thug" and "Steal was wasted" in event.message for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_target" and "less than $100" in event.message for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_mod" and "less than $100" in event.message for event in updated.notification_feed))

    def test_felon_jail_starts_escape_timer_and_notifies_felon_and_moderator(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-felon",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_police", "police", "Police", "Cop", 2, 250),
                    StartSessionParticipantInput("u_felon", "felon", "Mob", "Felon", 5, 100),
                    StartSessionParticipantInput("u_mob", "mobboss", "Mob", "Mob Boss", 1, 200),
                ],
                catalog=[],
            )
        )

        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_police",
                reported_by_user_id="u_mod",
                murderer_user_id="u_felon",
                attack_classification="knife",
                expected_version=started.version,
            )
        )
        after_accuse = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_mod",
                accused_user_id="u_felon",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_accuse.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_accuse.version,
            )
        )

        updated = after_start_voting
        jury_user_ids = list(after_start_voting.pending_trial.jury_user_ids) if after_start_voting.pending_trial else []
        for voter_user_id in jury_user_ids:
            updated = self.service.submit_trial_vote(
                SubmitTrialVoteCommand(
                    game_id=updated.game_id,
                    voter_user_id=voter_user_id,
                    vote="guilty",
                    expected_version=updated.version,
                )
            )

        felon = next(participant for participant in updated.participants if participant.user_id == "u_felon")
        self.assertEqual(felon.life_state, "jailed")
        self.assertEqual(updated.felon_escape_user_id, "u_felon")
        self.assertEqual(updated.felon_escape_expires_at_epoch_seconds, self.now_epoch_seconds + 1800)
        self.assertTrue(any(event.user_id == "u_felon" and "Sit out for 30 minutes" in event.message for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_mod" and "must sit out for 30 minutes" in event.message for event in updated.notification_feed))

    def test_felon_escapes_from_jail_after_timer_if_game_is_still_in_progress(self) -> None:
        jailed = GameDetailsSnapshot(
            game_id="g-felon-escape",
            room_id="r-felon-escape",
            moderator_user_id="u_mod",
            status="in_progress",
            phase="information",
            round_number=3,
            version=7,
            launched_at_epoch_seconds=100,
            ended_at_epoch_seconds=None,
            participants=[
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
                    money_balance=200,
                ),
            ],
            catalog=[],
            pending_trial=None,
            current_police_leader_user_id="u_mod",
            current_mob_leader_user_id="u_mob",
            felon_escape_user_id="u_felon",
            felon_escape_expires_at_epoch_seconds=1200,
            ledger=LedgerStateSnapshot(circulating_currency_baseline=600),
        )
        self.repository.save_game_session(jailed)
        self.now_epoch_seconds = 1201

        updated = self.service.get_game_details(jailed.game_id)

        felon = next(participant for participant in updated.participants if participant.user_id == "u_felon")
        self.assertEqual(felon.life_state, "alive")
        self.assertEqual(felon.money_balance, 10)
        self.assertIsNone(updated.felon_escape_user_id)
        self.assertIsNone(updated.felon_escape_expires_at_epoch_seconds)
        self.assertEqual(updated.latest_public_notice, "A felon has escaped from jail and is back in the game.")
        self.assertTrue(any(event.user_id == "u_felon" and "escaped from jail" in event.message for event in updated.notification_feed))

    def test_accused_selection_has_no_timeout_deadline(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-accused-deadline",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=444,
                participants=[
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 2, 250),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_gang", "gang", "Mob", "Gangster", 3, 120),
                ],
                catalog=[],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )

        self.assertEqual(after_report.phase, "accused_selection")
        self.assertEqual(after_report.pending_trial.accused_selection_cursor, ["u_chief"])
        self.assertIsNone(after_report.pending_trial.accused_selection_deadline_epoch_seconds)

    def test_submit_accused_selection_notifies_accused_player_of_trial(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-accused-notice",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=444,
                participants=[
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 2, 250),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_gang", "gang", "Mob", "Gangster", 3, 120),
                ],
                catalog=[],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )

        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_chief",
                accused_user_id="u_deputy",
                expected_version=after_report.version,
            )
        )

        accused_notifications = [
            event.message for event in after_selection.notification_feed if event.user_id == "u_deputy"
        ]
        self.assertIn(
            "You have been accused of murdering mob. You are being placed on trial.",
            accused_notifications,
        )

    def test_accused_selection_timeout_advance_requires_active_deadline(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_two_police.json"))
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )

        with self.assertRaises(ConflictProblem):
            self.service.advance_accused_selection_timeout(
                AdvanceAccusedSelectionTimeoutCommand(
                    game_id=after_report.game_id,
                    requested_by_user_id="u_mod",
                    expected_version=after_report.version,
                )
            )

    def test_police_cannot_win_if_police_mob_kills_exceed_allowed_formula(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_two_police.json"))
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                murderer_user_id="u_chief",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )

        self.assertEqual(after_report.total_mob_participants_at_start, 1)
        self.assertEqual(after_report.police_mob_kills_count, 1)
        self.assertEqual(after_report.phase, "ended")
        self.assertEqual(after_report.status, "ended")
        self.assertEqual(after_report.winning_faction, "Police")

    def test_mob_on_mob_kill_does_not_consume_police_allowed_kills(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-police-allowance",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_chief",
                        username="chief",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mob_a",
                        username="mob-a",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mob_b",
                        username="mob-b",
                        faction="Mob",
                        role_name="Under Boss",
                        rank=2,
                        starting_balance=250,
                    ),
                ],
                catalog=[],
            )
        )

        after_first_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob_a",
                murderer_user_id="u_mob_b",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )
        self.assertEqual(after_first_report.total_mob_participants_at_start, 2)
        self.assertEqual(after_first_report.police_mob_kills_count, 0)

        after_first_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_first_report.game_id,
                selected_by_user_id="u_chief",
                accused_user_id="u_chief",
                expected_version=after_first_report.version,
            )
        )
        after_first_voting_started = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_first_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_first_selection.version,
            )
        )
        after_first_boundary = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_first_voting_started.game_id,
                voter_user_id="u_mob_b",
                vote="innocent",
                expected_version=after_first_voting_started.version,
            )
        )
        self.assertEqual(after_first_boundary.status, "in_progress")
        self.assertEqual(after_first_boundary.phase, "information")

        self.assertEqual(after_first_boundary.police_mob_kills_count, 0)

    def test_advance_accused_selection_timeout_rejects_stale_expected_version(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_two_police.json"))
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )
        self.now_epoch_seconds = 1015

        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.advance_accused_selection_timeout(
                AdvanceAccusedSelectionTimeoutCommand(
                    game_id=after_report.game_id,
                    requested_by_user_id="u_mod",
                    expected_version=after_report.version + 1,
                )
            )
        self.assertEqual(exc_ctx.exception.code, "version_conflict")
        self.assertEqual(
            exc_ctx.exception.extensions,
            {"expected_version": after_report.version + 1, "current_version": after_report.version},
        )

    def test_submit_trial_vote_guilty_verdict_jails_accused_and_sets_vote_complete_resolution(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_two_police.json"))
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_chief",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_deputy",
                accused_user_id="u_mob",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )

        after_first_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_start_voting.game_id,
                voter_user_id="u_deputy",
                vote="guilty",
                expected_version=after_start_voting.version,
            )
        )

        accused = next(participant for participant in after_first_vote.participants if participant.user_id == "u_mob")
        self.assertEqual(after_first_vote.phase, "ended")
        self.assertEqual(after_first_vote.status, "ended")
        self.assertEqual(after_first_vote.winning_faction, "Police")
        self.assertEqual(after_first_vote.pending_trial.verdict, "guilty")
        self.assertEqual(after_first_vote.pending_trial.resolution, "vote_complete")
        self.assertEqual(accused.life_state, "jailed")
        self.assertEqual(after_first_vote.latest_public_notice, "Game ended. Police wins.")

    def test_allow_trial_voting_marks_jury_voting_active_without_default_timer(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_two_police.json"))
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_chief",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_deputy",
                accused_user_id="u_deputy",
                expected_version=after_report.version,
            )
        )

        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )

        self.assertIsNotNone(after_start_voting.pending_trial)
        self.assertEqual(after_start_voting.pending_trial.vote_deadline_epoch_seconds, -1)

    def test_gangster_tamper_can_replace_a_juror_vote_with_second_gangster_vote(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-gangster-tamper",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=100,
                participants=[
                    StartSessionParticipantInput("u_mod", "moderator", "Police", "Chief of Police", 1, 200),
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 2, 200),
                    StartSessionParticipantInput("u_gangster", "gangster", "Mob", "Gangster", 3, 200),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 200),
                    StartSessionParticipantInput("u_dead", "dead", "Merchant", "Merchant", 1, 200),
                ],
                catalog=[],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_dead",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                murderer_user_id="u_mob",
                expected_version=started.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_mod",
                accused_user_id="u_mob",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        after_chief_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_start_voting.game_id,
                voter_user_id="u_mod",
                vote="guilty",
                expected_version=after_start_voting.version,
            )
        )
        after_deputy_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_chief_vote.game_id,
                voter_user_id="u_deputy",
                vote="guilty",
                expected_version=after_chief_vote.version,
            )
        )
        after_tamper = self.service.activate_gangster_tamper(
            ActivateGangsterTamperCommand(
                game_id=after_deputy_vote.game_id,
                actor_user_id="u_gangster",
                target_user_id="u_mod",
                expected_version=after_deputy_vote.version,
            )
        )
        self.assertIsNotNone(after_tamper.pending_trial)
        self.assertEqual(after_tamper.pending_trial.gangster_tamper_target_user_id, "u_mod")
        self.assertIsNone(after_tamper.pending_trial.gangster_tamper_vote_deadline_epoch_seconds)
        after_gangster_jury_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_tamper.game_id,
                voter_user_id="u_gangster",
                vote="innocent",
                expected_version=after_tamper.version,
                vote_slot="jury",
            )
        )
        resolved = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_gangster_jury_vote.game_id,
                voter_user_id="u_gangster",
                vote="innocent",
                expected_version=after_gangster_jury_vote.version,
                vote_slot="tamper",
            )
        )

        self.assertEqual(resolved.phase, "information")
        self.assertIsNone(resolved.pending_trial)
        self.assertEqual(resolved.latest_public_notice, "mob was found not guilty.")

    def test_tied_jury_returns_hung_jury_mistrial_notice(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-hung-jury",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_captain", "captain", "Police", "Captain", 4, 260),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_hobo", "hobo", "Mob", "Knife Hobo", 2, 180),
                ],
                catalog=[],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_chief",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                murderer_user_id="u_hobo",
                expected_version=started.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_captain",
                accused_user_id="u_captain",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        first_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_start_voting.game_id,
                voter_user_id="u_mob",
                vote="guilty",
                expected_version=after_start_voting.version,
            )
        )
        resolved = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=first_vote.game_id,
                voter_user_id="u_hobo",
                vote="innocent",
                expected_version=first_vote.version,
            )
        )

        self.assertEqual(resolved.phase, "information")
        self.assertIsNone(resolved.pending_trial)
        self.assertEqual(resolved.latest_public_notice, "Hung jury. captain was found not guilty due to mistrial.")

    def test_deputy_can_activate_protective_custody_once_during_information_phase(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-deputy-custody",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 1, 200),
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 2, 250),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 200),
                ],
                catalog=[],
            )
        )

        updated = self.service.activate_deputy_protective_custody(
            ActivateDeputyProtectiveCustodyCommand(
                game_id=started.game_id,
                actor_user_id="u_deputy",
                target_user_id="u_mob",
                expected_version=started.version,
            )
        )

        deputy = next(participant for participant in updated.participants if participant.user_id == "u_deputy")
        self.assertTrue(deputy.power_state.deputy_protective_custody_used)
        self.assertEqual(updated.protective_custody_user_id, "u_mob")
        self.assertEqual(updated.protective_custody_by_user_id, "u_deputy")
        self.assertEqual(updated.protective_custody_expires_at_epoch_seconds, 1300)
        self.assertTrue(any(event.user_id == "u_mod" for event in updated.notification_feed))
        self.assertTrue(any(event.user_id == "u_deputy" for event in updated.notification_feed))
        self.assertTrue(
            any(
                event.user_id == "u_mob"
                and event.message == "You are under police protective custody for 5 minutes. Murder attempts on you will fail."
                for event in updated.notification_feed
            )
        )

    def test_attempted_murder_on_protected_target_starts_trial_without_killing_or_transfer(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-attempted",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 1, 200),
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 2, 250),
                    StartSessionParticipantInput("u_hobo", "hobo", "Mob", "Knife Hobo", 2, 150),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[],
            )
        )
        after_custody = self.service.activate_deputy_protective_custody(
            ActivateDeputyProtectiveCustodyCommand(
                game_id=started.game_id,
                actor_user_id="u_deputy",
                target_user_id="u_hobo",
                expected_version=started.version,
            )
        )

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=after_custody.game_id,
                murdered_user_id="u_hobo",
                reported_by_user_id="u_hobo",
                murderer_user_id="u_mob",
                attack_classification="knife",
                expected_version=after_custody.version,
            )
        )

        hobo = next(participant for participant in updated.participants if participant.user_id == "u_hobo")
        mob = next(participant for participant in updated.participants if participant.user_id == "u_mob")
        self.assertEqual(hobo.life_state, "alive")
        self.assertEqual(hobo.money_balance, 150)
        self.assertTrue(any(item.classification == "knife" for item in hobo.inventory))
        self.assertEqual(mob.money_balance, 300)
        self.assertEqual(updated.phase, "accused_selection")
        self.assertIsNotNone(updated.pending_trial)
        self.assertEqual(updated.pending_trial.murdered_user_id, "u_hobo")
        self.assertEqual(
            updated.latest_public_notice,
            "ATTEMPTED MURDER ON HOBO WITH KNIFE - REPORT IMMEDIATELY TO COURT HOUSE",
        )
        self.assertEqual(updated.latest_private_notice_user_id, "u_hobo")
        self.assertEqual(
            updated.latest_private_notice_message,
            "The murder attempt failed because you were under protective custody.",
        )
        self.assertEqual(updated.ledger.entries, [])

    def test_sheriff_can_view_most_recent_jury_log_twice(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-sheriff-log",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_sheriff", "sheriff", "Police", "Sheriff", 2, 200),
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 250),
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 3, 180),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_gang", "gang", "Mob", "Gangster", 3, 120),
                ],
                catalog=[],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_detective",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_chief",
                accused_user_id="u_mob",
                expected_version=after_report.version,
            )
        )

        first_view = self.service.activate_sheriff_view_jury_log(
            ActivateSheriffViewJuryLogCommand(
                game_id=after_selection.game_id,
                actor_user_id="u_sheriff",
                expected_version=after_selection.version,
            )
        )
        sheriff_after_first = next(participant for participant in first_view.participants if participant.user_id == "u_sheriff")
        self.assertEqual(sheriff_after_first.power_state.sheriff_jury_log_views_used, 1)
        self.assertEqual(
            sheriff_after_first.power_state.sheriff_last_viewed_jury_user_ids,
            first_view.latest_jury_log_user_ids,
        )
        self.assertEqual(sheriff_after_first.power_state.sheriff_jury_log_visible_until_epoch_seconds, 1060)

        second_view = self.service.activate_sheriff_view_jury_log(
            ActivateSheriffViewJuryLogCommand(
                game_id=first_view.game_id,
                actor_user_id="u_sheriff",
                expected_version=first_view.version,
            )
        )
        sheriff_after_second = next(participant for participant in second_view.participants if participant.user_id == "u_sheriff")
        self.assertEqual(sheriff_after_second.power_state.sheriff_jury_log_views_used, 2)

        with self.assertRaises(ConflictProblem):
            self.service.activate_sheriff_view_jury_log(
                ActivateSheriffViewJuryLogCommand(
                    game_id=second_view.game_id,
                    actor_user_id="u_sheriff",
                    expected_version=second_view.version,
                )
            )

    def test_sheriff_view_jury_log_fails_when_no_jury_history(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-sheriff-empty",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_sheriff", "sheriff", "Police", "Sheriff", 2, 200),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 150),
                ],
                catalog=[],
            )
        )

        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.activate_sheriff_view_jury_log(
                ActivateSheriffViewJuryLogCommand(
                    game_id=started.game_id,
                    actor_user_id="u_sheriff",
                    expected_version=started.version,
                )
            )

        self.assertEqual(str(exc_ctx.exception), "No jury history yet")

    def test_captain_asset_freeze_cancels_pending_transactions_and_notifies_involved_players(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-captain-freeze",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_captain", "captain", "Police", "Captain", 3, 250),
                    StartSessionParticipantInput("u_target", "target", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_hobo", "hobo", "Mob", "Knife Hobo", 2, 200),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 220),
                ],
                catalog=[],
            )
        )
        gift_item_id = next(
            item.item_id
            for participant in started.participants
            if participant.user_id == "u_hobo"
            for item in participant.inventory
            if item.classification == "knife"
        )
        after_gift_offer = self.service.offer_gift_item(
            OfferGiftItemCommand(
                game_id=started.game_id,
                giver_user_id="u_hobo",
                receiver_user_id="u_target",
                inventory_item_id=gift_item_id,
                expected_version=started.version,
            )
        )
        after_money_offer = self.service.give_money(
            GiveMoneyCommand(
                game_id=after_gift_offer.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_target",
                amount=40,
                expected_version=after_gift_offer.version,
            )
        )

        updated = self.service.activate_captain_asset_freeze(
            ActivateCaptainAssetFreezeCommand(
                game_id=after_money_offer.game_id,
                actor_user_id="u_captain",
                target_user_id="u_target",
                expected_version=after_money_offer.version,
            )
        )

        captain = next(participant for participant in updated.participants if participant.user_id == "u_captain")
        self.assertTrue(captain.power_state.captain_asset_freeze_used)
        self.assertEqual(updated.asset_freeze_user_id, "u_target")
        self.assertEqual(updated.asset_freeze_by_user_id, "u_captain")
        self.assertEqual(updated.asset_freeze_expires_at_epoch_seconds, 1600)
        self.assertEqual(updated.pending_gift_offers, [])
        self.assertEqual(updated.pending_money_gift_offers, [])
        messages_by_user = {event.user_id: event.message for event in updated.notification_feed}
        self.assertEqual(
            messages_by_user["u_target"],
            "Your accounts have been temporarily frozen by the police department for 10 minutes. No transactions can go through at this time.",
        )
        self.assertEqual(messages_by_user["u_captain"], "You froze target's accounts for 10 minutes.")
        self.assertEqual(messages_by_user["u_mod"], "Captain froze target's accounts for 10 minutes.")
        self.assertIn("temporarily frozen by the police department", messages_by_user["u_hobo"])
        self.assertIn("temporarily frozen by the police department", messages_by_user["u_merchant"])

    def test_asset_freeze_blocks_money_transfer_actions_for_frozen_target(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-captain-block",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_captain", "captain", "Police", "Captain", 3, 250),
                    StartSessionParticipantInput("u_target", "target", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 220),
                ],
                catalog=[],
            )
        )
        after_freeze = self.service.activate_captain_asset_freeze(
            ActivateCaptainAssetFreezeCommand(
                game_id=started.game_id,
                actor_user_id="u_captain",
                target_user_id="u_target",
                expected_version=started.version,
            )
        )

        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.give_money(
                GiveMoneyCommand(
                    game_id=after_freeze.game_id,
                    giver_user_id="u_merchant",
                    receiver_user_id="u_target",
                    amount=20,
                    expected_version=after_freeze.version,
                )
            )

        self.assertIn("temporarily frozen by the police department", str(exc_ctx.exception))

    def test_lieutenant_information_briefcase_reveals_alive_faction_counts_once(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-lieutenant",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_lieutenant", "lieutenant", "Police", "Lieutenant", 4, 250),
                    StartSessionParticipantInput("u_police", "police", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_gang", "gang", "Mob", "Gangster", 3, 120),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 250),
                ],
                catalog=[],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )
        updated = self.service.activate_lieutenant_information_briefcase(
            ActivateLieutenantInformationBriefcaseCommand(
                game_id=after_report.game_id,
                actor_user_id="u_lieutenant",
                expected_version=after_report.version,
            )
        )
        lieutenant = next(participant for participant in updated.participants if participant.user_id == "u_lieutenant")
        self.assertTrue(lieutenant.power_state.lieutenant_information_briefcase_used)
        self.assertEqual(lieutenant.power_state.lieutenant_briefcase_visible_until_epoch_seconds, 1060)
        self.assertEqual(lieutenant.power_state.lieutenant_briefcase_alive_police_count, 2)
        self.assertEqual(lieutenant.power_state.lieutenant_briefcase_alive_mob_count, 1)
        self.assertEqual(lieutenant.power_state.lieutenant_briefcase_alive_merchant_count, 1)

        with self.assertRaises(ConflictProblem):
            self.service.activate_lieutenant_information_briefcase(
                ActivateLieutenantInformationBriefcaseCommand(
                    game_id=updated.game_id,
                    actor_user_id="u_lieutenant",
                    expected_version=updated.version,
                )
            )

    def test_sergeant_capture_applies_temporary_custody_and_blocks_target_actions(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-sergeant-capture",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_sergeant", "sergeant", "Police", "Sergeant", 5, 200),
                    StartSessionParticipantInput("u_target", "target", "Mob", "Mob Boss", 1, 250),
                    StartSessionParticipantInput("u_mob2", "mob2", "Mob", "Gangster", 2, 180),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 250),
                ],
                catalog=[],
            )
        )
        updated = self.service.activate_sergeant_capture(
            ActivateSergeantCaptureCommand(
                game_id=started.game_id,
                actor_user_id="u_sergeant",
                target_user_id="u_target",
                expected_version=started.version,
            )
        )
        sergeant = next(participant for participant in updated.participants if participant.user_id == "u_sergeant")
        self.assertTrue(sergeant.power_state.sergeant_capture_used)
        self.assertEqual(updated.sergeant_capture_user_id, "u_target")
        self.assertEqual(updated.sergeant_capture_by_user_id, "u_sergeant")
        self.assertEqual(updated.sergeant_capture_expires_at_epoch_seconds, 1300)
        messages_by_user = {event.user_id: event.message for event in updated.notification_feed}
        self.assertEqual(
            messages_by_user["u_target"],
            "You have been taken into custody by the police department for questioning and cannot interact with others for 5 minutes.",
        )
        self.assertIn("has been taken into custody by the police department", messages_by_user["u_mod"])
        self.assertEqual(messages_by_user["u_sergeant"], "You took target into police custody for 5 minutes.")

        with self.assertRaises(ConflictProblem):
            self.service.give_money(
                GiveMoneyCommand(
                    game_id=updated.game_id,
                    giver_user_id="u_merchant",
                    receiver_user_id="u_target",
                    amount=10,
                    expected_version=updated.version,
                )
            )

    def test_sergeant_capture_auto_releases_if_target_is_required_leader_with_no_replacement(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-sergeant-release",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_sergeant", "sergeant", "Police", "Sergeant", 5, 200),
                    StartSessionParticipantInput("u_target", "target", "Mob", "Mob Boss", 1, 250),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 250),
                ],
                catalog=[],
            )
        )
        updated = self.service.activate_sergeant_capture(
            ActivateSergeantCaptureCommand(
                game_id=started.game_id,
                actor_user_id="u_sergeant",
                target_user_id="u_target",
                expected_version=started.version,
            )
        )

        self.assertIsNone(updated.sergeant_capture_user_id)
        self.assertIsNone(updated.sergeant_capture_expires_at_epoch_seconds)
        self.assertTrue(any("court ordered to be released" in event.message for event in updated.notification_feed))
        self.assertTrue(
            any(
                event.user_id == "u_target"
                and event.message == "You were court ordered to be released from police custody."
                for event in updated.notification_feed
            )
        )

    def test_detective_can_investigate_last_three_player_transactions_for_jailed_target(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-detective-investigation",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 3, 200),
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 500),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=100,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_money_offer = self.service.give_money(
            GiveMoneyCommand(
                game_id=started.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_mob",
                amount=40,
                expected_version=started.version,
            )
        )
        after_money_accept = self.service.respond_money_gift_offer(
            RespondMoneyGiftOfferCommand(
                game_id=after_money_offer.game_id,
                receiver_user_id="u_mob",
                money_gift_offer_id=after_money_offer.pending_money_gift_offers[0].money_gift_offer_id,
                accept=True,
                expected_version=after_money_offer.version,
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=after_money_accept.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=after_money_accept.version,
            )
        )
        merchant_after_buy = next(participant for participant in after_buy.participants if participant.user_id == "u_merchant")
        inventory_item_id = merchant_after_buy.inventory[0].item_id
        after_price = self.service.set_inventory_resale_price(
            SetInventoryResalePriceCommand(
                game_id=after_buy.game_id,
                seller_user_id="u_merchant",
                inventory_item_id=inventory_item_id,
                resale_price=125,
                expected_version=after_buy.version,
            )
        )
        after_sale_offer = self.service.sell_inventory_item(
            SellInventoryItemCommand(
                game_id=after_price.game_id,
                seller_user_id="u_merchant",
                buyer_user_id="u_mob",
                inventory_item_id=inventory_item_id,
                expected_version=after_price.version,
            )
        )
        after_sale_accept = self.service.respond_sale_offer(
            RespondSaleOfferCommand(
                game_id=after_sale_offer.game_id,
                buyer_user_id="u_mob",
                sale_offer_id=after_sale_offer.pending_sale_offers[0].sale_offer_id,
                accept=True,
                expected_version=after_sale_offer.version,
            )
        )
        mob_after_sale = next(participant for participant in after_sale_accept.participants if participant.user_id == "u_mob")
        gifted_item_id = mob_after_sale.inventory[0].item_id
        after_gift_offer = self.service.offer_gift_item(
            OfferGiftItemCommand(
                game_id=after_sale_accept.game_id,
                giver_user_id="u_mob",
                receiver_user_id="u_detective",
                inventory_item_id=gifted_item_id,
                expected_version=after_sale_accept.version,
            )
        )
        after_gift_accept = self.service.respond_gift_offer(
            RespondGiftOfferCommand(
                game_id=after_gift_offer.game_id,
                receiver_user_id="u_detective",
                gift_offer_id=after_gift_offer.pending_gift_offers[0].gift_offer_id,
                accept=True,
                expected_version=after_gift_offer.version,
            )
        )
        jailed_snapshot = replace(
            after_gift_accept,
            phase="boundary_resolution",
            participants=[
                replace(participant, life_state="jailed") if participant.user_id == "u_mob" else participant
                for participant in after_gift_accept.participants
            ],
        )
        self.repository.save_game_session(jailed_snapshot)

        investigated = self.service.activate_detective_investigation(
            ActivateDetectiveInvestigationCommand(
                game_id=jailed_snapshot.game_id,
                actor_user_id="u_detective",
                target_user_id="u_mob",
                expected_version=jailed_snapshot.version,
            )
        )

        detective = next(participant for participant in investigated.participants if participant.user_id == "u_detective")
        self.assertTrue(detective.power_state.detective_investigation_used)
        self.assertEqual(detective.power_state.detective_investigation_visible_until_epoch_seconds, 1060)
        self.assertEqual(detective.power_state.detective_investigation_target_user_id, "u_mob")
        self.assertEqual(detective.power_state.detective_last_viewed_transaction_total, 3)
        self.assertEqual(
            [transaction.transaction_kind for transaction in detective.power_state.detective_last_viewed_transactions],
            ["money_gift", "sale", "item_gift"],
        )
        self.assertEqual(detective.power_state.detective_last_viewed_transactions[1].money_amount, 125)
        self.assertEqual(detective.power_state.detective_last_viewed_transactions[1].item_name, "Knife")
        self.assertEqual(detective.power_state.detective_last_viewed_transactions[2].sender_user_id, "u_mob")
        self.assertTrue(any(event.user_id == "u_detective" for event in investigated.notification_feed))

    def test_detective_investigation_uses_legacy_ledger_history_when_transaction_log_is_empty(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-detective-legacy",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 3, 200),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 500),
                ],
                catalog=[],
            )
        )
        legacy_snapshot = replace(
            started,
            ledger=replace(
                started.ledger,
                entries=[
                    *started.ledger.entries,
                    LedgerEntrySnapshot(
                        entry_id="led-legacy-1",
                        entry_kind="money_gift",
                        amount=35,
                        from_holder_id="u_merchant",
                        to_holder_id="u_mob",
                        created_at_epoch_seconds=900,
                        note="Accepted money gift offer.",
                    ),
                    LedgerEntrySnapshot(
                        entry_id="led-legacy-2",
                        entry_kind="participant_sale",
                        amount=120,
                        from_holder_id="u_mob",
                        to_holder_id="u_merchant",
                        created_at_epoch_seconds=950,
                        note="Participant sale: Knife",
                    ),
                ],
            ),
        )
        self.repository.save_game_session(legacy_snapshot)

        investigated = self.service.activate_detective_investigation(
            ActivateDetectiveInvestigationCommand(
                game_id=legacy_snapshot.game_id,
                actor_user_id="u_detective",
                target_user_id="u_mob",
                expected_version=legacy_snapshot.version,
            )
        )

        detective = next(participant for participant in investigated.participants if participant.user_id == "u_detective")
        self.assertEqual(detective.power_state.detective_last_viewed_transaction_total, 2)
        self.assertEqual(
            [transaction.transaction_kind for transaction in detective.power_state.detective_last_viewed_transactions],
            ["money_gift", "sale"],
        )
        self.assertEqual(detective.power_state.detective_last_viewed_transactions[1].item_name, "Knife")

    def test_detective_investigation_is_blocked_while_detective_is_in_custody(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-detective-blocked",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 3, 200),
                    StartSessionParticipantInput("u_sergeant", "sergeant", "Police", "Sergeant", 5, 200),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[],
            )
        )
        captured_snapshot = replace(
            started,
            sergeant_capture_user_id="u_detective",
            sergeant_capture_by_user_id="u_sergeant",
            sergeant_capture_expires_at_epoch_seconds=1300,
        )
        self.repository.save_game_session(captured_snapshot)

        with self.assertRaises(ConflictProblem):
            self.service.activate_detective_investigation(
                ActivateDetectiveInvestigationCommand(
                    game_id=captured_snapshot.game_id,
                    actor_user_id="u_detective",
                    target_user_id="u_mob",
                    expected_version=captured_snapshot.version,
                )
            )

    def test_inspector_can_view_role_name_of_dead_or_jailed_target_once(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-inspector-record",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_inspector", "inspector", "Police", "Inspector", 4, 200),
                    StartSessionParticipantInput("u_dead", "dead", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_jailed", "jailed", "Mob", "Gangster", 2, 180),
                    StartSessionParticipantInput("u_live", "live", "Merchant", "Merchant", 1, 220),
                ],
                catalog=[],
            )
        )
        prepared = replace(
            started,
            phase="boundary_resolution",
            participants=[
                replace(participant, life_state="dead")
                if participant.user_id == "u_dead"
                else (replace(participant, life_state="jailed") if participant.user_id == "u_jailed" else participant)
                for participant in started.participants
            ],
        )
        self.repository.save_game_session(prepared)

        inspected = self.service.activate_inspector_record_inspection(
            ActivateInspectorRecordInspectionCommand(
                game_id=prepared.game_id,
                actor_user_id="u_inspector",
                target_user_id="u_dead",
                expected_version=prepared.version,
            )
        )

        inspector = next(participant for participant in inspected.participants if participant.user_id == "u_inspector")
        self.assertTrue(inspector.power_state.inspector_record_inspection_used)
        self.assertEqual(inspector.power_state.inspector_record_visible_until_epoch_seconds, 1060)
        self.assertEqual(inspector.power_state.inspector_record_target_user_id, "u_dead")
        self.assertEqual(inspector.power_state.inspector_last_viewed_role_name, "Mob Boss")
        self.assertTrue(any(event.user_id == "u_inspector" for event in inspected.notification_feed))

        with self.assertRaises(ConflictProblem):
            self.service.activate_inspector_record_inspection(
                ActivateInspectorRecordInspectionCommand(
                    game_id=inspected.game_id,
                    actor_user_id="u_inspector",
                    target_user_id="u_jailed",
                    expected_version=inspected.version,
                )
            )

    def test_inspector_record_inspection_fails_when_no_dead_or_jailed_targets_exist(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-inspector-empty",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_inspector", "inspector", "Police", "Inspector", 4, 200),
                    StartSessionParticipantInput("u_live", "live", "Merchant", "Merchant", 1, 220),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[],
            )
        )

        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.activate_inspector_record_inspection(
                ActivateInspectorRecordInspectionCommand(
                    game_id=started.game_id,
                    actor_user_id="u_inspector",
                    target_user_id="u_mob",
                    expected_version=started.version,
                )
            )

        self.assertEqual(str(exc_ctx.exception), "No jail or morgue records available yet.")

    def test_inspector_record_inspection_is_blocked_while_inspector_is_in_custody(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-inspector-blocked",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_inspector", "inspector", "Police", "Inspector", 4, 200),
                    StartSessionParticipantInput("u_sergeant", "sergeant", "Police", "Sergeant", 5, 200),
                    StartSessionParticipantInput("u_dead", "dead", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[],
            )
        )
        captured_snapshot = replace(
            started,
            participants=[
                replace(participant, life_state="dead") if participant.user_id == "u_dead" else participant
                for participant in started.participants
            ],
            sergeant_capture_user_id="u_inspector",
            sergeant_capture_by_user_id="u_sergeant",
            sergeant_capture_expires_at_epoch_seconds=1300,
        )
        self.repository.save_game_session(captured_snapshot)

        with self.assertRaises(ConflictProblem):
            self.service.activate_inspector_record_inspection(
                ActivateInspectorRecordInspectionCommand(
                    game_id=captured_snapshot.game_id,
                    actor_user_id="u_inspector",
                    target_user_id="u_dead",
                    expected_version=captured_snapshot.version,
                )
            )

    def test_police_officer_confiscation_redistributes_guilty_resources(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-confiscation",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 2, 250),
                    StartSessionParticipantInput("u_officer", "officer", "Police", "Police Officer", 6, 200),
                    StartSessionParticipantInput("u_hobo", "hobo", "Mob", "Knife Hobo", 2, 180),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=100,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        armed = self.service.activate_police_officer_confiscation(
            ActivatePoliceOfficerConfiscationCommand(
                game_id=started.game_id,
                actor_user_id="u_officer",
                expected_version=started.version,
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=armed.game_id,
                murdered_user_id="u_deputy",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                murderer_user_id="u_hobo",
                expected_version=armed.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_chief",
                accused_user_id="u_hobo",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        resolved = after_start_voting
        for juror_user_id in after_start_voting.pending_trial.jury_user_ids:
            resolved = self.service.submit_trial_vote(
                SubmitTrialVoteCommand(
                    game_id=resolved.game_id,
                    voter_user_id=juror_user_id,
                    vote="guilty",
                    expected_version=resolved.version,
                )
            )

        officer = next(participant for participant in resolved.participants if participant.user_id == "u_officer")
        chief = next(participant for participant in resolved.participants if participant.user_id == "u_chief")
        hobo = next(participant for participant in resolved.participants if participant.user_id == "u_hobo")
        self.assertEqual(hobo.life_state, "jailed")
        self.assertEqual(hobo.money_balance, 0)
        self.assertEqual(hobo.inventory, [])
        self.assertTrue(officer.power_state.police_officer_confiscation_used)
        self.assertFalse(officer.power_state.police_officer_confiscation_pending)
        self.assertEqual(officer.money_balance, 460)
        self.assertEqual(chief.money_balance, 570)
        self.assertEqual(resolved.latest_private_notice_user_id, None)
        self.assertTrue(any("confiscated" in event.message.lower() for event in resolved.notification_feed if event.user_id == "u_officer"))
        self.assertTrue(any("share was $270" in event.message for event in resolved.notification_feed if event.user_id == "u_chief"))
        self.assertTrue(any("will not receive" in event.message for event in resolved.notification_feed if event.user_id == "u_chief"))

    def test_police_officer_confiscation_cancels_if_officer_is_no_longer_active(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-confiscation-dead",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_officer", "officer", "Police", "Police Officer", 6, 200),
                    StartSessionParticipantInput("u_hobo", "hobo", "Mob", "Knife Hobo", 2, 180),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[],
            )
        )
        armed = self.service.activate_police_officer_confiscation(
            ActivatePoliceOfficerConfiscationCommand(
                game_id=started.game_id,
                actor_user_id="u_officer",
                expected_version=started.version,
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=armed.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                murderer_user_id="u_hobo",
                expected_version=armed.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_chief",
                accused_user_id="u_hobo",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        first_juror = after_start_voting.pending_trial.jury_user_ids[0]
        after_first_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_start_voting.game_id,
                voter_user_id=first_juror,
                vote="guilty",
                expected_version=after_start_voting.version,
            )
        )
        prepared = replace(
            after_first_vote,
            participants=[
                replace(participant, life_state="dead") if participant.user_id == "u_officer" else participant
                for participant in after_first_vote.participants
            ],
        )
        self.repository.save_game_session(prepared)
        remaining_juror = next(user_id for user_id in prepared.pending_trial.jury_user_ids if user_id != first_juror)
        resolved = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=prepared.game_id,
                voter_user_id=remaining_juror,
                vote="guilty",
                expected_version=prepared.version,
            )
        )

        chief = next(participant for participant in resolved.participants if participant.user_id == "u_chief")
        officer = next(participant for participant in resolved.participants if participant.user_id == "u_officer")
        self.assertTrue(officer.power_state.police_officer_confiscation_used)
        self.assertEqual(chief.money_balance, 780)
        self.assertEqual(chief.inventory[0].classification, "knife")
        self.assertTrue(any("no longer active" in event.message for event in resolved.notification_feed if event.user_id == "u_mod"))

    def test_police_officer_confiscation_triggers_when_merchant_is_found_guilty(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-confiscation-merchant",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 2, 250),
                    StartSessionParticipantInput("u_officer", "officer", "Police", "Police Officer", 6, 200),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 450),
                    StartSessionParticipantInput("u_hobo", "hobo", "Mob", "Knife Hobo", 2, 180),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=100,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        armed = self.service.activate_police_officer_confiscation(
            ActivatePoliceOfficerConfiscationCommand(
                game_id=started.game_id,
                actor_user_id="u_officer",
                expected_version=started.version,
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=armed.game_id,
                murdered_user_id="u_deputy",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                murderer_user_id="u_hobo",
                expected_version=armed.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_chief",
                accused_user_id="u_merchant",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        resolved = after_start_voting
        for juror_user_id in after_start_voting.pending_trial.jury_user_ids:
            resolved = self.service.submit_trial_vote(
                SubmitTrialVoteCommand(
                    game_id=resolved.game_id,
                    voter_user_id=juror_user_id,
                    vote="guilty",
                    expected_version=resolved.version,
                )
            )

        officer = next(participant for participant in resolved.participants if participant.user_id == "u_officer")
        chief = next(participant for participant in resolved.participants if participant.user_id == "u_chief")
        merchant = next(participant for participant in resolved.participants if participant.user_id == "u_merchant")
        mob_boss = next(participant for participant in resolved.participants if participant.user_id == "u_mob")

        self.assertEqual(merchant.life_state, "jailed")
        self.assertEqual(merchant.money_balance, 0)
        self.assertEqual(merchant.inventory, [])
        self.assertTrue(officer.power_state.police_officer_confiscation_used)
        self.assertFalse(officer.power_state.police_officer_confiscation_pending)
        self.assertGreater(officer.money_balance, 200)
        self.assertGreater(chief.money_balance, 300)
        self.assertEqual(mob_boss.money_balance, 300)
        self.assertTrue(any("confiscated" in event.message.lower() for event in resolved.notification_feed if event.user_id == "u_officer"))

    def test_police_officer_confiscation_is_consumed_when_efj_triggers(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-confiscation-efj",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 500),
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_officer", "officer", "Police", "Police Officer", 6, 200),
                    StartSessionParticipantInput("u_accused", "accused", "Mob", "Knife Hobo", 2, 180),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="escape_from_jail",
                        display_name="Escape From Jail",
                        base_price=50,
                        image_path="/static/items/defaults/default_escape_from_jail.svg",
                        is_active=True,
                    )
                ],
            )
        )
        armed = self.service.activate_police_officer_confiscation(
            ActivatePoliceOfficerConfiscationCommand(
                game_id=started.game_id,
                actor_user_id="u_officer",
                expected_version=started.version,
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=armed.game_id,
                buyer_user_id="u_merchant",
                classification="escape_from_jail",
                expected_version=armed.version,
            )
        )
        efj_item_id = next(participant for participant in after_buy.participants if participant.user_id == "u_merchant").inventory[0].item_id
        after_offer = self.service.offer_gift_item(
            OfferGiftItemCommand(
                game_id=after_buy.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_accused",
                inventory_item_id=efj_item_id,
                expected_version=after_buy.version,
            )
        )
        after_accept = self.service.respond_gift_offer(
            RespondGiftOfferCommand(
                game_id=after_offer.game_id,
                receiver_user_id="u_accused",
                gift_offer_id=after_offer.pending_gift_offers[0].gift_offer_id,
                accept=True,
                expected_version=after_offer.version,
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=after_accept.game_id,
                murdered_user_id="u_chief",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                murderer_user_id="u_accused",
                expected_version=after_accept.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_officer",
                accused_user_id="u_accused",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        latest = after_start_voting
        for juror_user_id in after_start_voting.pending_trial.jury_user_ids:
            latest = self.service.submit_trial_vote(
                SubmitTrialVoteCommand(
                    game_id=latest.game_id,
                    voter_user_id=juror_user_id,
                    vote="guilty",
                    expected_version=latest.version,
                )
            )

        officer = next(participant for participant in latest.participants if participant.user_id == "u_officer")
        self.assertTrue(officer.power_state.police_officer_confiscation_used)
        self.assertFalse(officer.power_state.police_officer_confiscation_pending)
        self.assertTrue(any("escaped from jail" in event.message.lower() for event in latest.notification_feed if event.user_id == "u_officer"))

    def test_new_game_starts_with_no_transaction_history_after_previous_game_ended(self) -> None:
        first_game = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-clean-reset",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 3, 200),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 500),
                ],
                catalog=[],
            )
        )
        offered = self.service.give_money(
            GiveMoneyCommand(
                game_id=first_game.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_mob",
                amount=25,
                expected_version=first_game.version,
            )
        )
        accepted = self.service.respond_money_gift_offer(
            RespondMoneyGiftOfferCommand(
                game_id=offered.game_id,
                receiver_user_id="u_mob",
                money_gift_offer_id=offered.pending_money_gift_offers[0].money_gift_offer_id,
                accept=True,
                expected_version=offered.version,
            )
        )
        ended = self.service.kill_game(
            KillGameCommand(
                game_id=accepted.game_id,
                requested_by_user_id="u_mod",
            )
        )
        self.assertEqual(len(ended.player_transactions), 1)

        next_game = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-clean-reset",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=222,
                participants=[
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 3, 200),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 500),
                ],
                catalog=[],
            )
        )

        self.assertNotEqual(first_game.game_id, next_game.game_id)
        self.assertEqual(next_game.room_id, "r-clean-reset")
        self.assertEqual(next_game.player_transactions, [])
        self.assertEqual(next_game.pending_gift_offers, [])
        self.assertEqual(next_game.pending_money_gift_offers, [])
        self.assertEqual(next_game.pending_sale_offers, [])

        investigated = self.service.activate_detective_investigation(
            ActivateDetectiveInvestigationCommand(
                game_id=next_game.game_id,
                actor_user_id="u_detective",
                target_user_id="u_mob",
                expected_version=next_game.version,
            )
        )
        detective = next(participant for participant in investigated.participants if participant.user_id == "u_detective")
        self.assertEqual(detective.power_state.detective_last_viewed_transaction_total, 0)
        self.assertEqual(detective.power_state.detective_last_viewed_transactions, [])

    def test_concurrent_games_in_different_rooms_do_not_share_transaction_history(self) -> None:
        room_a = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-alpha",
                moderator_user_id="u_mod_a",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 3, 200),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 500),
                ],
                catalog=[],
            )
        )
        room_b = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-bravo",
                moderator_user_id="u_mod_b",
                launched_at_epoch_seconds=112,
                participants=[
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 3, 200),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 500),
                ],
                catalog=[],
            )
        )

        room_a_offer = self.service.give_money(
            GiveMoneyCommand(
                game_id=room_a.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_mob",
                amount=30,
                expected_version=room_a.version,
            )
        )
        room_a_accept = self.service.respond_money_gift_offer(
            RespondMoneyGiftOfferCommand(
                game_id=room_a_offer.game_id,
                receiver_user_id="u_mob",
                money_gift_offer_id=room_a_offer.pending_money_gift_offers[0].money_gift_offer_id,
                accept=True,
                expected_version=room_a_offer.version,
            )
        )
        self.assertEqual(len(room_a_accept.player_transactions), 1)

        room_b_investigation = self.service.activate_detective_investigation(
            ActivateDetectiveInvestigationCommand(
                game_id=room_b.game_id,
                actor_user_id="u_detective",
                target_user_id="u_mob",
                expected_version=room_b.version,
            )
        )
        detective_b = next(participant for participant in room_b_investigation.participants if participant.user_id == "u_detective")
        self.assertEqual(detective_b.power_state.detective_last_viewed_transaction_total, 0)
        self.assertEqual(detective_b.power_state.detective_last_viewed_transactions, [])

        room_a_fresh = self.service.get_game_details(room_a_accept.game_id)
        self.assertEqual(len(room_a_fresh.player_transactions), 1)
        self.assertEqual(room_a_fresh.room_id, "r-alpha")
        self.assertEqual(room_b_investigation.room_id, "r-bravo")

    def test_don_can_arm_silence_and_auto_apply_on_next_reported_murder(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-don",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 1, 150),
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 2, 80),
                    StartSessionParticipantInput("u_sergeant", "sergeant", "Police", "Sergeant", 3, 70),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 100),
                    StartSessionParticipantInput("u_don", "don", "Mob", "Don", 2, 60),
                    StartSessionParticipantInput("u_under", "under", "Mob", "Under Boss", 3, 50),
                ],
                catalog=[],
            )
        )

        armed = self.service.activate_don_silence(
            ActivateDonSilenceCommand(
                game_id=started.game_id,
                actor_user_id="u_don",
                target_user_id="u_deputy",
                expected_version=started.version,
            )
        )
        don_after_arm = next(participant for participant in armed.participants if participant.user_id == "u_don")
        self.assertTrue(don_after_arm.power_state.don_silence_used)
        self.assertEqual(don_after_arm.power_state.don_silence_target_user_id, "u_deputy")

        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=armed.game_id,
                murdered_user_id="u_detective",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=armed.version,
            )
        )
        don_after_report = next(participant for participant in after_report.participants if participant.user_id == "u_don")
        self.assertIsNone(don_after_report.power_state.don_silence_target_user_id)
        self.assertIn("u_deputy", after_report.pending_trial.silenced_user_ids)
        self.assertTrue(
            any(
                "seems to be afraid to testify at court" in event.message
                for event in after_report.notification_feed
            )
        )
        self.assertTrue(
            any(
                event.user_id == "u_deputy"
                and event.message == "You seem to be afraid to testify at court. You must remain silent during this trial."
                for event in after_report.notification_feed
            )
        )

        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_deputy",
                accused_user_id="u_mob",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        self.assertIsNotNone(after_start_voting.pending_trial)
        after_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_start_voting.game_id,
                voter_user_id="u_deputy",
                vote="guilty",
                expected_version=after_start_voting.version,
            )
        )
        self.assertTrue(
            any(
                vote.get("user_id") == "u_deputy" and vote.get("vote") == "guilty"
                for vote in after_vote.pending_trial.votes
            )
        )

    def test_underboss_can_replace_juror_once(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-underboss",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 1, 150),
                    StartSessionParticipantInput("u_detective", "detective", "Police", "Detective", 2, 80),
                    StartSessionParticipantInput("u_sergeant", "sergeant", "Police", "Sergeant", 3, 70),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 100),
                    StartSessionParticipantInput("u_don", "don", "Mob", "Don", 2, 60),
                    StartSessionParticipantInput("u_under", "under", "Mob", "Under Boss", 3, 50),
                ],
                catalog=[],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_detective",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_deputy",
                accused_user_id="u_deputy",
                expected_version=after_report.version,
            )
        )

        self.assertNotIn("u_under", after_selection.pending_trial.jury_user_ids)
        removed_juror_user_id = after_selection.pending_trial.jury_user_ids[0]
        updated = self.service.activate_underboss_jury_override(
            ActivateUnderBossJuryOverrideCommand(
                game_id=after_selection.game_id,
                actor_user_id="u_under",
                removed_juror_user_id=removed_juror_user_id,
                expected_version=after_selection.version,
            )
        )

        underboss = next(participant for participant in updated.participants if participant.user_id == "u_under")
        self.assertTrue(underboss.power_state.underboss_jury_override_used)
        self.assertIn("u_under", updated.pending_trial.jury_user_ids)
        self.assertNotIn(removed_juror_user_id, updated.pending_trial.jury_user_ids)

    def test_kingpin_can_start_jury_timer_twice_on_different_trials(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-kingpin",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_police", "police", "Police", "Chief of Police", 1, 240),
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 2, 150),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 100),
                    StartSessionParticipantInput("u_kingpin", "kingpin", "Mob", "Kingpin", 2, 50),
                    StartSessionParticipantInput("u_gangster", "gangster", "Mob", "Gangster", 3, 20),
                ],
                catalog=[],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_deputy",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_police",
                accused_user_id="u_mob",
                expected_version=after_report.version,
            )
        )
        self.now_epoch_seconds = 1200
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        after_first_reduce = self.service.activate_kingpin_reduce_clock(
            ActivateKingpinReduceClockCommand(
                game_id=after_start_voting.game_id,
                actor_user_id="u_kingpin",
                expected_version=after_start_voting.version,
            )
        )

        self.assertEqual(after_first_reduce.pending_trial.vote_deadline_epoch_seconds, 1215)
        kingpin = next(participant for participant in after_first_reduce.participants if participant.user_id == "u_kingpin")
        self.assertEqual(len(kingpin.power_state.kingpin_reduced_trial_keys), 1)

    def test_guilty_correct_accusation_transfers_jailed_inventory_to_police_chief(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-correct",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_chief",
                        username="chief",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_deputy",
                        username="deputy",
                        faction="Police",
                        role_name="Deputy",
                        rank=2,
                        starting_balance=250,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_hobo",
                        username="hobo",
                        faction="Mob",
                        role_name="Knife Hobo",
                        rank=2,
                        starting_balance=180,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mob",
                        username="mob",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=100,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_deputy",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                murderer_user_id="u_hobo",
                expected_version=started.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_chief",
                accused_user_id="u_hobo",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        after_chief_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_start_voting.game_id,
                voter_user_id="u_chief",
                vote="guilty",
                expected_version=after_start_voting.version,
            )
        )
        after_mob_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_chief_vote.game_id,
                voter_user_id="u_mob",
                vote="guilty",
                expected_version=after_chief_vote.version,
            )
        )

        chief = next(participant for participant in after_mob_vote.participants if participant.user_id == "u_chief")
        hobo = next(participant for participant in after_mob_vote.participants if participant.user_id == "u_hobo")
        self.assertEqual(after_mob_vote.phase, "information")
        self.assertEqual(after_mob_vote.pending_trial, None)
        self.assertEqual(hobo.life_state, "jailed")
        self.assertEqual(len(hobo.inventory), 0)
        self.assertEqual(hobo.money_balance, 0)
        self.assertEqual(len(chief.inventory), 1)
        self.assertEqual(chief.inventory[0].classification, "knife")
        self.assertEqual(chief.money_balance, 730)
        self.assertNotIn("received", after_mob_vote.latest_public_notice)
        self.assertEqual(after_mob_vote.latest_private_notice_user_id, "u_chief")
        self.assertEqual(after_mob_vote.latest_private_notice_message, "You received hobo's inventory.")

    def test_guilty_verdict_with_efj_auto_use_returns_accused_to_active_and_records_bribe_transfer(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-efj",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput("u_merchant", "merchant", "Merchant", "Merchant", 1, 500),
                    StartSessionParticipantInput("u_chief", "chief", "Police", "Chief of Police", 1, 300),
                    StartSessionParticipantInput("u_deputy", "deputy", "Police", "Deputy", 2, 250),
                    StartSessionParticipantInput("u_accused", "accused", "Mob", "Knife Hobo", 2, 180),
                    StartSessionParticipantInput("u_mob", "mob", "Mob", "Mob Boss", 1, 300),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="escape_from_jail",
                        display_name="Escape From Jail",
                        base_price=50,
                        image_path="/static/items/defaults/default_escape_from_jail.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="escape_from_jail",
                expected_version=started.version,
            )
        )
        efj_item_id = next(
            participant for participant in after_buy.participants if participant.user_id == "u_merchant"
        ).inventory[0].item_id
        after_offer = self.service.offer_gift_item(
            OfferGiftItemCommand(
                game_id=after_buy.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_accused",
                inventory_item_id=efj_item_id,
                expected_version=after_buy.version,
            )
        )
        after_accept = self.service.respond_gift_offer(
            RespondGiftOfferCommand(
                game_id=after_offer.game_id,
                receiver_user_id="u_accused",
                gift_offer_id=after_offer.pending_gift_offers[0].gift_offer_id,
                accept=True,
                expected_version=after_offer.version,
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=after_accept.game_id,
                murdered_user_id="u_deputy",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                murderer_user_id="u_accused",
                expected_version=after_accept.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_chief",
                accused_user_id="u_accused",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )

        latest = after_start_voting
        for juror_user_id in after_start_voting.pending_trial.jury_user_ids:
            latest = self.service.submit_trial_vote(
                SubmitTrialVoteCommand(
                    game_id=latest.game_id,
                    voter_user_id=juror_user_id,
                    vote="guilty",
                    expected_version=latest.version,
                )
            )

        accused = next(participant for participant in latest.participants if participant.user_id == "u_accused")
        chief = next(participant for participant in latest.participants if participant.user_id == "u_chief")
        self.assertEqual(latest.phase, "information")
        self.assertIsNone(latest.pending_trial)
        self.assertEqual(accused.life_state, "alive")
        self.assertEqual(accused.money_balance, 430)
        self.assertEqual(len(accused.inventory), 1)
        self.assertEqual(accused.inventory[0].classification, "knife")
        self.assertTrue(all(item.classification != "escape_from_jail" for item in accused.inventory))
        self.assertEqual(chief.money_balance, 350)
        self.assertEqual(latest.latest_public_notice, "accused was found guilty.")
        self.assertIsNone(latest.latest_private_notice_user_id)
        self.assertIsNone(latest.latest_private_notice_message)
        self.assertTrue(any(event.user_id == "u_chief" and event.message == "You accepted a bribe." for event in latest.notification_feed))
        self.assertEqual(latest.ledger.entries[-1].entry_kind, "efj_bribe_transfer")
        self.assertEqual(latest.ledger.entries[-1].amount, 50)
        self.assertEqual(latest.ledger.entries[-1].from_holder_id, "central_supply")
        self.assertEqual(latest.ledger.entries[-1].to_holder_id, "u_chief")

    def test_guilty_incorrect_accusation_transfers_jailed_inventory_to_mob_boss(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-incorrect",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_chief",
                        username="chief",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_deputy",
                        username="deputy",
                        faction="Police",
                        role_name="Deputy",
                        rank=2,
                        starting_balance=250,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_hobo",
                        username="hobo",
                        faction="Mob",
                        role_name="Knife Hobo",
                        rank=2,
                        starting_balance=180,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mob",
                        username="mob",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=100,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_deputy",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                murderer_user_id="u_mob",
                expected_version=started.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_chief",
                accused_user_id="u_hobo",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        after_chief_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_start_voting.game_id,
                voter_user_id="u_chief",
                vote="guilty",
                expected_version=after_start_voting.version,
            )
        )
        after_mob_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_chief_vote.game_id,
                voter_user_id="u_mob",
                vote="guilty",
                expected_version=after_chief_vote.version,
            )
        )

        mob_boss = next(participant for participant in after_mob_vote.participants if participant.user_id == "u_mob")
        hobo = next(participant for participant in after_mob_vote.participants if participant.user_id == "u_hobo")
        self.assertEqual(after_mob_vote.phase, "information")
        self.assertEqual(hobo.life_state, "jailed")
        self.assertEqual(len(hobo.inventory), 0)
        self.assertEqual(hobo.money_balance, 0)
        self.assertEqual(len(mob_boss.inventory), 1)
        self.assertEqual(mob_boss.inventory[0].classification, "knife")
        self.assertEqual(mob_boss.money_balance, 730)
        self.assertNotIn("received", after_mob_vote.latest_public_notice)
        self.assertEqual(after_mob_vote.latest_private_notice_user_id, "u_mob")
        self.assertEqual(after_mob_vote.latest_private_notice_message, "You received hobo's inventory.")

    def test_boundary_resolution_without_winner_loops_to_information(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_two_police.json"))
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_chief",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )
        after_selection = self.service.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=after_report.game_id,
                selected_by_user_id="u_deputy",
                accused_user_id="u_mob",
                expected_version=after_report.version,
            )
        )
        after_start_voting = self.service.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=after_selection.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_selection.version,
            )
        )
        after_vote = self.service.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=after_start_voting.game_id,
                voter_user_id="u_deputy",
                vote="innocent",
                expected_version=after_start_voting.version,
            )
        )

        self.assertEqual(after_vote.status, "in_progress")
        self.assertEqual(after_vote.phase, "information")
        self.assertEqual(after_vote.round_number, 2)
        self.assertIsNone(after_vote.pending_trial)
        self.assertEqual(after_vote.latest_public_notice, "mob was found not guilty.")

    def test_boundary_resolution_merchant_win_precedence_over_faction_wipeout(self) -> None:
        command = StartSessionFromRoomCommand(
            room_id="r-merchant",
            moderator_user_id="u_mod",
            launched_at_epoch_seconds=111,
            participants=[
                StartSessionParticipantInput(
                    user_id="u_police",
                    username="police",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                    starting_balance=300,
                ),
                StartSessionParticipantInput(
                    user_id="u_mob",
                    username="mob",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    starting_balance=300,
                ),
                StartSessionParticipantInput(
                    user_id="u_merchant",
                    username="merchant",
                    faction="Merchant",
                    role_name="Merchant",
                    rank=1,
                    starting_balance=1200,
                ),
            ],
            catalog=[],
        )
        started = self.service.start_session_from_room(command)
        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_police",
                reported_by_user_id="u_mod",
                attack_classification="knife",
                expected_version=started.version,
            )
        )

        self.assertEqual(updated.status, "ended")
        self.assertEqual(updated.phase, "ended")
        self.assertEqual(updated.winning_faction, "Merchant")
        self.assertEqual(updated.winning_user_id, "u_merchant")
        self.assertEqual(updated.latest_public_notice, "Game ended. merchant (Merchant) wins.")

    def test_merchant_can_buy_from_supply_and_set_resale_price(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-econ",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mob",
                        username="mob",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )

        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        merchant = next(participant for participant in after_buy.participants if participant.user_id == "u_merchant")
        self.assertEqual(merchant.money_balance, 380)
        self.assertEqual(len(merchant.inventory), 1)
        self.assertEqual(merchant.inventory[0].classification, "knife")
        self.assertEqual(merchant.inventory[0].acquisition_value, 120)
        self.assertEqual(len(after_buy.ledger.entries), 1)
        self.assertEqual(after_buy.ledger.entries[0].entry_kind, "central_supply_purchase")
        self.assertEqual(after_buy.ledger.entries[0].amount, 120)
        knife_catalog = next(item for item in after_buy.catalog if item.classification == "knife")
        self.assertEqual(knife_catalog.base_price, 180)
        self.assertFalse(knife_catalog.is_active)

        after_resale = self.service.set_inventory_resale_price(
            SetInventoryResalePriceCommand(
                game_id=after_buy.game_id,
                seller_user_id="u_merchant",
                inventory_item_id=merchant.inventory[0].item_id,
                resale_price=95,
                expected_version=after_buy.version,
            )
        )
        merchant_after_resale = next(
            participant for participant in after_resale.participants if participant.user_id == "u_merchant"
        )
        self.assertEqual(merchant_after_resale.inventory[0].resale_price, 95)

    def test_non_merchant_can_set_resale_price_and_sell_inventory_item(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-non-merchant-sales",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_hobo",
                        username="hobo",
                        faction="Mob",
                        role_name="Knife Hobo",
                        rank=1,
                        starting_balance=200,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[],
            )
        )

        hobo = next(participant for participant in started.participants if participant.user_id == "u_hobo")
        self.assertEqual(len(hobo.inventory), 1)
        item_id = hobo.inventory[0].item_id

        after_resale = self.service.set_inventory_resale_price(
            SetInventoryResalePriceCommand(
                game_id=started.game_id,
                seller_user_id="u_hobo",
                inventory_item_id=item_id,
                resale_price=57,
                expected_version=started.version,
            )
        )
        hobo_after_resale = next(participant for participant in after_resale.participants if participant.user_id == "u_hobo")
        self.assertEqual(hobo_after_resale.inventory[0].resale_price, 57)

        after_sale_offer = self.service.sell_inventory_item(
            SellInventoryItemCommand(
                game_id=after_resale.game_id,
                seller_user_id="u_hobo",
                buyer_user_id="u_police",
                inventory_item_id=item_id,
                expected_version=after_resale.version,
            )
        )
        self.assertEqual(len(after_sale_offer.pending_sale_offers), 1)
        sale_offer_id = after_sale_offer.pending_sale_offers[0].sale_offer_id

        after_accept = self.service.respond_sale_offer(
            RespondSaleOfferCommand(
                game_id=after_sale_offer.game_id,
                buyer_user_id="u_police",
                sale_offer_id=sale_offer_id,
                accept=True,
                expected_version=after_sale_offer.version,
            )
        )
        hobo_after_sale = next(participant for participant in after_accept.participants if participant.user_id == "u_hobo")
        police_after_sale = next(participant for participant in after_accept.participants if participant.user_id == "u_police")
        self.assertEqual(hobo_after_sale.money_balance, 257)
        self.assertEqual(police_after_sale.money_balance, 243)
        self.assertEqual(len(hobo_after_sale.inventory), 0)
        self.assertEqual(len(police_after_sale.inventory), 1)
        self.assertEqual(police_after_sale.inventory[0].item_id, item_id)

    def test_supply_item_reactivates_when_merchant_sells_item_back_to_supply(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-knife-pricing",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=1000,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=80,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )

        after_first_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        knife_after_first_buy = next(item for item in after_first_buy.catalog if item.classification == "knife")
        self.assertEqual(knife_after_first_buy.base_price, 120)
        self.assertFalse(knife_after_first_buy.is_active)

        merchant = next(participant for participant in after_first_buy.participants if participant.user_id == "u_merchant")
        after_buyback = self.service.sell_inventory_to_supply(
            SellInventoryToSupplyCommand(
                game_id=after_first_buy.game_id,
                seller_user_id="u_merchant",
                inventory_item_id=merchant.inventory[0].item_id,
                expected_version=after_first_buy.version,
            )
        )
        knife_after_buyback = next(item for item in after_buyback.catalog if item.classification == "knife")
        self.assertTrue(knife_after_buyback.is_active)
        self.assertEqual(knife_after_buyback.base_price, 80)

    def test_cannot_buy_supply_item_after_it_has_already_been_purchased(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-single-stock",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=1000,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=80,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_first_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )

        with self.assertRaises(ValueError):
            self.service.buy_from_supply(
                BuyFromSupplyCommand(
                    game_id=after_first_buy.game_id,
                    buyer_user_id="u_merchant",
                    classification="knife",
                    expected_version=after_first_buy.version,
                )
            )

    def test_non_merchant_cannot_buy_from_supply(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-econ2",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mob",
                        username="mob",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )

        with self.assertRaises(PermissionError):
            self.service.buy_from_supply(
                BuyFromSupplyCommand(
                    game_id=started.game_id,
                    buyer_user_id="u_police",
                    classification="knife",
                    expected_version=started.version,
                )
            )

    def test_start_session_gives_knife_hobo_starting_knife_inventory(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-knife-hobo",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_hobo",
                        username="hobo",
                        faction="Mob",
                        role_name="Knife Hobo",
                        rank=1,
                        starting_balance=180,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )

        knife_hobo = next(participant for participant in started.participants if participant.user_id == "u_hobo")
        self.assertEqual(len(knife_hobo.inventory), 1)
        self.assertEqual(knife_hobo.inventory[0].classification, "knife")
        self.assertEqual(knife_hobo.inventory[0].display_name, "Knife")

    def test_merchant_sale_requires_buyer_acceptance_to_transfer_money_and_item(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-sale",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mob",
                        username="mob",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        merchant = next(participant for participant in after_buy.participants if participant.user_id == "u_merchant")
        inventory_item_id = merchant.inventory[0].item_id
        after_price = self.service.set_inventory_resale_price(
            SetInventoryResalePriceCommand(
                game_id=after_buy.game_id,
                seller_user_id="u_merchant",
                inventory_item_id=inventory_item_id,
                resale_price=200,
                expected_version=after_buy.version,
            )
        )

        after_sale_offer = self.service.sell_inventory_item(
            SellInventoryItemCommand(
                game_id=after_price.game_id,
                seller_user_id="u_merchant",
                buyer_user_id="u_police",
                inventory_item_id=inventory_item_id,
                expected_version=after_price.version,
            )
        )
        self.assertEqual(len(after_sale_offer.pending_sale_offers), 1)

        after_sale_accept = self.service.respond_sale_offer(
            RespondSaleOfferCommand(
                game_id=after_sale_offer.game_id,
                buyer_user_id="u_police",
                sale_offer_id=after_sale_offer.pending_sale_offers[0].sale_offer_id,
                accept=True,
                expected_version=after_sale_offer.version,
            )
        )
        merchant_after_sale = next(participant for participant in after_sale_accept.participants if participant.user_id == "u_merchant")
        buyer_after_sale = next(participant for participant in after_sale_accept.participants if participant.user_id == "u_police")
        self.assertEqual(merchant_after_sale.money_balance, 580)
        self.assertEqual(buyer_after_sale.money_balance, 100)
        self.assertEqual(len(merchant_after_sale.inventory), 0)
        self.assertEqual(len(buyer_after_sale.inventory), 1)
        self.assertEqual(buyer_after_sale.inventory[0].item_id, inventory_item_id)
        self.assertEqual(len(after_sale_accept.pending_sale_offers), 0)

    def test_merchant_can_send_sale_offer_without_disclosing_buyer_funds(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-sale-hidden-funds",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=100,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        inventory_item_id = next(participant for participant in after_buy.participants if participant.user_id == "u_merchant").inventory[0].item_id
        after_price = self.service.set_inventory_resale_price(
            SetInventoryResalePriceCommand(
                game_id=after_buy.game_id,
                seller_user_id="u_merchant",
                inventory_item_id=inventory_item_id,
                resale_price=200,
                expected_version=after_buy.version,
            )
        )

        offered = self.service.sell_inventory_item(
            SellInventoryItemCommand(
                game_id=after_price.game_id,
                seller_user_id="u_merchant",
                buyer_user_id="u_police",
                inventory_item_id=inventory_item_id,
                expected_version=after_price.version,
            )
        )
        self.assertEqual(len(offered.pending_sale_offers), 1)

    def test_merchant_can_sell_item_to_supply_for_full_acquisition_value(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-supply-buyback",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        merchant_after_buy = next(participant for participant in after_buy.participants if participant.user_id == "u_merchant")
        inventory_item_id = merchant_after_buy.inventory[0].item_id
        self.assertEqual(merchant_after_buy.money_balance, 380)

        after_sell = self.service.sell_inventory_to_supply(
            SellInventoryToSupplyCommand(
                game_id=after_buy.game_id,
                seller_user_id="u_merchant",
                inventory_item_id=inventory_item_id,
                expected_version=after_buy.version,
            )
        )
        merchant_after_sell = next(participant for participant in after_sell.participants if participant.user_id == "u_merchant")
        self.assertEqual(merchant_after_sell.money_balance, 500)
        self.assertEqual(len(merchant_after_sell.inventory), 0)

    def test_merchant_wins_immediately_when_money_gift_reaches_goal(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-merchant-goal",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=640,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mob",
                        username="mob",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[],
            )
        )

        offered = self.service.give_money(
            GiveMoneyCommand(
                game_id=started.game_id,
                giver_user_id="u_police",
                receiver_user_id="u_merchant",
                amount=100,
                expected_version=started.version,
            )
        )
        accepted = self.service.respond_money_gift_offer(
            RespondMoneyGiftOfferCommand(
                game_id=offered.game_id,
                receiver_user_id="u_merchant",
                money_gift_offer_id=offered.pending_money_gift_offers[0].money_gift_offer_id,
                accept=True,
                expected_version=offered.version,
            )
        )

        self.assertEqual(accepted.status, "ended")
        self.assertEqual(accepted.phase, "ended")
        self.assertEqual(accepted.winning_faction, "Merchant")
        self.assertEqual(accepted.winning_user_id, "u_merchant")
        self.assertEqual(accepted.latest_public_notice, "Game ended. merchant (Merchant) wins.")

    def test_kill_game_ends_session_and_syncs_room_lifecycle(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        killed = self.service.kill_game(
            KillGameCommand(
                game_id=started.game_id,
                requested_by_user_id="u_mod",
            )
        )

        self.assertEqual(killed.status, "ended")
        self.assertEqual(killed.phase, "ended")
        self.assertEqual(killed.latest_public_notice, "Game ended by moderator.")
        self.assertEqual(self.room_lifecycle.calls, [("r-2", started.game_id)])

    def test_gift_offer_accept_transfers_item_without_payment(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-gift",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mob",
                        username="mob",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        giver = next(participant for participant in after_buy.participants if participant.user_id == "u_merchant")
        gift_item_id = giver.inventory[0].item_id
        after_offer = self.service.offer_gift_item(
            OfferGiftItemCommand(
                game_id=after_buy.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_police",
                inventory_item_id=gift_item_id,
                expected_version=after_buy.version,
            )
        )
        self.assertEqual(len(after_offer.pending_gift_offers), 1)
        offer_id = after_offer.pending_gift_offers[0].gift_offer_id

        after_accept = self.service.respond_gift_offer(
            RespondGiftOfferCommand(
                game_id=after_offer.game_id,
                receiver_user_id="u_police",
                gift_offer_id=offer_id,
                accept=True,
                expected_version=after_offer.version,
            )
        )
        giver_after = next(participant for participant in after_accept.participants if participant.user_id == "u_merchant")
        receiver_after = next(participant for participant in after_accept.participants if participant.user_id == "u_police")
        self.assertEqual(len(giver_after.inventory), 0)
        self.assertEqual(len(receiver_after.inventory), 1)
        self.assertEqual(giver_after.money_balance, 380)
        self.assertEqual(receiver_after.money_balance, 300)
        self.assertEqual(len(after_accept.pending_gift_offers), 0)

    def test_sale_offer_decline_keeps_item_with_seller(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-sale-decline",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        inventory_item_id = next(participant for participant in after_buy.participants if participant.user_id == "u_merchant").inventory[0].item_id
        after_sale_offer = self.service.sell_inventory_item(
            SellInventoryItemCommand(
                game_id=after_buy.game_id,
                seller_user_id="u_merchant",
                buyer_user_id="u_police",
                inventory_item_id=inventory_item_id,
                expected_version=after_buy.version,
            )
        )

        after_decline = self.service.respond_sale_offer(
            RespondSaleOfferCommand(
                game_id=after_sale_offer.game_id,
                buyer_user_id="u_police",
                sale_offer_id=after_sale_offer.pending_sale_offers[0].sale_offer_id,
                accept=False,
                expected_version=after_sale_offer.version,
            )
        )
        seller_after = next(participant for participant in after_decline.participants if participant.user_id == "u_merchant")
        buyer_after = next(participant for participant in after_decline.participants if participant.user_id == "u_police")
        self.assertEqual(len(seller_after.inventory), 1)
        self.assertEqual(len(buyer_after.inventory), 0)
        self.assertEqual(seller_after.money_balance, 380)
        self.assertEqual(buyer_after.money_balance, 300)
        self.assertEqual(len(after_decline.pending_sale_offers), 0)
        self.assertIsNone(after_decline.latest_public_notice)
        decline_notifications = [event for event in after_decline.notification_feed if "declined merchant's sale offer for Knife." in event.message]
        self.assertEqual({event.user_id for event in decline_notifications}, {"u_merchant", "u_police", "u_mod"})

    def test_sale_offer_accept_with_insufficient_funds_notifies_buyer_and_records_decline_notice(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-sale-insufficient",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=100,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        inventory_item_id = next(participant for participant in after_buy.participants if participant.user_id == "u_merchant").inventory[0].item_id
        after_price = self.service.set_inventory_resale_price(
            SetInventoryResalePriceCommand(
                game_id=after_buy.game_id,
                seller_user_id="u_merchant",
                inventory_item_id=inventory_item_id,
                resale_price=200,
                expected_version=after_buy.version,
            )
        )
        after_sale_offer = self.service.sell_inventory_item(
            SellInventoryItemCommand(
                game_id=after_price.game_id,
                seller_user_id="u_merchant",
                buyer_user_id="u_police",
                inventory_item_id=inventory_item_id,
                expected_version=after_price.version,
            )
        )
        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.respond_sale_offer(
                RespondSaleOfferCommand(
                    game_id=after_sale_offer.game_id,
                    buyer_user_id="u_police",
                    sale_offer_id=after_sale_offer.pending_sale_offers[0].sale_offer_id,
                    accept=True,
                    expected_version=after_sale_offer.version,
                )
            )
        self.assertEqual(exc_ctx.exception.code, "invalid_state")
        self.assertEqual(str(exc_ctx.exception), "Buyer has insufficient funds for this purchase.")

        latest = self.service.get_game_details(after_sale_offer.game_id)
        seller_after = next(participant for participant in latest.participants if participant.user_id == "u_merchant")
        buyer_after = next(participant for participant in latest.participants if participant.user_id == "u_police")
        self.assertEqual(len(latest.pending_sale_offers), 0)
        self.assertEqual(len(seller_after.inventory), 1)
        self.assertEqual(len(buyer_after.inventory), 0)
        self.assertIsNone(latest.latest_public_notice)
        decline_notifications = [event for event in latest.notification_feed if event.message == "police declined merchant's sale offer for Knife."]
        self.assertEqual({event.user_id for event in decline_notifications}, {"u_merchant", "u_police", "u_mod"})

    def test_gift_offer_decline_keeps_item_with_giver(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-gift-2",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        giver = next(participant for participant in after_buy.participants if participant.user_id == "u_merchant")
        gift_item_id = giver.inventory[0].item_id
        after_offer = self.service.offer_gift_item(
            OfferGiftItemCommand(
                game_id=after_buy.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_police",
                inventory_item_id=gift_item_id,
                expected_version=after_buy.version,
            )
        )

        after_decline = self.service.respond_gift_offer(
            RespondGiftOfferCommand(
                game_id=after_offer.game_id,
                receiver_user_id="u_police",
                gift_offer_id=after_offer.pending_gift_offers[0].gift_offer_id,
                accept=False,
                expected_version=after_offer.version,
            )
        )
        giver_after = next(participant for participant in after_decline.participants if participant.user_id == "u_merchant")
        receiver_after = next(participant for participant in after_decline.participants if participant.user_id == "u_police")
        self.assertEqual(len(giver_after.inventory), 1)
        self.assertEqual(len(receiver_after.inventory), 0)
        self.assertEqual(len(after_decline.pending_gift_offers), 0)
        decline_notifications = [event for event in after_decline.notification_feed if "declined merchant's gift offer for Knife." in event.message]
        self.assertEqual({event.user_id for event in decline_notifications}, {"u_merchant", "u_police", "u_mod"})

    def test_respond_gift_offer_is_blocked_outside_information_phase(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-gift-phase-lock",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        gift_item_id = next(
            participant for participant in after_buy.participants if participant.user_id == "u_merchant"
        ).inventory[0].item_id
        after_offer = self.service.offer_gift_item(
            OfferGiftItemCommand(
                game_id=after_buy.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_police",
                inventory_item_id=gift_item_id,
                expected_version=after_buy.version,
            )
        )
        trial_locked = replace(after_offer, phase="trial_voting", version=after_offer.version + 1)
        self.repository.save_game_session(trial_locked)

        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.respond_gift_offer(
                RespondGiftOfferCommand(
                    game_id=after_offer.game_id,
                    receiver_user_id="u_police",
                    gift_offer_id=after_offer.pending_gift_offers[0].gift_offer_id,
                    accept=True,
                    expected_version=trial_locked.version,
                )
            )
        self.assertEqual(exc_ctx.exception.code, "invalid_state")
        self.assertEqual(str(exc_ctx.exception), "Cannot respond to gift offers outside information phase.")

    def test_give_money_offer_accept_transfers_balance_between_alive_players(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        offered = self.service.give_money(
            GiveMoneyCommand(
                game_id=started.game_id,
                giver_user_id="u_police",
                receiver_user_id="u_mob",
                amount=50,
                expected_version=started.version,
            )
        )
        self.assertEqual(len(offered.pending_money_gift_offers), 1)
        offer_id = offered.pending_money_gift_offers[0].money_gift_offer_id
        before_accept_giver = next(participant for participant in offered.participants if participant.user_id == "u_police")
        before_accept_receiver = next(participant for participant in offered.participants if participant.user_id == "u_mob")
        self.assertEqual(before_accept_giver.money_balance, 300)
        self.assertEqual(before_accept_receiver.money_balance, 300)

        after_transfer = self.service.respond_money_gift_offer(
            RespondMoneyGiftOfferCommand(
                game_id=offered.game_id,
                receiver_user_id="u_mob",
                money_gift_offer_id=offer_id,
                accept=True,
                expected_version=offered.version,
            )
        )
        giver = next(participant for participant in after_transfer.participants if participant.user_id == "u_police")
        receiver = next(participant for participant in after_transfer.participants if participant.user_id == "u_mob")
        self.assertEqual(giver.money_balance, 250)
        self.assertEqual(receiver.money_balance, 350)
        self.assertEqual(len(after_transfer.pending_money_gift_offers), 0)
        self.assertEqual(after_transfer.ledger.entries[-1].entry_kind, "money_gift")
        self.assertEqual(after_transfer.ledger.entries[-1].amount, 50)
        self.assertEqual(after_transfer.ledger.entries[-1].from_holder_id, "u_police")
        self.assertEqual(after_transfer.ledger.entries[-1].to_holder_id, "u_mob")

    def test_give_money_rejects_insufficient_funds(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.give_money(
                GiveMoneyCommand(
                    game_id=started.game_id,
                    giver_user_id="u_police",
                    receiver_user_id="u_mob",
                    amount=9999,
                    expected_version=started.version,
                )
            )
        self.assertEqual(exc_ctx.exception.code, "invalid_state")
        self.assertEqual(str(exc_ctx.exception), "Giver has insufficient funds.")

    def test_moderator_can_add_funds_to_participant(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        updated = self.service.moderator_add_funds(
            ModeratorAddFundsCommand(
                game_id=started.game_id,
                requested_by_user_id="u_mod",
                recipient_user_id="u_mob",
                amount=70,
                expected_version=started.version,
            )
        )

        recipient = next(participant for participant in updated.participants if participant.user_id == "u_mob")
        self.assertEqual(recipient.money_balance, 370)
        self.assertEqual(updated.ledger.entries[-1].entry_kind, "moderator_adjustment")
        self.assertEqual(updated.ledger.entries[-1].from_holder_id, "central_supply")
        self.assertEqual(updated.ledger.entries[-1].to_holder_id, "u_mob")
        self.assertEqual(updated.ledger.entries[-1].amount, 70)

    def test_moderator_can_transfer_funds_between_participants(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        updated = self.service.moderator_transfer_funds(
            ModeratorTransferFundsCommand(
                game_id=started.game_id,
                requested_by_user_id="u_mod",
                from_user_id="u_police",
                to_user_id="u_mob",
                amount=60,
                expected_version=started.version,
            )
        )

        source = next(participant for participant in updated.participants if participant.user_id == "u_police")
        recipient = next(participant for participant in updated.participants if participant.user_id == "u_mob")
        self.assertEqual(source.money_balance, 240)
        self.assertEqual(recipient.money_balance, 360)
        self.assertEqual(updated.ledger.entries[-1].entry_kind, "moderator_adjustment")
        self.assertEqual(updated.ledger.entries[-1].from_holder_id, "u_police")
        self.assertEqual(updated.ledger.entries[-1].to_holder_id, "u_mob")
        self.assertEqual(updated.ledger.entries[-1].amount, 60)

    def test_moderator_item_transfer_moves_item_and_clears_pending_item_offer(self) -> None:
        started = self.service.start_session_from_room(
            StartSessionFromRoomCommand(
                room_id="r-moderator-item-transfer",
                moderator_user_id="u_mod",
                launched_at_epoch_seconds=111,
                participants=[
                    StartSessionParticipantInput(
                        user_id="u_merchant",
                        username="merchant",
                        faction="Merchant",
                        role_name="Merchant",
                        rank=1,
                        starting_balance=500,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_police",
                        username="police",
                        faction="Police",
                        role_name="Chief of Police",
                        rank=1,
                        starting_balance=300,
                    ),
                    StartSessionParticipantInput(
                        user_id="u_mob",
                        username="mob",
                        faction="Mob",
                        role_name="Mob Boss",
                        rank=1,
                        starting_balance=300,
                    ),
                ],
                catalog=[
                    StartSessionCatalogItemInput(
                        classification="knife",
                        display_name="Knife",
                        base_price=120,
                        image_path="/static/items/defaults/default_knife.svg",
                        is_active=True,
                    )
                ],
            )
        )
        after_buy = self.service.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=started.game_id,
                buyer_user_id="u_merchant",
                classification="knife",
                expected_version=started.version,
            )
        )
        inventory_item_id = next(
            participant for participant in after_buy.participants if participant.user_id == "u_merchant"
        ).inventory[0].item_id
        after_offer = self.service.offer_gift_item(
            OfferGiftItemCommand(
                game_id=after_buy.game_id,
                giver_user_id="u_merchant",
                receiver_user_id="u_police",
                inventory_item_id=inventory_item_id,
                expected_version=after_buy.version,
            )
        )

        updated = self.service.moderator_transfer_inventory_item(
            ModeratorTransferInventoryItemCommand(
                game_id=after_offer.game_id,
                requested_by_user_id="u_mod",
                from_user_id="u_merchant",
                to_user_id="u_mob",
                inventory_item_id=inventory_item_id,
                expected_version=after_offer.version,
            )
        )

        giver = next(participant for participant in updated.participants if participant.user_id == "u_merchant")
        receiver = next(participant for participant in updated.participants if participant.user_id == "u_mob")
        self.assertEqual(len(giver.inventory), 0)
        self.assertEqual(len(receiver.inventory), 1)
        self.assertEqual(receiver.inventory[0].item_id, inventory_item_id)
        self.assertEqual(len(updated.pending_gift_offers), 0)


if __name__ == "__main__":
    unittest.main()
