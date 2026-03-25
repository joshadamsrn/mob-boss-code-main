"""Gameplay use-case service.

Authoritative invariants for this slice:
- one-trial-per-murder: `report_death` is blocked while any active trial is pending.
- boundary checks decide whether game ends or loops back to information phase.
- role-leak safety: this service stores full internal truth; visibility filtering is
  enforced in the API/web projection layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields
from dataclasses import replace
import hashlib
import random
import time
from typing import cast
from uuid import uuid4

from project.mobboss_apps.gameplay.ports.inbound import GameplayInboundPort
from project.mobboss_apps.gameplay.ports.internal import (
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
    GiftOfferSnapshot,
    KillGameCommand,
    AllowTrialVotingCommand,
    AdvanceAccusedSelectionTimeoutCommand,
    CatalogItemStateSnapshot,
    GameDetailsSnapshot,
    GamePhase,
    InventoryItemStateSnapshot,
    LedgerEntrySnapshot,
    LedgerStateSnapshot,
    MoneyGiftOfferSnapshot,
    NotificationEventSnapshot,
    ParticipantStateSnapshot,
    ParticipantPowerStateSnapshot,
    PlayerTransactionSnapshot,
    OfferGiftItemCommand,
    ReportDeathCommand,
    RespondGiftOfferCommand,
    RespondMoneyGiftOfferCommand,
    RespondSaleOfferCommand,
    SaleOfferSnapshot,
    SellInventoryItemCommand,
    SellInventoryToSupplyCommand,
    SetInventoryResalePriceCommand,
    StartSessionFromRoomCommand,
    SubmitAccusedSelectionCommand,
    SubmitTrialVoteCommand,
    TrialStateSnapshot,
)
from project.mobboss_apps.gameplay.ports.outbound import GameplayOutboundPort
from project.mobboss_apps.gameplay.ports.room_lifecycle_outbound import (
    GameplayRoomLifecycleOutboundPort,
)
from project.mobboss_apps.mobboss.src.starting_money import getStartingMoney
from project.mobboss_apps.mobboss.src.weights import DEFAULT_WEIGHTS
from project.mobboss_apps.mobboss.exceptions import ConflictProblem

ACCUSED_SELECTION_TIMEOUT_SECONDS = 15
TRIAL_VOTING_TIMEOUT_SECONDS = 10
KINGPIN_VOTE_CLOCK_REDUCTION_SECONDS = 5
GANGSTER_TAMPER_VOTE_TIMEOUT_SECONDS = 10
PROTECTIVE_CUSTODY_DURATION_SECONDS = 300
SHERIFF_JURY_LOG_VISIBLE_SECONDS = 60
CAPTAIN_ASSET_FREEZE_SECONDS = 600
LIEUTENANT_BRIEFCASE_VISIBLE_SECONDS = 60
SERGEANT_CAPTURE_SECONDS = 300
DETECTIVE_INVESTIGATION_VISIBLE_SECONDS = 60
INSPECTOR_RECORD_VISIBLE_SECONDS = 60
FELON_ESCAPE_SECONDS = 1800
GUN_RUNNER_CHARISMA_SECONDS = 180
MERCHANT_GOAL_ADDITIONAL_PERCENT = 0.40
SUPPLY_BUYBACK_PERCENT = 1.00
CENTRAL_SUPPLY_HOLDER_ID = "central_supply"
_GUN_ATTACK_CLASSIFICATIONS = {"gun_tier_1", "gun_tier_2", "gun_tier_3"}
COP_LAST_THREE_THRESHOLD = 3
MERCHANT_WHOLESALE_DISCOUNT_PERCENT = 30
GUN_RUNNER_CHARISMA_BONUS_PERCENT = 30
SUPPLIER_ACQUIRE_STEAL_PERCENT = 50
SUPPLIER_ACQUIRE_VALID_TARGET_ROLES = {"Merchant", "Arms Dealer", "Smuggler", "Gun Runner"}
INACTIVITY_AUTO_END_SECONDS = 24 * 60 * 60


class GameplayService(GameplayInboundPort):
    def __init__(
        self,
        repository: GameplayOutboundPort,
        *,
        now_epoch_seconds_provider=None,
        room_lifecycle_outbound_port: GameplayRoomLifecycleOutboundPort | None = None,
        efj_bribe_recipient_selector=None,
        smuggler_item_selector=None,
    ) -> None:
        self._repository = repository
        self._now_epoch_seconds_provider = now_epoch_seconds_provider or (lambda: int(time.time()))
        self._room_lifecycle_outbound_port = room_lifecycle_outbound_port
        self._efj_bribe_recipient_selector = efj_bribe_recipient_selector or random.choice
        self._smuggler_item_selector = smuggler_item_selector or random.choice

    def start_session_from_room(self, command: StartSessionFromRoomCommand) -> GameDetailsSnapshot:
        if not command.participants:
            raise ValueError("Cannot start game session without participants.")

        game_id = self._repository.reserve_game_id(command.room_id)
        catalog = [
            CatalogItemStateSnapshot(
                classification=item.classification,
                display_name=item.display_name,
                base_price=item.base_price,
                image_path=item.image_path,
                is_active=item.is_active,
            )
            for item in command.catalog
        ]
        participants: list[ParticipantStateSnapshot] = []
        startup_notifications: list[tuple[str, str]] = []
        for participant in command.participants:
            inventory, catalog, notifications = _build_role_starting_loadout(
                role_name=participant.role_name,
                catalog=catalog,
                username=participant.username,
                user_id=participant.user_id,
            )
            participants.append(
                ParticipantStateSnapshot(
                    user_id=participant.user_id,
                    username=participant.username,
                    faction=participant.faction,
                    role_name=participant.role_name,
                    rank=participant.rank,
                    life_state="alive",
                    money_balance=participant.starting_balance,
                    inventory=inventory,
                )
            )
            startup_notifications.extend(notifications)

        session = GameDetailsSnapshot(
            game_id=game_id,
            room_id=command.room_id,
            moderator_user_id=command.moderator_user_id,
            status="in_progress",
            phase="information",
            round_number=1,
            version=1,
            launched_at_epoch_seconds=command.launched_at_epoch_seconds,
            ended_at_epoch_seconds=None,
            participants=participants,
            catalog=catalog,
            pending_trial=None,
            last_progressed_at_epoch_seconds=command.launched_at_epoch_seconds,
            ledger=LedgerStateSnapshot(
                circulating_currency_baseline=sum(participant.money_balance for participant in participants),
            ),
            current_police_leader_user_id=_find_faction_leader_user_id(participants, faction="Police"),
            current_mob_leader_user_id=_find_faction_leader_user_id(participants, faction="Mob"),
            player_transactions=[],
            pending_gift_offers=[],
            pending_money_gift_offers=[],
            pending_sale_offers=[],
            total_mob_participants_at_start=sum(1 for participant in participants if participant.faction == "Mob"),
            police_mob_kills_count=0,
            notification_feed=_append_notifications(
                [],
                startup_notifications,
                now_epoch_seconds=command.launched_at_epoch_seconds,
            ),
        )
        session = _refresh_ledger(session)
        self._repository.save_game_session(session)
        return session

    def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
        session = self._repository.get_game_session(game_id)
        if session is None:
            raise ValueError("Game session not found.")
        now_epoch_seconds = self._now_epoch_seconds()
        session = self._resolve_felon_escape_if_needed(session, now_epoch_seconds=now_epoch_seconds)
        session = self._cancel_gangster_tamper_if_needed(session, now_epoch_seconds=now_epoch_seconds)
        session = self._resolve_trial_voting_if_deadline_elapsed(session, now_epoch_seconds=now_epoch_seconds)
        session = self._auto_end_if_inactive(session, now_epoch_seconds=now_epoch_seconds)
        return session

    def report_death(self, command: ReportDeathCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        is_moderator_report = command.reported_by_user_id == session.moderator_user_id
        is_self_report = command.reported_by_user_id == command.murdered_user_id
        if not is_moderator_report and not is_self_report:
            raise PermissionError("Only moderator or the murdered player can report this death.")
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.status != "in_progress":
            raise ConflictProblem("Cannot report death outside in-progress game.", code="invalid_state")
        # Invariant: one murder can only drive one trial at a time.
        if _has_active_trial(session.pending_trial):
            raise ConflictProblem("Cannot report death while a trial is pending.", code="invalid_state")
        if command.reported_by_user_id != session.moderator_user_id:
            _raise_if_sergeant_captured(
                session,
                user_id=command.reported_by_user_id,
                now_epoch_seconds=now_epoch_seconds,
            )
        captured_target_user_id = _active_sergeant_capture_target_user_id(session, now_epoch_seconds=now_epoch_seconds)
        if captured_target_user_id == command.murdered_user_id:
            raise ConflictProblem("Captured player cannot be targeted during police custody.", code="invalid_state")
        protected_target_user_id = _active_protective_custody_target_user_id(
            session,
            now_epoch_seconds=now_epoch_seconds,
        )

        participant_exists = False
        updated_participants: list[ParticipantStateSnapshot] = []
        murdered_participant: ParticipantStateSnapshot | None = None
        for participant in session.participants:
            if participant.user_id == command.murdered_user_id:
                participant_exists = True
                if participant.life_state != "alive":
                    raise ValueError("Reported participant is not alive.")
                murdered_participant = participant
                continue
            updated_participants.append(participant)

        if not participant_exists:
            raise ValueError("Murdered participant not found in session.")
        if murdered_participant is None:
            raise ValueError("Murdered participant not found in session.")

        murderer_user_id = command.murderer_user_id
        if is_self_report and not murderer_user_id:
            raise ValueError("Murderer must be selected when a player reports their own death.")

        murderer_participant: ParticipantStateSnapshot | None = None
        if murderer_user_id:
            if murderer_user_id == command.murdered_user_id:
                raise ValueError("Murderer cannot be the murdered player.")
            murderer_participant = next((p for p in session.participants if p.user_id == murderer_user_id), None)
            if murderer_participant is None:
                raise ValueError("Murderer participant not found in session.")
            if murderer_participant.life_state != "alive":
                raise ValueError("Murderer must be an active player.")

        vest_inventory_item = _find_inventory_item(
            session.participants,
            user_id=command.murdered_user_id,
            classification="bulletproof_vest",
        )
        attack_display_name = _attack_display_name(session.catalog, command.attack_classification)
        if vest_inventory_item is not None and _is_gun_attack_classification(command.attack_classification):
            if murderer_participant is None:
                raise ValueError("Murderer must be selected when reporting a vest-blocked gunshot.")

            next_participants = _remove_inventory_item_from_participant(
                session.participants,
                user_id=command.murdered_user_id,
                inventory_item_id=vest_inventory_item.item_id,
            )
            next_participants = _adjust_participant_money_balance(
                next_participants,
                user_id=murderer_participant.user_id,
                delta=vest_inventory_item.acquisition_value,
            )
            updated = replace(
                session,
                participants=next_participants,
                latest_public_notice=(
                    f"{murdered_participant.username.upper()} SURVIVED A {attack_display_name.upper()} SHOT USING A BULLETPROOF VEST"
                ),
                latest_private_notice_user_id=None,
                latest_private_notice_message=None,
                version=session.version + 1,
            )
            updated = _append_ledger_entries(
                updated,
                [
                    _build_ledger_entry(
                        entry_kind="vest_block_transfer",
                        amount=vest_inventory_item.acquisition_value,
                        from_holder_id=CENTRAL_SUPPLY_HOLDER_ID,
                        to_holder_id=murderer_participant.user_id,
                        now_epoch_seconds=now_epoch_seconds,
                        note="Vest block transfer.",
                    )
                ],
            )
            updated = self._resolve_information_winner_if_needed(updated, now_epoch_seconds=now_epoch_seconds)
            self._save_game_session(session, updated)
            return updated

        if protected_target_user_id == command.murdered_user_id:
            unavailable_user_ids = {captured_target_user_id} if captured_target_user_id else set()
            next_police_leader_user_id = _resolve_next_leader_user_id(
                session.participants,
                faction="Police",
                current_leader_user_id=session.current_police_leader_user_id,
                unavailable_user_ids=unavailable_user_ids,
            )
            next_mob_leader_user_id = _resolve_next_leader_user_id(
                session.participants,
                faction="Mob",
                current_leader_user_id=session.current_mob_leader_user_id,
                unavailable_user_ids=unavailable_user_ids,
            )
            accused_selection_cursor = [next_police_leader_user_id] if next_police_leader_user_id else []
            silenced_user_ids, post_trial_participants, post_trial_notification_feed = _apply_armed_don_silence_for_upcoming_trial(
                session.participants,
                accused_selection_cursor=accused_selection_cursor,
                moderator_user_id=session.moderator_user_id,
                notification_feed=session.notification_feed,
                now_epoch_seconds=now_epoch_seconds,
            )
            pending_trial = TrialStateSnapshot(
                murdered_user_id=command.murdered_user_id,
                murderer_user_id=murderer_user_id,
                accused_user_id=None,
                accused_selection_cursor=accused_selection_cursor,
                accused_selection_deadline_epoch_seconds=(
                    now_epoch_seconds + ACCUSED_SELECTION_TIMEOUT_SECONDS if accused_selection_cursor else None
                ),
                jury_user_ids=[],
                vote_deadline_epoch_seconds=None,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution=None if accused_selection_cursor else "no_conviction",
                accused_by_user_id=None,
                silenced_user_ids=silenced_user_ids,
            )
            next_phase = cast(GamePhase, "accused_selection" if accused_selection_cursor else "boundary_resolution")
            updated = replace(
                session,
                participants=post_trial_participants,
                pending_trial=pending_trial,
                phase=next_phase,
                current_police_leader_user_id=next_police_leader_user_id,
                current_mob_leader_user_id=next_mob_leader_user_id,
                latest_public_notice=(
                    f"ATTEMPTED MURDER ON {murdered_participant.username.upper()} WITH {attack_display_name.upper()} - REPORT IMMEDIATELY TO COURT HOUSE"
                ),
                latest_private_notice_user_id=command.murdered_user_id,
                latest_private_notice_message=(
                    "The murder attempt failed because you were under protective custody."
                ),
                notification_feed=post_trial_notification_feed,
                pending_gift_offers=[],
                pending_money_gift_offers=[],
                pending_sale_offers=[],
                version=session.version + 1,
            )
            updated = self._resolve_boundary_if_needed(updated, now_epoch_seconds=now_epoch_seconds)
            self._save_game_session(session, updated)
            return updated

        police_mob_kill_increment = 1 if (
            murderer_participant is not None
            and murderer_participant.faction == "Police"
            and murdered_participant.faction == "Mob"
        ) else 0
        next_participants = list(updated_participants)
        next_participants.append(
            replace(
                murdered_participant,
                life_state="dead",
                inventory=list(murdered_participant.inventory),
                money_balance=murdered_participant.money_balance,
                murdered_by_user_id=murderer_user_id,
            )
        )
        ledger_entries: list[LedgerEntrySnapshot] = []
        next_notification_feed = session.notification_feed
        if murderer_participant is not None:
            next_participants = _transfer_inventory_between_participants(
                next_participants,
                from_user_id=command.murdered_user_id,
                to_user_id=murderer_participant.user_id,
            )
            transfer_amount = max(murdered_participant.money_balance, 0)
            if transfer_amount > 0:
                ledger_entries.append(
                    _build_ledger_entry(
                        entry_kind="murder_transfer",
                        amount=transfer_amount,
                        from_holder_id=command.murdered_user_id,
                        to_holder_id=murderer_participant.user_id,
                        now_epoch_seconds=now_epoch_seconds,
                        note="Reported murder transfer.",
                    )
                )
            next_participants, next_notification_feed, enforcer_bonus_entries = _apply_enforcer_first_kill_bonus_if_needed(
                next_participants,
                murderer_user_id=murderer_participant.user_id,
                victim_user_id=command.murdered_user_id,
                victim_money_balance=transfer_amount,
                moderator_user_id=session.moderator_user_id,
                notification_feed=next_notification_feed,
                now_epoch_seconds=now_epoch_seconds,
            )
            ledger_entries.extend(enforcer_bonus_entries)

        unavailable_user_ids = {captured_target_user_id} if captured_target_user_id else set()
        next_police_leader_user_id = _resolve_next_leader_user_id(
            next_participants,
            faction="Police",
            current_leader_user_id=session.current_police_leader_user_id,
            unavailable_user_ids=unavailable_user_ids,
        )
        next_mob_leader_user_id = _resolve_next_leader_user_id(
            next_participants,
            faction="Mob",
            current_leader_user_id=session.current_mob_leader_user_id,
            unavailable_user_ids=unavailable_user_ids,
        )

        accused_selection_cursor = [next_police_leader_user_id] if next_police_leader_user_id else []
        silenced_user_ids, next_participants, post_trial_notification_feed = _apply_armed_don_silence_for_upcoming_trial(
            next_participants,
            accused_selection_cursor=accused_selection_cursor,
            moderator_user_id=session.moderator_user_id,
            notification_feed=next_notification_feed,
            now_epoch_seconds=now_epoch_seconds,
        )
        pending_trial = TrialStateSnapshot(
            murdered_user_id=command.murdered_user_id,
            murderer_user_id=murderer_user_id,
            accused_user_id=None,
            accused_selection_cursor=accused_selection_cursor,
            accused_selection_deadline_epoch_seconds=(
                now_epoch_seconds + ACCUSED_SELECTION_TIMEOUT_SECONDS if accused_selection_cursor else None
            ),
            jury_user_ids=[],
            vote_deadline_epoch_seconds=None,
            votes=[],
            verdict=None,
            conviction_correct=None,
            resolution=None if accused_selection_cursor else "no_conviction",
            accused_by_user_id=None,
            silenced_user_ids=silenced_user_ids,
        )
        next_phase = cast(GamePhase, "accused_selection" if accused_selection_cursor else "boundary_resolution")
        updated = replace(
            session,
            participants=next_participants,
            pending_trial=pending_trial,
            phase=next_phase,
            current_police_leader_user_id=next_police_leader_user_id,
            current_mob_leader_user_id=next_mob_leader_user_id,
            latest_public_notice=(
                f"{murdered_participant.username.upper()} WAS MURDERED WITH "
                f"{'GUN' if _is_gun_attack_classification(command.attack_classification) else 'KNIFE'} "
                f"- REPORT IMMEDIATELY TO COURT HOUSE"
            ),
            latest_private_notice_user_id=None,
            latest_private_notice_message=None,
            notification_feed=post_trial_notification_feed,
            pending_gift_offers=[],
            pending_money_gift_offers=[],
            pending_sale_offers=[],
            police_mob_kills_count=session.police_mob_kills_count + police_mob_kill_increment,
            version=session.version + 1,
        )
        if ledger_entries:
            updated = _append_ledger_entries(updated, ledger_entries)
        updated = self._resolve_boundary_if_needed(updated, now_epoch_seconds=now_epoch_seconds)
        self._save_game_session(session, updated)
        return updated

    def advance_accused_selection_timeout(self, command: AdvanceAccusedSelectionTimeoutCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        if command.requested_by_user_id != session.moderator_user_id:
            raise PermissionError("Only moderator can advance accused-selection timeout.")
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.phase != "accused_selection" or session.pending_trial is None:
            raise ConflictProblem("Accused-selection timeout advance is only valid during accused_selection phase.")

        pending_trial = session.pending_trial
        deadline = pending_trial.accused_selection_deadline_epoch_seconds
        if deadline is None:
            raise ConflictProblem("Accused-selection timeout advance requires an active deadline.")

        now_epoch_seconds = self._now_epoch_seconds()
        if now_epoch_seconds < deadline:
            raise ConflictProblem(
                detail=(
                    "Accused-selection timeout has not elapsed yet. "
                    f"Current time {now_epoch_seconds}, deadline {deadline}."
                ),
                code="timeout_not_reached",
            )

        next_cursor = list(pending_trial.accused_selection_cursor[1:])
        if next_cursor:
            next_trial = replace(
                pending_trial,
                accused_selection_cursor=next_cursor,
                accused_selection_deadline_epoch_seconds=now_epoch_seconds + ACCUSED_SELECTION_TIMEOUT_SECONDS,
            )
            next_phase = cast(GamePhase, "accused_selection")
        else:
            next_trial = replace(
                pending_trial,
                accused_selection_cursor=[],
                accused_selection_deadline_epoch_seconds=None,
                resolution="no_conviction",
            )
            # Invariant: trial chain exhaustion resolves into boundary phase; end-game
            # checks are intentionally deferred to boundary-resolution handling.
            next_phase = cast(GamePhase, "boundary_resolution")

        updated = replace(
            session,
            pending_trial=next_trial,
            phase=next_phase,
            version=session.version + 1,
        )
        updated = self._resolve_boundary_if_needed(updated, now_epoch_seconds=now_epoch_seconds)
        self._save_game_session(session, updated)
        return updated


    def submit_trial_vote(self, command: SubmitTrialVoteCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.phase != "trial_voting" or session.pending_trial is None:
            raise ConflictProblem("Trial voting is only valid during trial_voting phase.", code="invalid_state")
        _raise_if_sergeant_captured(
            session,
            user_id=command.voter_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )

        pending_trial = session.pending_trial
        jury_deadline = pending_trial.vote_deadline_epoch_seconds
        tamper_deadline = pending_trial.gangster_tamper_vote_deadline_epoch_seconds
        if command.vote_slot == "jury":
            if jury_deadline is None:
                raise ConflictProblem("Jury voting is not active yet.", code="invalid_state")
            if command.voter_user_id not in pending_trial.jury_user_ids:
                raise PermissionError("Only assigned jury members can vote.")
        elif command.vote_slot == "tamper":
            if pending_trial.gangster_tamper_actor_user_id != command.voter_user_id:
                raise PermissionError("Only the Gangster can submit the tamper vote.")
            if tamper_deadline is None:
                raise ConflictProblem("Tamper voting is not active.", code="invalid_state")
        if any(
            vote.get("user_id") == command.voter_user_id and str(vote.get("vote_slot", "jury")) == command.vote_slot
            for vote in pending_trial.votes
        ):
            raise ConflictProblem("Vote has already been submitted for this slot.", code="invalid_state")

        next_votes = [*pending_trial.votes, {"user_id": command.voter_user_id, "vote": command.vote, "vote_slot": command.vote_slot}]
        updated = replace(
            session,
            pending_trial=replace(pending_trial, votes=next_votes),
            version=session.version + 1,
        )
        updated = self._finalize_trial_voting_if_ready(updated, now_epoch_seconds=now_epoch_seconds)
        self._save_game_session(session, updated)
        return updated

    def activate_don_silence(self, command: ActivateDonSilenceCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Don")
        if session.phase != "information":
            raise ConflictProblem("Don Intimidation can only be armed during information phase.", code="invalid_state")
        if actor.power_state.don_silence_used:
            raise ConflictProblem("Don Intimidation has already been used.", code="invalid_state")

        target = next((participant for participant in session.participants if participant.user_id == command.target_user_id), None)
        if target is None or target.life_state != "alive":
            raise ValueError("Intimidation target must be an alive participant.")
        if target.user_id == actor.user_id:
            raise ValueError("Don cannot target self with Intimidation.")

        participants = [
            replace(
                participant,
                power_state=replace(
                    participant.power_state,
                    don_silence_used=True,
                    don_silence_target_user_id=target.user_id,
                ),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]

        updated = replace(
            session,
            participants=participants,
            notification_feed=_append_notifications(
                session.notification_feed,
                [
                    (actor.user_id, f"You armed Intimidation. {target.username} will be silenced on the next trial."),
                    (
                        session.moderator_user_id,
                        f"Don armed Intimidation targeting {target.username}.",
                    ),
                ],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_underboss_jury_override(self, command: ActivateUnderBossJuryOverrideCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Under Boss")
        if session.phase != "trial_voting" or session.pending_trial is None:
            raise ConflictProblem("Under Boss jury override can only be used during trial voting.", code="invalid_state")
        if actor.power_state.underboss_jury_override_used:
            raise ConflictProblem("Under Boss jury override has already been used.", code="invalid_state")
        if actor.user_id == session.pending_trial.accused_user_id:
            raise ConflictProblem("Accused player cannot force onto the jury.", code="invalid_state")
        if actor.user_id in session.pending_trial.jury_user_ids:
            raise ConflictProblem("Under Boss is already on the jury.", code="invalid_state")
        if command.removed_juror_user_id not in session.pending_trial.jury_user_ids:
            raise ValueError("Selected juror is not assigned to this trial.")

        removed_juror = next(
            (participant for participant in session.participants if participant.user_id == command.removed_juror_user_id),
            None,
        )
        if removed_juror is None:
            raise ValueError("Removed juror participant not found.")

        jury_user_ids = [
            actor.user_id if user_id == command.removed_juror_user_id else user_id
            for user_id in session.pending_trial.jury_user_ids
        ]
        next_votes = [
            vote
            for vote in session.pending_trial.votes
            if vote.get("user_id") != command.removed_juror_user_id
        ]
        participants = [
            replace(
                participant,
                power_state=replace(participant.power_state, underboss_jury_override_used=True),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]

        updated = replace(
            session,
            participants=participants,
            pending_trial=replace(
                session.pending_trial,
                jury_user_ids=jury_user_ids,
                votes=next_votes,
            ),
            notification_feed=_append_notifications(
                session.notification_feed,
                [
                    (actor.user_id, f"You forced onto the jury and removed {removed_juror.username}."),
                    (
                        removed_juror.user_id,
                        "The mob manipulated the jury selection process and removed you from this trial.",
                    ),
                    (
                        session.moderator_user_id,
                        f"Under Boss replaced juror {removed_juror.username} on this trial.",
                    ),
                ],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_kingpin_reduce_clock(self, command: ActivateKingpinReduceClockCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Kingpin")
        if session.phase != "trial_voting" or session.pending_trial is None:
            raise ConflictProblem("Kingpin clock reduction can only be used during trial voting.", code="invalid_state")
        if session.pending_trial.vote_deadline_epoch_seconds is None:
            raise ConflictProblem("Jury voting is not active yet.", code="invalid_state")

        reduced_trial_keys = list(actor.power_state.kingpin_reduced_trial_keys)
        current_trial_key = _current_trial_key(session)
        if current_trial_key in reduced_trial_keys:
            raise ConflictProblem("Kingpin has already reduced this trial clock.", code="invalid_state")
        if len(reduced_trial_keys) >= 2:
            raise ConflictProblem("Kingpin has already used both clock reductions.", code="invalid_state")

        next_deadline = max(now_epoch_seconds, session.pending_trial.vote_deadline_epoch_seconds - KINGPIN_VOTE_CLOCK_REDUCTION_SECONDS)
        participants = [
            replace(
                participant,
                power_state=replace(
                    participant.power_state,
                    kingpin_reduced_trial_keys=[*reduced_trial_keys, current_trial_key],
                ),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]
        updated = replace(
            session,
            participants=participants,
            pending_trial=replace(session.pending_trial, vote_deadline_epoch_seconds=next_deadline),
            notification_feed=_append_notifications(
                session.notification_feed,
                [
                    (actor.user_id, "You reduced the jury vote clock by 5 seconds."),
                    (session.moderator_user_id, "Kingpin reduced the jury vote clock by 5 seconds."),
                ],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_gangster_tamper(self, command: ActivateGangsterTamperCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Gangster")
        if session.phase != "trial_voting" or session.pending_trial is None:
            raise ConflictProblem("Gangster tamper can only be used during trial voting.", code="invalid_state")
        if actor.power_state.gangster_tamper_used:
            raise ConflictProblem("Gangster tamper has already been used.", code="invalid_state")
        if session.pending_trial.gangster_tamper_target_user_id is not None:
            raise ConflictProblem("Gangster tamper is already active for this trial.", code="invalid_state")
        if command.target_user_id not in session.pending_trial.jury_user_ids:
            raise ValueError("Selected target is not on the current jury.")
        if actor.user_id in session.pending_trial.jury_user_ids and command.target_user_id == actor.user_id:
            raise ValueError("Gangster cannot target self while serving on the jury.")

        participants = [
            replace(
                participant,
                power_state=replace(participant.power_state, gangster_tamper_used=True),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]
        target = next((participant for participant in session.participants if participant.user_id == command.target_user_id), None)
        target_label = target.username if target is not None else command.target_user_id
        updated = replace(
            session,
            participants=participants,
            pending_trial=replace(
                session.pending_trial,
                gangster_tamper_target_user_id=command.target_user_id,
                gangster_tamper_actor_user_id=actor.user_id,
                gangster_tamper_vote_deadline_epoch_seconds=now_epoch_seconds + GANGSTER_TAMPER_VOTE_TIMEOUT_SECONDS,
            ),
            notification_feed=_append_notifications(
                session.notification_feed,
                [
                    (actor.user_id, f"You tampered with {target_label}'s jury slot and received a replacement vote."),
                    (command.target_user_id, "The mob manipulated your vote through court document tampering."),
                    (session.moderator_user_id, f"Gangster tampered with juror {target_label}."),
                ],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        updated = self._finalize_trial_voting_if_ready(updated, now_epoch_seconds=now_epoch_seconds)
        self._save_game_session(session, updated)
        return updated

    def activate_street_thug_steal(self, command: ActivateStreetThugStealCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Street Thug")
        if actor.power_state.street_thug_steal_used:
            raise ConflictProblem("Street Thug steal has already been used.", code="invalid_state")
        if actor.user_id == command.target_user_id:
            raise ValueError("Street Thug cannot target self with steal.")

        target = next((participant for participant in session.participants if participant.user_id == command.target_user_id), None)
        if target is None:
            raise ValueError("Steal target not found.")
        if target.life_state != "alive":
            raise ConflictProblem("Steal target must be alive.", code="invalid_state")
        if _active_sergeant_capture_target_user_id(session, now_epoch_seconds=now_epoch_seconds) == target.user_id:
            raise ConflictProblem("Player in police custody cannot be targeted by steal right now.", code="invalid_state")

        success = target.money_balance >= 100
        updated_participants: list[ParticipantStateSnapshot] = []
        for participant in session.participants:
            next_participant = participant
            if participant.user_id == actor.user_id:
                next_money_balance = participant.money_balance + (100 if success else 0)
                next_participant = replace(
                    participant,
                    money_balance=next_money_balance,
                    power_state=replace(participant.power_state, street_thug_steal_used=True),
                )
            elif participant.user_id == target.user_id:
                next_money_balance = participant.money_balance - (100 if success else 0)
                next_participant = replace(participant, money_balance=next_money_balance)
            updated_participants.append(next_participant)

        if success:
            notifications = [
                (actor.user_id, f"You mugged {target.username} and stole $100."),
                (target.user_id, "You were mugged and $100 was stolen."),
                (session.moderator_user_id, f"{actor.username} mugged {target.username} and stole $100."),
            ]
            ledger_entries = [
                _build_ledger_entry(
                    entry_kind="street_thug_steal",
                    amount=100,
                    from_holder_id=target.user_id,
                    to_holder_id=actor.user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    note="Street Thug steal.",
                )
            ]
        else:
            notifications = [
                (actor.user_id, f"{target.username} had less than $100. Steal was wasted."),
                (target.user_id, "Someone tried to mug you, but you had less than $100 to steal."),
                (session.moderator_user_id, f"{actor.username} tried to mug {target.username}, but the target had less than $100."),
            ]
            ledger_entries = []

        updated = replace(
            session,
            participants=updated_participants,
            notification_feed=_append_notifications(
                session.notification_feed,
                notifications,
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        updated = _append_ledger_entries(updated, ledger_entries)
        updated = _refresh_ledger(updated)
        self._save_game_session(session, updated)
        return updated

    def activate_smuggler_smuggle(self, command: ActivateSmugglerSmuggleCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Smuggler")
        if session.phase != "information":
            raise ConflictProblem("Smuggle is only available during information phase.", code="invalid_state")
        if actor.power_state.smuggler_smuggle_used:
            raise ConflictProblem("Smuggle has already been used.", code="invalid_state")
        if actor.user_id == command.target_user_id:
            raise ValueError("Smuggler cannot target self with smuggle.")

        target = next((participant for participant in session.participants if participant.user_id == command.target_user_id), None)
        if target is None:
            raise ValueError("Smuggle target not found.")
        if target.life_state != "alive":
            raise ConflictProblem("Smuggle target must be alive.", code="invalid_state")
        if _active_sergeant_capture_target_user_id(session, now_epoch_seconds=now_epoch_seconds) == target.user_id:
            raise ConflictProblem("Player in police custody cannot be targeted by smuggle right now.", code="invalid_state")

        locked_inventory_item_ids = _locked_inventory_item_ids_for_participant(session, participant_user_id=target.user_id)
        eligible_items = [item for item in target.inventory if item.item_id not in locked_inventory_item_ids]
        stolen_item = self._smuggler_item_selector(eligible_items) if eligible_items else None

        updated_participants: list[ParticipantStateSnapshot] = []
        for participant in session.participants:
            next_participant = participant
            if participant.user_id == actor.user_id:
                next_inventory = participant.inventory
                if stolen_item is not None:
                    next_inventory = [*participant.inventory, stolen_item]
                next_participant = replace(
                    participant,
                    inventory=next_inventory,
                    power_state=replace(participant.power_state, smuggler_smuggle_used=True),
                )
            elif participant.user_id == target.user_id and stolen_item is not None:
                next_participant = replace(
                    participant,
                    inventory=[item for item in participant.inventory if item.item_id != stolen_item.item_id],
                )
            updated_participants.append(next_participant)

        if stolen_item is None:
            notifications = [
                (actor.user_id, f"{target.username} had no eligible items to steal. Smuggle was wasted."),
                (target.user_id, "Someone attempted to burgle you, but no item was taken."),
                (session.moderator_user_id, f"{actor.username} tried to smuggle from {target.username}, but no eligible item was available."),
            ]
            player_transactions: list[PlayerTransactionSnapshot] = []
        else:
            notifications = [
                (actor.user_id, f"You smuggled {stolen_item.display_name} from {target.username}."),
                (target.user_id, f"You were burglarized. {stolen_item.display_name} was stolen."),
                (session.moderator_user_id, f"{target.username} was burglarized by {actor.username}. {stolen_item.display_name} was stolen."),
            ]
            player_transactions = [
                _build_player_transaction(
                    transaction_kind="item_theft",
                    sender_user_id=target.user_id,
                    recipient_user_id=actor.user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    item_name=stolen_item.display_name,
                )
            ]

        updated = replace(
            session,
            participants=updated_participants,
            notification_feed=_append_notifications(
                session.notification_feed,
                notifications,
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        updated = _append_player_transactions(updated, player_transactions)
        self._save_game_session(session, updated)
        return updated

    def activate_gun_runner_charisma(self, command: ActivateGunRunnerCharismaCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Gun Runner")
        if session.phase != "information":
            raise ConflictProblem("Charisma is only available during information phase.", code="invalid_state")
        if actor.power_state.gun_runner_charisma_used:
            raise ConflictProblem("Charisma has already been used.", code="invalid_state")

        notifications = [
            (
                actor.user_id,
                "Charisma is active for 3 minutes. You will receive a 30% bonus on accepted sales during this window.",
            ),
            (
                session.moderator_user_id,
                f"{actor.username} activated Charisma for the next 3 minutes.",
            ),
        ]
        if _active_asset_freeze_target_user_id(session, now_epoch_seconds=now_epoch_seconds) == actor.user_id:
            notifications.append(
                (
                    actor.user_id,
                    "Your accounts are frozen, so no transactions can be completed until the police freeze expires.",
                )
            )

        updated = replace(
            session,
            participants=[
                replace(
                    participant,
                    power_state=replace(
                        participant.power_state,
                        gun_runner_charisma_used=True,
                        gun_runner_charisma_expires_at_epoch_seconds=now_epoch_seconds + GUN_RUNNER_CHARISMA_SECONDS,
                    ),
                )
                if participant.user_id == actor.user_id
                else participant
                for participant in session.participants
            ],
            notification_feed=_append_notifications(
                session.notification_feed,
                notifications,
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_supplier_acquire(self, command: ActivateSupplierAcquireCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Supplier")
        if session.phase != "information":
            raise ConflictProblem("Acquire is only available during information phase.", code="invalid_state")
        if actor.power_state.supplier_acquire_used:
            raise ConflictProblem("Acquire has already been used.", code="invalid_state")
        if actor.user_id == command.target_user_id:
            raise ValueError("Supplier cannot target self with Acquire.")

        target = next((participant for participant in session.participants if participant.user_id == command.target_user_id), None)
        if target is None:
            raise ValueError("Acquire target not found.")
        if target.life_state != "alive":
            raise ConflictProblem("Acquire target must be alive.", code="invalid_state")

        if target.role_name not in SUPPLIER_ACQUIRE_VALID_TARGET_ROLES:
            notifications = [
                (actor.user_id, f"Acquire failed. {target.username} is not a merchant-faction seller role."),
                (session.moderator_user_id, f"{actor.username} used Acquire on {target.username}, but the guess was wrong."),
            ]
            updated = replace(
                session,
                participants=[
                    replace(
                        participant,
                        power_state=replace(participant.power_state, supplier_acquire_used=True),
                    )
                    if participant.user_id == actor.user_id
                    else participant
                    for participant in session.participants
                ],
                notification_feed=_append_notifications(
                    session.notification_feed,
                    notifications,
                    now_epoch_seconds=now_epoch_seconds,
                ),
                version=session.version + 1,
            )
            self._save_game_session(session, updated)
            return updated

        notifications = [
            (
                actor.user_id,
                f"Acquire is armed on {target.username}. If they complete the next successful player-to-player sale, you will steal 50% of the base sale price.",
            ),
            (
                session.moderator_user_id,
                f"{actor.username} armed Acquire on {target.username}.",
            ),
        ]
        target_user_id = target.user_id
        if _active_asset_freeze_target_user_id(session, now_epoch_seconds=now_epoch_seconds) == actor.user_id:
            notifications = [
                (actor.user_id, "Acquire was canceled immediately because your accounts are currently frozen."),
                (session.moderator_user_id, f"{actor.username}'s Acquire was canceled immediately because the Supplier is frozen."),
            ]
            target_user_id = None

        updated = replace(
            session,
            participants=[
                replace(
                    participant,
                    power_state=replace(
                        participant.power_state,
                        supplier_acquire_used=True,
                        supplier_acquire_target_user_id=target_user_id,
                    ),
                )
                if participant.user_id == actor.user_id
                else participant
                for participant in session.participants
            ],
            notification_feed=_append_notifications(
                session.notification_feed,
                notifications,
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_merchant_wholesale_order(
        self, command: ActivateMerchantWholesaleOrderCommand
    ) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_asset_frozen(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Merchant")
        if session.phase != "information":
            raise ConflictProblem("Wholesale Order is only available during information phase.", code="invalid_state")
        if actor.power_state.merchant_wholesale_order_used:
            raise ConflictProblem("Wholesale Order has already been used.", code="invalid_state")

        updated = _purchase_from_supply(
            session,
            buyer_user_id=command.actor_user_id,
            classification=command.classification,
            role_mode="merchant_wholesale_order",
            now_epoch_seconds=now_epoch_seconds,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_deputy_protective_custody(self, command: ActivateDeputyProtectiveCustodyCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Deputy")
        if session.phase != "information":
            raise ConflictProblem("Protective custody is only available during information phase.", code="invalid_state")
        if actor.power_state.deputy_protective_custody_used:
            raise ConflictProblem("Deputy protective custody has already been used.", code="invalid_state")
        if actor.user_id == command.target_user_id:
            raise ValueError("Deputy cannot target self with protective custody.")

        target = next((participant for participant in session.participants if participant.user_id == command.target_user_id), None)
        if target is None:
            raise ValueError("Protective custody target not found.")
        if target.life_state != "alive":
            raise ConflictProblem("Protective custody target must be alive.", code="invalid_state")

        if _active_protective_custody_target_user_id(session, now_epoch_seconds=now_epoch_seconds) is not None:
            raise ConflictProblem("Only one protective custody target can be active at a time.", code="invalid_state")

        participants = [
            replace(
                participant,
                power_state=replace(participant.power_state, deputy_protective_custody_used=True),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]
        updated = replace(
            session,
            participants=participants,
            protective_custody_user_id=target.user_id,
            protective_custody_by_user_id=actor.user_id,
            protective_custody_expires_at_epoch_seconds=now_epoch_seconds + PROTECTIVE_CUSTODY_DURATION_SECONDS,
            notification_feed=_append_notifications(
                session.notification_feed,
                [
                    (actor.user_id, f"You placed {target.username} in protective custody for 5 minutes."),
                    (
                        target.user_id,
                        "You are under police protective custody for 5 minutes. Murder attempts on you will fail.",
                    ),
                    (
                        session.moderator_user_id,
                        f"Deputy placed {target.username} in protective custody for 5 minutes.",
                    ),
                ],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_sheriff_view_jury_log(self, command: ActivateSheriffViewJuryLogCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Sheriff")
        if session.status != "in_progress":
            raise ConflictProblem("Cannot use powers outside an in-progress game.", code="invalid_state")
        if actor.power_state.sheriff_jury_log_views_used >= 2:
            raise ConflictProblem("Sheriff can only view jury log twice per game.", code="invalid_state")
        if not session.latest_jury_log_user_ids:
            raise ConflictProblem("No jury history yet", code="invalid_state")

        updated_participants = [
            replace(
                participant,
                power_state=replace(
                    participant.power_state,
                    sheriff_jury_log_views_used=participant.power_state.sheriff_jury_log_views_used + 1,
                    sheriff_jury_log_visible_until_epoch_seconds=now_epoch_seconds + SHERIFF_JURY_LOG_VISIBLE_SECONDS,
                    sheriff_last_viewed_jury_user_ids=list(session.latest_jury_log_user_ids),
                ),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]
        updated = replace(
            session,
            participants=updated_participants,
            notification_feed=_append_notifications(
                session.notification_feed,
                [(actor.user_id, "Most recent jury log revealed for 60 seconds.")],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_captain_asset_freeze(self, command: ActivateCaptainAssetFreezeCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=self._now_epoch_seconds(),
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Captain")
        if actor.power_state.captain_asset_freeze_used:
            raise ConflictProblem("Captain asset freeze has already been used.", code="invalid_state")
        if actor.user_id == command.target_user_id:
            raise ValueError("Captain cannot target self with asset freeze.")
        if _active_asset_freeze_target_user_id(session, now_epoch_seconds=self._now_epoch_seconds()) is not None:
            raise ConflictProblem("Only one asset freeze can be active at a time.", code="invalid_state")

        target = next((participant for participant in session.participants if participant.user_id == command.target_user_id), None)
        if target is None:
            raise ValueError("Asset freeze target not found.")
        if target.life_state != "alive":
            raise ConflictProblem("Asset freeze target must be alive.", code="invalid_state")

        frozen_message = _build_asset_freeze_blocked_message(target.username)
        now_epoch_seconds = self._now_epoch_seconds()
        canceled_gift_offers = [
            offer
            for offer in session.pending_gift_offers
            if command.target_user_id in {offer.giver_user_id, offer.receiver_user_id}
        ]
        canceled_money_offers = [
            offer
            for offer in session.pending_money_gift_offers
            if command.target_user_id in {offer.giver_user_id, offer.receiver_user_id}
        ]
        canceled_sale_offers = [
            offer
            for offer in session.pending_sale_offers
            if command.target_user_id in {offer.seller_user_id, offer.buyer_user_id}
        ]
        canceled_user_ids: set[str] = {command.target_user_id}
        for offer in canceled_gift_offers:
            canceled_user_ids.update({offer.giver_user_id, offer.receiver_user_id})
        for offer in canceled_money_offers:
            canceled_user_ids.update({offer.giver_user_id, offer.receiver_user_id})
        for offer in canceled_sale_offers:
            canceled_user_ids.update({offer.seller_user_id, offer.buyer_user_id})
        canceled_user_ids.update({actor.user_id, session.moderator_user_id})

        updated_participants = [
            replace(
                participant,
                power_state=replace(participant.power_state, captain_asset_freeze_used=True),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]
        updated = replace(
            session,
            participants=updated_participants,
            pending_gift_offers=[
                offer
                for offer in session.pending_gift_offers
                if offer not in canceled_gift_offers
            ],
            pending_money_gift_offers=[
                offer
                for offer in session.pending_money_gift_offers
                if offer not in canceled_money_offers
            ],
            pending_sale_offers=[
                offer
                for offer in session.pending_sale_offers
                if offer not in canceled_sale_offers
            ],
            asset_freeze_user_id=target.user_id,
            asset_freeze_by_user_id=actor.user_id,
            asset_freeze_expires_at_epoch_seconds=now_epoch_seconds + CAPTAIN_ASSET_FREEZE_SECONDS,
            notification_feed=_append_notifications(
                session.notification_feed,
                [(user_id, frozen_message) for user_id in sorted(canceled_user_ids)],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_lieutenant_information_briefcase(
        self, command: ActivateLieutenantInformationBriefcaseCommand
    ) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=self._now_epoch_seconds(),
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Lieutenant")
        if actor.power_state.lieutenant_information_briefcase_used:
            raise ConflictProblem("Lieutenant information briefcase has already been used.", code="invalid_state")

        alive_police_count = sum(
            1
            for participant in session.participants
            if participant.life_state == "alive" and participant.faction == "Police"
        )
        alive_mob_count = sum(
            1
            for participant in session.participants
            if participant.life_state == "alive" and participant.faction == "Mob"
        )
        alive_merchant_count = sum(
            1
            for participant in session.participants
            if participant.life_state == "alive" and participant.faction == "Merchant"
        )
        now_epoch_seconds = self._now_epoch_seconds()
        updated_participants = [
            replace(
                participant,
                power_state=replace(
                    participant.power_state,
                    lieutenant_information_briefcase_used=True,
                    lieutenant_briefcase_visible_until_epoch_seconds=(
                        now_epoch_seconds + LIEUTENANT_BRIEFCASE_VISIBLE_SECONDS
                    ),
                    lieutenant_briefcase_alive_police_count=alive_police_count,
                    lieutenant_briefcase_alive_mob_count=alive_mob_count,
                    lieutenant_briefcase_alive_merchant_count=alive_merchant_count,
                ),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]
        updated = replace(
            session,
            participants=updated_participants,
            notification_feed=_append_notifications(
                session.notification_feed,
                [(actor.user_id, "Information briefcase opened for 60 seconds.")],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_sergeant_capture(self, command: ActivateSergeantCaptureCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=self._now_epoch_seconds(),
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Sergeant")
        if session.phase != "information":
            raise ConflictProblem("Sergeant capture is only available during information phase.", code="invalid_state")
        if actor.power_state.sergeant_capture_used:
            raise ConflictProblem("Sergeant capture has already been used.", code="invalid_state")
        if actor.user_id == command.target_user_id:
            raise ValueError("Sergeant cannot target self with capture.")

        now_epoch_seconds = self._now_epoch_seconds()
        if _active_sergeant_capture_target_user_id(session, now_epoch_seconds=now_epoch_seconds) is not None:
            raise ConflictProblem("Only one captured player can be active at a time.", code="invalid_state")

        target = next((participant for participant in session.participants if participant.user_id == command.target_user_id), None)
        if target is None:
            raise ValueError("Capture target not found.")
        if target.life_state != "alive":
            raise ConflictProblem("Capture target must be alive.", code="invalid_state")

        participants_after_use = [
            replace(
                participant,
                power_state=replace(participant.power_state, sergeant_capture_used=True),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]

        next_police_leader_user_id = _resolve_next_leader_user_id(
            participants_after_use,
            faction="Police",
            current_leader_user_id=session.current_police_leader_user_id,
            unavailable_user_ids={target.user_id},
        )
        next_mob_leader_user_id = _resolve_next_leader_user_id(
            participants_after_use,
            faction="Mob",
            current_leader_user_id=session.current_mob_leader_user_id,
            unavailable_user_ids={target.user_id},
        )
        if (
            (session.current_police_leader_user_id == target.user_id and next_police_leader_user_id is None)
            or (session.current_mob_leader_user_id == target.user_id and next_mob_leader_user_id is None)
        ):
            release_message = f"{target.username} was court ordered to be released from police custody."
            updated = replace(
                session,
                participants=participants_after_use,
                notification_feed=_append_notifications(
                    session.notification_feed,
                    [
                        (actor.user_id, release_message),
                        (session.moderator_user_id, release_message),
                        (target.user_id, release_message),
                    ],
                    now_epoch_seconds=now_epoch_seconds,
                ),
                version=session.version + 1,
            )
            self._save_game_session(session, updated)
            return updated

        capture_message = (
            f"{target.username} has been taken into custody by the police department for questioning "
            "and cannot interact with others for 5 minutes."
        )
        notifications = [
            (actor.user_id, capture_message),
            (session.moderator_user_id, capture_message),
            (target.user_id, capture_message),
        ]
        if next_police_leader_user_id != session.current_police_leader_user_id and next_police_leader_user_id is not None:
            notifications.append(
                (
                    next_police_leader_user_id,
                    f"Responsibilities have been temporarily transferred to you because {target.username} is temporarily in police custody.",
                )
            )
        if next_mob_leader_user_id != session.current_mob_leader_user_id and next_mob_leader_user_id is not None:
            notifications.append(
                (
                    next_mob_leader_user_id,
                    f"Responsibilities have been temporarily transferred to you because {target.username} is temporarily in police custody.",
                )
            )
        updated = replace(
            session,
            participants=participants_after_use,
            sergeant_capture_user_id=target.user_id,
            sergeant_capture_by_user_id=actor.user_id,
            sergeant_capture_expires_at_epoch_seconds=now_epoch_seconds + SERGEANT_CAPTURE_SECONDS,
            notification_feed=_append_notifications(
                session.notification_feed,
                notifications,
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def allow_trial_voting(self, command: AllowTrialVotingCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        if command.requested_by_user_id != session.moderator_user_id:
            raise PermissionError("Only moderator can start jury voting.")
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.phase != "trial_voting" or session.pending_trial is None:
            raise ConflictProblem("Start jury voting is only valid during trial_voting phase.", code="invalid_state")
        if session.pending_trial.vote_deadline_epoch_seconds is not None:
            raise ConflictProblem("Jury voting is already active.", code="invalid_state")

        now_epoch_seconds = self._now_epoch_seconds()
        updated = replace(
            session,
            pending_trial=replace(
                session.pending_trial,
                vote_deadline_epoch_seconds=now_epoch_seconds + TRIAL_VOTING_TIMEOUT_SECONDS,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def _cancel_gangster_tamper_if_needed(
        self,
        session: GameDetailsSnapshot,
        *,
        now_epoch_seconds: int,
    ) -> GameDetailsSnapshot:
        pending_trial = session.pending_trial
        if session.phase != "trial_voting" or pending_trial is None:
            return session
        actor_user_id = pending_trial.gangster_tamper_actor_user_id
        if actor_user_id is None:
            return session
        actor = next((participant for participant in session.participants if participant.user_id == actor_user_id), None)
        captured_user_id = _active_sergeant_capture_target_user_id(session, now_epoch_seconds=now_epoch_seconds)
        if actor is not None and actor.life_state == "alive" and captured_user_id != actor.user_id:
            return session
        target_label = pending_trial.gangster_tamper_target_user_id or "unknown juror"
        updated = replace(
            session,
            pending_trial=replace(
                pending_trial,
                gangster_tamper_target_user_id=None,
                gangster_tamper_actor_user_id=None,
                gangster_tamper_vote_deadline_epoch_seconds=None,
            ),
            notification_feed=_append_notifications(
                session.notification_feed,
                [
                    (actor_user_id, "Tamper was canceled because you were no longer active for this trial."),
                    (session.moderator_user_id, f"Gangster tamper on {target_label} was canceled because the Gangster was no longer active."),
                ],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def _resolve_trial_voting_if_deadline_elapsed(
        self,
        session: GameDetailsSnapshot,
        *,
        now_epoch_seconds: int,
    ) -> GameDetailsSnapshot:
        pending_trial = session.pending_trial
        if session.phase != "trial_voting" or pending_trial is None:
            return session
        final_deadline = _trial_final_vote_deadline_epoch_seconds(pending_trial)
        if final_deadline is None or now_epoch_seconds < final_deadline:
            return session
        updated = self._finalize_trial_voting_if_ready(session, now_epoch_seconds=now_epoch_seconds, allow_timeout=True)
        if updated is session:
            return session
        self._save_game_session(session, updated)
        return updated

    def _resolve_felon_escape_if_needed(
        self,
        session: GameDetailsSnapshot,
        *,
        now_epoch_seconds: int,
    ) -> GameDetailsSnapshot:
        felon_user_id = session.felon_escape_user_id
        expires_at = session.felon_escape_expires_at_epoch_seconds
        if not felon_user_id or expires_at is None:
            return session
        if now_epoch_seconds < expires_at:
            return session

        if session.status != "in_progress":
            updated = replace(
                session,
                felon_escape_user_id=None,
                felon_escape_expires_at_epoch_seconds=None,
                version=session.version + 1,
            )
            self._save_game_session(session, updated)
            return updated

        felon = next((participant for participant in session.participants if participant.user_id == felon_user_id), None)
        if felon is None or felon.life_state != "jailed" or felon.role_name != "Felon":
            updated = replace(
                session,
                felon_escape_user_id=None,
                felon_escape_expires_at_epoch_seconds=None,
                version=session.version + 1,
            )
            self._save_game_session(session, updated)
            return updated

        balance_delta = felon.money_balance - 10
        updated_participants = [
            replace(participant, life_state="alive", money_balance=10)
            if participant.user_id == felon_user_id
            else participant
            for participant in session.participants
        ]
        ledger_entries: list[LedgerEntrySnapshot] = []
        if balance_delta > 0:
            ledger_entries.append(
                _build_ledger_entry(
                    entry_kind="felon_escape_reset",
                    amount=balance_delta,
                    from_holder_id=felon_user_id,
                    to_holder_id=CENTRAL_SUPPLY_HOLDER_ID,
                    now_epoch_seconds=now_epoch_seconds,
                    note="Felon escape reset to $10.",
                )
            )
        elif balance_delta < 0:
            ledger_entries.append(
                _build_ledger_entry(
                    entry_kind="felon_escape_reset",
                    amount=abs(balance_delta),
                    from_holder_id=CENTRAL_SUPPLY_HOLDER_ID,
                    to_holder_id=felon_user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    note="Felon escape reset to $10.",
                )
            )
        current_police_leader_user_id = _resolve_next_leader_user_id(
            updated_participants,
            faction="Police",
            current_leader_user_id=session.current_police_leader_user_id,
        )
        current_mob_leader_user_id = _resolve_next_leader_user_id(
            updated_participants,
            faction="Mob",
            current_leader_user_id=session.current_mob_leader_user_id,
        )
        updated = replace(
            session,
            participants=updated_participants,
            current_police_leader_user_id=current_police_leader_user_id,
            current_mob_leader_user_id=current_mob_leader_user_id,
            felon_escape_user_id=None,
            felon_escape_expires_at_epoch_seconds=None,
            latest_public_notice="A felon has escaped from jail and is back in the game.",
            notification_feed=_append_notifications(
                session.notification_feed,
                [(felon_user_id, "You escaped from jail and are back in the game.")],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        if ledger_entries:
            updated = _append_ledger_entries(updated, ledger_entries)
        self._save_game_session(session, updated)
        return updated

    def _finalize_trial_voting_if_ready(
        self,
        session: GameDetailsSnapshot,
        *,
        now_epoch_seconds: int,
        allow_timeout: bool = False,
    ) -> GameDetailsSnapshot:
        pending_trial = session.pending_trial
        if session.phase != "trial_voting" or pending_trial is None:
            return session
        counted_votes = _counted_trial_votes(session, pending_trial, now_epoch_seconds=now_epoch_seconds)
        required_vote_count = len(pending_trial.jury_user_ids)
        if len(counted_votes) < required_vote_count and not (
            allow_timeout and _trial_final_vote_deadline_epoch_seconds(pending_trial) is not None
        ):
            return session
        if len(counted_votes) < required_vote_count and not allow_timeout:
            return session

        guilty_votes = sum(1 for vote in counted_votes if vote.get("vote") == "guilty")
        innocent_votes = len(counted_votes) - guilty_votes
        verdict = "guilty" if guilty_votes > innocent_votes else "innocent"
        next_pending = replace(
            pending_trial,
            votes=list(pending_trial.votes),
            verdict=verdict,
            resolution="vote_complete",
            conviction_correct=None,
            gangster_tamper_target_user_id=None,
            gangster_tamper_actor_user_id=None,
            gangster_tamper_vote_deadline_epoch_seconds=None,
        )
        next_phase = "boundary_resolution"
        next_participants = session.participants
        next_police_leader_user_id = session.current_police_leader_user_id
        next_mob_leader_user_id = session.current_mob_leader_user_id
        ledger_entries: list[LedgerEntrySnapshot] = []
        next_notification_feed = session.notification_feed
        confiscation_successful = False
        conviction_correct = None
        if verdict == "guilty" and pending_trial.accused_user_id:
            conviction_correct = (
                pending_trial.murderer_user_id is not None
                and pending_trial.murderer_user_id == pending_trial.accused_user_id
            )
            efj_inventory_item = _find_inventory_item(
                session.participants,
                user_id=pending_trial.accused_user_id,
                classification="escape_from_jail",
            )
            if efj_inventory_item is not None:
                participants_after_resolution = _remove_inventory_item_from_participant(
                    session.participants,
                    user_id=pending_trial.accused_user_id,
                    inventory_item_id=efj_inventory_item.item_id,
                )
                efj_recipient = _select_efj_bribe_recipient(
                    participants_after_resolution,
                    accused_user_id=pending_trial.accused_user_id,
                    selector=self._efj_bribe_recipient_selector,
                )
                if efj_recipient is not None:
                    participants_after_resolution = _adjust_participant_money_balance(
                        participants_after_resolution,
                        user_id=efj_recipient.user_id,
                        delta=efj_inventory_item.acquisition_value,
                    )
                    ledger_entries.append(
                        _build_ledger_entry(
                            entry_kind="efj_bribe_transfer",
                            amount=efj_inventory_item.acquisition_value,
                            from_holder_id=CENTRAL_SUPPLY_HOLDER_ID,
                            to_holder_id=efj_recipient.user_id,
                            now_epoch_seconds=self._now_epoch_seconds(),
                            note="EFJ bribe transfer.",
                        )
                    )
                    next_notification_feed = _append_notifications(
                        session.notification_feed,
                        [(efj_recipient.user_id, "You accepted a bribe.")],
                        now_epoch_seconds=self._now_epoch_seconds(),
                    )
                participants_after_resolution, next_notification_feed = _consume_police_confiscation_if_pending(
                    participants_after_resolution,
                    notification_feed=next_notification_feed,
                    moderator_user_id=session.moderator_user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    message="Confiscation was canceled because the accused escaped from jail.",
                )
                updated = replace(
                    session,
                    participants=participants_after_resolution,
                    pending_trial=replace(next_pending, resolution="efj_saved", conviction_correct=conviction_correct),
                    phase=next_phase,
                    notification_feed=next_notification_feed,
                    version=session.version + 1,
                )
                if ledger_entries:
                    updated = _append_ledger_entries(updated, ledger_entries)
                return self._resolve_boundary_if_needed(updated, now_epoch_seconds=self._now_epoch_seconds())

            participants_after_jail = [
                replace(participant, life_state="jailed")
                if participant.user_id == pending_trial.accused_user_id and participant.life_state == "alive"
                else participant
                for participant in session.participants
            ]
            captured_user_id = _active_sergeant_capture_target_user_id(session, now_epoch_seconds=now_epoch_seconds)
            unavailable_user_ids = {captured_user_id} if captured_user_id else set()
            next_police_leader_user_id = _resolve_next_leader_user_id(
                participants_after_jail,
                faction="Police",
                current_leader_user_id=session.current_police_leader_user_id,
                unavailable_user_ids=unavailable_user_ids,
            )
            next_mob_leader_user_id = _resolve_next_leader_user_id(
                participants_after_jail,
                faction="Mob",
                current_leader_user_id=session.current_mob_leader_user_id,
                unavailable_user_ids=unavailable_user_ids,
            )
            inventory_recipient_user_id = next_police_leader_user_id if conviction_correct else next_mob_leader_user_id
            confiscation_result = _apply_police_officer_confiscation_if_pending(
                participants_after_jail,
                accused_user_id=pending_trial.accused_user_id,
                normal_recipient_user_id=inventory_recipient_user_id,
                moderator_user_id=session.moderator_user_id,
                now_epoch_seconds=now_epoch_seconds,
            )
            next_participants = confiscation_result.participants
            next_notification_feed = _append_notifications(
                next_notification_feed,
                confiscation_result.notifications,
                now_epoch_seconds=now_epoch_seconds,
            )
            ledger_entries.extend(confiscation_result.ledger_entries)
            confiscation_successful = confiscation_result.handled
            if not confiscation_result.handled:
                convicted_money_balance = max(
                    next(
                        (
                            participant.money_balance
                            for participant in confiscation_result.participants
                            if participant.user_id == pending_trial.accused_user_id
                        ),
                        0,
                    ),
                    0,
                )
                next_participants = _transfer_inventory_between_participants(
                    confiscation_result.participants,
                    from_user_id=pending_trial.accused_user_id,
                    to_user_id=inventory_recipient_user_id,
                )
                if inventory_recipient_user_id is not None and inventory_recipient_user_id != pending_trial.accused_user_id:
                    if convicted_money_balance > 0:
                        ledger_entries.append(
                            _build_ledger_entry(
                                entry_kind="conviction_transfer",
                                amount=convicted_money_balance,
                                from_holder_id=pending_trial.accused_user_id,
                                to_holder_id=inventory_recipient_user_id,
                                now_epoch_seconds=self._now_epoch_seconds(),
                                note="Conviction resource transfer.",
                            )
                        )
            next_participants = [
                replace(
                    participant,
                    accused_by_user_id=pending_trial.accused_by_user_id,
                    convicted_by_user_ids=sorted(
                        {
                            str(vote.get("user_id", ""))
                            for vote in counted_votes
                            if vote.get("vote") == "guilty" and str(vote.get("user_id", "")).strip()
                        }
                    ),
                )
                if participant.user_id == pending_trial.accused_user_id
                else participant
                for participant in next_participants
            ]
            felon_escape_user_id = session.felon_escape_user_id
            felon_escape_expires_at_epoch_seconds = session.felon_escape_expires_at_epoch_seconds
            accused_after_verdict = next(
                (participant for participant in next_participants if participant.user_id == pending_trial.accused_user_id),
                None,
            )
            if accused_after_verdict is not None and accused_after_verdict.role_name == "Felon" and accused_after_verdict.life_state == "jailed":
                felon_escape_user_id = accused_after_verdict.user_id
                felon_escape_expires_at_epoch_seconds = now_epoch_seconds + FELON_ESCAPE_SECONDS
                next_notification_feed = _append_notifications(
                    next_notification_feed,
                    [
                        (
                            accused_after_verdict.user_id,
                            "You were jailed. Sit out for 30 minutes. Do not talk to active players or look at their devices during this time.",
                        ),
                        (
                            session.moderator_user_id,
                            f"{accused_after_verdict.username} was jailed and must sit out for 30 minutes before escape is possible.",
                        ),
                    ],
                    now_epoch_seconds=now_epoch_seconds,
                )
            next_pending = replace(
                next_pending,
                resolution="confiscated" if confiscation_successful else "vote_complete",
                conviction_correct=conviction_correct,
            )
        elif verdict == "innocent":
            next_participants, next_notification_feed = _consume_police_confiscation_if_pending(
                session.participants,
                notification_feed=next_notification_feed,
                moderator_user_id=session.moderator_user_id,
                now_epoch_seconds=now_epoch_seconds,
                message="Confiscation was consumed because the next trial did not end in a guilty verdict.",
            )
        updated = replace(
            session,
            participants=next_participants,
            pending_trial=next_pending,
            phase=next_phase,
            current_police_leader_user_id=next_police_leader_user_id,
            current_mob_leader_user_id=next_mob_leader_user_id,
            felon_escape_user_id=felon_escape_user_id if verdict == "guilty" else session.felon_escape_user_id,
            felon_escape_expires_at_epoch_seconds=(
                felon_escape_expires_at_epoch_seconds if verdict == "guilty" else session.felon_escape_expires_at_epoch_seconds
            ),
            notification_feed=next_notification_feed,
            version=session.version + 1,
        )
        if ledger_entries:
            updated = _append_ledger_entries(updated, ledger_entries)
        return self._resolve_boundary_if_needed(updated, now_epoch_seconds=self._now_epoch_seconds())

    def activate_detective_investigation(self, command: ActivateDetectiveInvestigationCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Detective")
        if session.status != "in_progress":
            raise ConflictProblem("Cannot use powers outside an in-progress game.", code="invalid_state")
        if actor.power_state.detective_investigation_used:
            raise ConflictProblem("Detective investigation has already been used.", code="invalid_state")

        target = next((participant for participant in session.participants if participant.user_id == command.target_user_id), None)
        if target is None:
            raise ValueError("Investigation target not found.")

        transaction_history = _build_detective_transaction_history(session)
        target_transactions = [
            transaction
            for transaction in transaction_history
            if command.target_user_id in {transaction.sender_user_id, transaction.recipient_user_id}
        ]
        latest_transactions = target_transactions[-3:]

        updated_participants = [
            replace(
                participant,
                power_state=replace(
                    participant.power_state,
                    detective_investigation_used=True,
                    detective_investigation_visible_until_epoch_seconds=(
                        now_epoch_seconds + DETECTIVE_INVESTIGATION_VISIBLE_SECONDS
                    ),
                    detective_investigation_target_user_id=target.user_id,
                    detective_last_viewed_transaction_total=len(target_transactions),
                    detective_last_viewed_transactions=latest_transactions,
                ),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]
        updated = replace(
            session,
            participants=updated_participants,
            notification_feed=_append_notifications(
                session.notification_feed,
                [(actor.user_id, "Investigation opened for 60 seconds.")],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_inspector_record_inspection(self, command: ActivateInspectorRecordInspectionCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Inspector")
        if session.status != "in_progress":
            raise ConflictProblem("Cannot use powers outside an in-progress game.", code="invalid_state")
        if actor.power_state.inspector_record_inspection_used:
            raise ConflictProblem("Inspector record inspection has already been used.", code="invalid_state")

        eligible_targets = [
            participant for participant in session.participants if participant.life_state in {"dead", "jailed"}
        ]
        if not eligible_targets:
            raise ConflictProblem("No jail or morgue records available yet.", code="invalid_state")
        if actor.user_id == command.target_user_id:
            raise ValueError("Inspector cannot inspect self.")

        target = next((participant for participant in session.participants if participant.user_id == command.target_user_id), None)
        if target is None:
            raise ValueError("Record inspection target not found.")
        if target.life_state not in {"dead", "jailed"}:
            raise ConflictProblem("Record inspection target must be dead or jailed.", code="invalid_state")

        updated_participants = [
            replace(
                participant,
                power_state=replace(
                    participant.power_state,
                    inspector_record_inspection_used=True,
                    inspector_record_visible_until_epoch_seconds=now_epoch_seconds + INSPECTOR_RECORD_VISIBLE_SECONDS,
                    inspector_record_target_user_id=target.user_id,
                    inspector_last_viewed_role_name=target.role_name,
                ),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]
        updated = replace(
            session,
            participants=updated_participants,
            notification_feed=_append_notifications(
                session.notification_feed,
                [(actor.user_id, "Record inspection opened for 60 seconds.")],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_police_officer_confiscation(
        self, command: ActivatePoliceOfficerConfiscationCommand
    ) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Police Officer")
        if actor.power_state.police_officer_confiscation_used:
            raise ConflictProblem("Police Officer confiscation has already been used.", code="invalid_state")
        if actor.power_state.police_officer_confiscation_pending:
            raise ConflictProblem("Confiscation is already armed for the next guilty verdict.", code="invalid_state")
        if not _can_activate_police_officer_confiscation(session):
            raise ConflictProblem(
                "Confiscation can only be activated during information, accused selection, or before all trial votes are submitted.",
                code="invalid_state",
            )

        updated_participants = [
            replace(
                participant,
                power_state=replace(participant.power_state, police_officer_confiscation_pending=True),
            )
            if participant.user_id == actor.user_id
            else participant
            for participant in session.participants
        ]
        updated = replace(
            session,
            participants=updated_participants,
            notification_feed=_append_notifications(
                session.notification_feed,
                [(actor.user_id, "Confiscation has been armed for the next guilty verdict.")],
                now_epoch_seconds=now_epoch_seconds,
            ),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def activate_made_man_skip_middle_man(
        self, command: ActivateMadeManSkipMiddleManCommand
    ) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        _validate_expected_version(command.expected_version, session.version)
        _raise_if_asset_frozen(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=command.actor_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        actor = _require_active_role_participant(session, user_id=command.actor_user_id, role_name="Made Man")
        if actor.power_state.made_man_skip_middle_man_used:
            raise ConflictProblem("Made Man skip middle man has already been used.", code="invalid_state")

        updated = _purchase_from_supply(
            session,
            buyer_user_id=actor.user_id,
            classification=command.classification,
            role_mode="made_man",
            now_epoch_seconds=now_epoch_seconds,
        )
        self._save_game_session(session, updated)
        return updated

    def buy_from_supply(self, command: BuyFromSupplyCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.status != "in_progress" or session.phase != "information":
            raise ConflictProblem("Purchases are only allowed during information phase.", code="invalid_state")
        _raise_if_asset_frozen(
            session,
            user_id=command.buyer_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=command.buyer_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )

        updated = _purchase_from_supply(
            session,
            buyer_user_id=command.buyer_user_id,
            classification=command.classification,
            role_mode="merchant",
            now_epoch_seconds=now_epoch_seconds,
        )
        self._save_game_session(session, updated)
        return updated

    def set_inventory_resale_price(self, command: SetInventoryResalePriceCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.status != "in_progress":
            raise ConflictProblem("Cannot set resale price outside in-progress game.", code="invalid_state")
        if session.phase != "information":
            raise ConflictProblem("Resale price updates are only allowed during information phase.", code="invalid_state")
        _raise_if_asset_frozen(
            session,
            user_id=command.seller_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=command.seller_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )

        resale_price = _round_money_to_nearest_ten(command.resale_price)
        if resale_price < 0:
            raise ValueError("Resale price must be >= 0.")

        participants: list[ParticipantStateSnapshot] = []
        seller_found = False
        inventory_item_found = False
        for participant in session.participants:
            if participant.user_id != command.seller_user_id:
                participants.append(participant)
                continue

            seller_found = True
            if participant.faction != "Merchant":
                raise PermissionError("Only merchants can set resale prices.")
            updated_inventory: list[InventoryItemStateSnapshot] = []
            for inventory_item in participant.inventory:
                if inventory_item.item_id == command.inventory_item_id:
                    inventory_item_found = True
                    updated_inventory.append(replace(inventory_item, resale_price=resale_price))
                else:
                    updated_inventory.append(inventory_item)
            participants.append(replace(participant, inventory=updated_inventory))

        if not seller_found:
            raise ValueError("Seller participant not found in session.")
        if not inventory_item_found:
            raise ValueError("Inventory item not found for merchant.")

        updated = replace(session, participants=participants, version=session.version + 1)
        self._save_game_session(session, updated)
        return updated

    def sell_inventory_item(self, command: SellInventoryItemCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.status != "in_progress" or session.phase != "information":
            raise ConflictProblem("Merchant sales are only allowed during information phase.", code="invalid_state")
        _raise_if_asset_frozen(
            session,
            user_id=command.seller_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_asset_frozen(
            session,
            user_id=command.buyer_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=command.seller_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=command.buyer_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        if command.seller_user_id == command.buyer_user_id:
            raise ValueError("Seller and buyer must be different participants.")

        seller = next((p for p in session.participants if p.user_id == command.seller_user_id), None)
        buyer = next((p for p in session.participants if p.user_id == command.buyer_user_id), None)
        if seller is None:
            raise ValueError("Seller participant not found in session.")
        if buyer is None:
            raise ValueError("Buyer participant not found in session.")
        if seller.faction != "Merchant":
            raise PermissionError("Only merchants can sell inventory items.")
        if seller.life_state != "alive":
            raise ConflictProblem("Only alive merchants can sell inventory items.", code="invalid_state")
        if buyer.life_state != "alive":
            raise ConflictProblem("Buyer must be alive to receive inventory items.", code="invalid_state")

        inventory_item = next((item for item in seller.inventory if item.item_id == command.inventory_item_id), None)
        if inventory_item is None:
            raise ValueError("Inventory item not found for merchant.")

        duplicate_pending = any(
            offer.inventory_item_id == command.inventory_item_id and offer.seller_user_id == command.seller_user_id
            for offer in session.pending_sale_offers
        )
        if duplicate_pending:
            raise ConflictProblem("This item already has a pending sale offer.", code="invalid_state")
        duplicate_gift_pending = any(
            offer.inventory_item_id == command.inventory_item_id and offer.giver_user_id == command.seller_user_id
            for offer in session.pending_gift_offers
        )
        if duplicate_gift_pending:
            raise ConflictProblem("This item already has a pending gift offer.", code="invalid_state")

        new_offer = SaleOfferSnapshot(
            sale_offer_id=f"sale-{str(uuid4())[:8]}",
            seller_user_id=command.seller_user_id,
            buyer_user_id=command.buyer_user_id,
            inventory_item_id=command.inventory_item_id,
            item_display_name=inventory_item.display_name,
            sale_price=inventory_item.resale_price,
            created_at_epoch_seconds=now_epoch_seconds,
        )
        updated = replace(
            session,
            pending_sale_offers=[*session.pending_sale_offers, new_offer],
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def sell_inventory_to_supply(self, command: SellInventoryToSupplyCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.status != "in_progress" or session.phase != "information":
            raise ConflictProblem("Selling to supply is only allowed during information phase.", code="invalid_state")
        _raise_if_asset_frozen(
            session,
            user_id=command.seller_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=command.seller_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )

        seller = next((p for p in session.participants if p.user_id == command.seller_user_id), None)
        if seller is None:
            raise ValueError("Seller participant not found in session.")
        if seller.faction != "Merchant":
            raise PermissionError("Only merchants can sell inventory to supply.")
        if seller.life_state != "alive":
            raise ConflictProblem("Only alive merchants can sell inventory to supply.", code="invalid_state")

        inventory_item = next((item for item in seller.inventory if item.item_id == command.inventory_item_id), None)
        if inventory_item is None:
            raise ValueError("Inventory item not found for merchant.")

        payout = int(inventory_item.acquisition_value * SUPPLY_BUYBACK_PERCENT)
        participants: list[ParticipantStateSnapshot] = []
        for participant in session.participants:
            if participant.user_id == seller.user_id:
                participants.append(
                    replace(
                        participant,
                        money_balance=participant.money_balance + payout,
                        inventory=[item for item in participant.inventory if item.item_id != inventory_item.item_id],
                    )
                )
                continue
            participants.append(participant)

        updated = replace(
            session,
            participants=participants,
            catalog=_reactivate_supply_catalog_item(session.catalog, inventory_item),
            pending_sale_offers=[offer for offer in session.pending_sale_offers if offer.inventory_item_id != inventory_item.item_id],
            pending_gift_offers=[offer for offer in session.pending_gift_offers if offer.inventory_item_id != inventory_item.item_id],
            latest_public_notice=None,
            version=session.version + 1,
        )
        updated = _append_ledger_entries(
            updated,
            [
                _build_ledger_entry(
                    entry_kind="central_supply_buyback",
                    amount=payout,
                    from_holder_id=CENTRAL_SUPPLY_HOLDER_ID,
                    to_holder_id=command.seller_user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    note=f"Supply buyback: {inventory_item.display_name}",
                )
            ],
        )
        updated = self._resolve_information_winner_if_needed(updated, now_epoch_seconds=now_epoch_seconds)
        self._save_game_session(session, updated)
        return updated

    def respond_sale_offer(self, command: RespondSaleOfferCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.status != "in_progress" or session.phase != "information":
            raise ConflictProblem("Cannot respond to sale offers outside information phase.", code="invalid_state")

        offer = next((candidate for candidate in session.pending_sale_offers if candidate.sale_offer_id == command.sale_offer_id), None)
        if offer is None:
            raise ValueError("Sale offer not found.")
        if offer.buyer_user_id != command.buyer_user_id:
            raise PermissionError("Only the addressed buyer can respond to this sale offer.")
        _raise_if_asset_frozen(
            session,
            user_id=offer.buyer_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_asset_frozen(
            session,
            user_id=offer.seller_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=offer.buyer_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=offer.seller_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )

        remaining_offers = [candidate for candidate in session.pending_sale_offers if candidate.sale_offer_id != command.sale_offer_id]
        participant_name_by_id = _participant_name_by_id(session.participants)
        buyer_name = participant_name_by_id.get(offer.buyer_user_id, offer.buyer_user_id)
        seller_name = participant_name_by_id.get(offer.seller_user_id, offer.seller_user_id)
        decline_notice = f"{buyer_name} declined {seller_name}'s sale offer for {offer.item_display_name}."
        if not command.accept:
            updated = replace(
                session,
                pending_sale_offers=remaining_offers,
                latest_public_notice=decline_notice,
                version=session.version + 1,
            )
            self._save_game_session(session, updated)
            return updated

        seller = next((p for p in session.participants if p.user_id == offer.seller_user_id), None)
        buyer = next((p for p in session.participants if p.user_id == offer.buyer_user_id), None)
        if seller is None or buyer is None:
            raise ConflictProblem("Sale-offer participants are no longer in session.", code="invalid_state")
        if seller.life_state != "alive" or buyer.life_state != "alive":
            raise ConflictProblem("Sale transaction requires alive seller and buyer.", code="invalid_state")
        if seller.faction != "Merchant":
            raise ConflictProblem("Sale offer seller is no longer a merchant.", code="invalid_state")

        inventory_item = next((item for item in seller.inventory if item.item_id == offer.inventory_item_id), None)
        if inventory_item is None:
            raise ConflictProblem("Sale item is no longer available in seller inventory.", code="invalid_state")
        if buyer.money_balance < inventory_item.resale_price:
            updated = replace(
                session,
                pending_sale_offers=remaining_offers,
                latest_public_notice=decline_notice,
                version=session.version + 1,
            )
            self._save_game_session(session, updated)
            raise ConflictProblem("Buyer has insufficient funds for this purchase.", code="invalid_state")

        participants: list[ParticipantStateSnapshot] = []
        for participant in session.participants:
            if participant.user_id == seller.user_id:
                participants.append(
                    replace(
                        participant,
                        money_balance=participant.money_balance + inventory_item.resale_price,
                        inventory=[item for item in participant.inventory if item.item_id != inventory_item.item_id],
                    )
                )
                continue
            if participant.user_id == buyer.user_id:
                participants.append(
                    replace(
                        participant,
                        money_balance=participant.money_balance - inventory_item.resale_price,
                        inventory=[*participant.inventory, inventory_item],
                    )
                )
                continue
            participants.append(participant)

        updated = replace(
            session,
            participants=participants,
            pending_sale_offers=remaining_offers,
            pending_gift_offers=[offer for offer in session.pending_gift_offers if offer.inventory_item_id != inventory_item.item_id],
            latest_public_notice=None,
            version=session.version + 1,
        )
        updated = _append_ledger_entries(
            updated,
            [
                _build_ledger_entry(
                    entry_kind="participant_sale",
                    amount=inventory_item.resale_price,
                    from_holder_id=buyer.user_id,
                    to_holder_id=seller.user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    note=f"Participant sale: {inventory_item.display_name}",
                )
            ],
        )
        updated = _append_player_transactions(
            updated,
            [
                _build_player_transaction(
                    transaction_kind="sale",
                    sender_user_id=seller.user_id,
                    recipient_user_id=buyer.user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    money_amount=inventory_item.resale_price,
                    item_name=inventory_item.display_name,
                )
            ],
        )
        updated = _apply_supplier_acquire_if_needed(
            updated,
            seller_user_id=seller.user_id,
            sale_price=inventory_item.resale_price,
            moderator_user_id=session.moderator_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        updated = _apply_gun_runner_charisma_bonus_if_needed(
            updated,
            seller_user_id=seller.user_id,
            sale_price=inventory_item.resale_price,
            now_epoch_seconds=now_epoch_seconds,
        )
        updated = self._resolve_information_winner_if_needed(updated, now_epoch_seconds=now_epoch_seconds)
        self._save_game_session(session, updated)
        return updated

    def offer_gift_item(self, command: OfferGiftItemCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.status != "in_progress" or session.phase != "information":
            raise ConflictProblem("Gifting is only allowed during information phase.", code="invalid_state")
        _raise_if_asset_frozen(
            session,
            user_id=command.giver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_asset_frozen(
            session,
            user_id=command.receiver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=command.giver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=command.receiver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        if command.giver_user_id == command.receiver_user_id:
            raise ValueError("Giver and receiver must be different participants.")

        giver = next((p for p in session.participants if p.user_id == command.giver_user_id), None)
        receiver = next((p for p in session.participants if p.user_id == command.receiver_user_id), None)
        if giver is None:
            raise ValueError("Giver participant not found in session.")
        if receiver is None:
            raise ValueError("Receiver participant not found in session.")
        if giver.life_state != "alive" or receiver.life_state != "alive":
            raise ConflictProblem("Gift transfers require alive giver and receiver.", code="invalid_state")

        gift_item = next((item for item in giver.inventory if item.item_id == command.inventory_item_id), None)
        if gift_item is None:
            raise ValueError("Inventory item not found for giver.")

        duplicate_pending = any(
            offer.inventory_item_id == command.inventory_item_id and offer.giver_user_id == command.giver_user_id
            for offer in session.pending_gift_offers
        )
        if duplicate_pending:
            raise ConflictProblem("This item already has a pending gift offer.", code="invalid_state")
        duplicate_sale_pending = any(
            offer.inventory_item_id == command.inventory_item_id and offer.seller_user_id == command.giver_user_id
            for offer in session.pending_sale_offers
        )
        if duplicate_sale_pending:
            raise ConflictProblem("This item already has a pending sale offer.", code="invalid_state")

        new_offer = GiftOfferSnapshot(
            gift_offer_id=f"gift-{str(uuid4())[:8]}",
            giver_user_id=command.giver_user_id,
            receiver_user_id=command.receiver_user_id,
            inventory_item_id=command.inventory_item_id,
            item_display_name=gift_item.display_name,
            created_at_epoch_seconds=now_epoch_seconds,
        )
        updated = replace(
            session,
            pending_gift_offers=[*session.pending_gift_offers, new_offer],
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def respond_gift_offer(self, command: RespondGiftOfferCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.status != "in_progress" or session.phase != "information":
            raise ConflictProblem("Cannot respond to gift offers outside information phase.", code="invalid_state")

        offer = next((candidate for candidate in session.pending_gift_offers if candidate.gift_offer_id == command.gift_offer_id), None)
        if offer is None:
            raise ValueError("Gift offer not found.")
        if offer.receiver_user_id != command.receiver_user_id:
            raise PermissionError("Only the addressed receiver can respond to this gift offer.")
        _raise_if_asset_frozen(
            session,
            user_id=offer.receiver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_asset_frozen(
            session,
            user_id=offer.giver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=offer.receiver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=offer.giver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )

        remaining_offers = [candidate for candidate in session.pending_gift_offers if candidate.gift_offer_id != command.gift_offer_id]
        if not command.accept:
            updated = replace(session, pending_gift_offers=remaining_offers, version=session.version + 1)
            self._save_game_session(session, updated)
            return updated

        giver = next((p for p in session.participants if p.user_id == offer.giver_user_id), None)
        receiver = next((p for p in session.participants if p.user_id == offer.receiver_user_id), None)
        if giver is None or receiver is None:
            raise ConflictProblem("Gift offer participants are no longer in session.", code="invalid_state")
        if giver.life_state != "alive" or receiver.life_state != "alive":
            raise ConflictProblem("Gift transfer requires alive giver and receiver.", code="invalid_state")

        gift_item = next((item for item in giver.inventory if item.item_id == offer.inventory_item_id), None)
        if gift_item is None:
            raise ConflictProblem("Gift item is no longer available in giver inventory.", code="invalid_state")

        participants: list[ParticipantStateSnapshot] = []
        for participant in session.participants:
            if participant.user_id == giver.user_id:
                participants.append(
                    replace(participant, inventory=[item for item in participant.inventory if item.item_id != gift_item.item_id])
                )
                continue
            if participant.user_id == receiver.user_id:
                participants.append(replace(participant, inventory=[*participant.inventory, gift_item]))
                continue
            participants.append(participant)

        updated = replace(
            session,
            participants=participants,
            pending_gift_offers=remaining_offers,
            pending_sale_offers=[offer for offer in session.pending_sale_offers if offer.inventory_item_id != gift_item.item_id],
            version=session.version + 1,
        )
        updated = _append_player_transactions(
            updated,
            [
                _build_player_transaction(
                    transaction_kind="item_gift",
                    sender_user_id=giver.user_id,
                    recipient_user_id=receiver.user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    item_name=gift_item.display_name,
                )
            ],
        )
        self._save_game_session(session, updated)
        return updated

    def give_money(self, command: GiveMoneyCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.status != "in_progress" or session.phase != "information":
            raise ConflictProblem("Money gifting is only allowed during information phase.", code="invalid_state")
        _raise_if_asset_frozen(
            session,
            user_id=command.giver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_asset_frozen(
            session,
            user_id=command.receiver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=command.giver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=command.receiver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        if command.giver_user_id == command.receiver_user_id:
            raise ValueError("Giver and receiver must be different participants.")
        if command.amount <= 0:
            raise ValueError("Amount must be greater than 0.")

        giver = next((p for p in session.participants if p.user_id == command.giver_user_id), None)
        receiver = next((p for p in session.participants if p.user_id == command.receiver_user_id), None)
        if giver is None:
            raise ValueError("Giver participant not found in session.")
        if receiver is None:
            raise ValueError("Receiver participant not found in session.")
        if giver.life_state != "alive" or receiver.life_state != "alive":
            raise ConflictProblem("Money transfer requires alive giver and receiver.", code="invalid_state")
        if giver.money_balance < command.amount:
            raise ConflictProblem("Giver has insufficient funds.", code="invalid_state")

        new_offer = MoneyGiftOfferSnapshot(
            money_gift_offer_id=f"money-gift-{str(uuid4())[:8]}",
            giver_user_id=command.giver_user_id,
            receiver_user_id=command.receiver_user_id,
            amount=command.amount,
            created_at_epoch_seconds=now_epoch_seconds,
        )

        updated = replace(
            session,
            pending_money_gift_offers=[*session.pending_money_gift_offers, new_offer],
            latest_public_notice=None,
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def respond_money_gift_offer(self, command: RespondMoneyGiftOfferCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.status != "in_progress" or session.phase != "information":
            raise ConflictProblem("Cannot respond to money gift offers outside information phase.", code="invalid_state")

        offer = next(
            (candidate for candidate in session.pending_money_gift_offers if candidate.money_gift_offer_id == command.money_gift_offer_id),
            None,
        )
        if offer is None:
            raise ValueError("Money gift offer not found.")
        if offer.receiver_user_id != command.receiver_user_id:
            raise PermissionError("Only the addressed receiver can respond to this money gift offer.")
        _raise_if_asset_frozen(
            session,
            user_id=offer.receiver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_asset_frozen(
            session,
            user_id=offer.giver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=offer.receiver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        _raise_if_sergeant_captured(
            session,
            user_id=offer.giver_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )

        remaining_offers = [
            candidate for candidate in session.pending_money_gift_offers if candidate.money_gift_offer_id != command.money_gift_offer_id
        ]
        if not command.accept:
            updated = replace(session, pending_money_gift_offers=remaining_offers, version=session.version + 1)
            self._save_game_session(session, updated)
            return updated

        giver = next((p for p in session.participants if p.user_id == offer.giver_user_id), None)
        receiver = next((p for p in session.participants if p.user_id == offer.receiver_user_id), None)
        if giver is None or receiver is None:
            raise ConflictProblem("Money-gift participants are no longer in session.", code="invalid_state")
        if giver.life_state != "alive" or receiver.life_state != "alive":
            raise ConflictProblem("Money transfer requires alive giver and receiver.", code="invalid_state")
        if giver.money_balance < offer.amount:
            updated = replace(session, pending_money_gift_offers=remaining_offers, version=session.version + 1)
            self._save_game_session(session, updated)
            raise ConflictProblem("Giver has insufficient funds.", code="invalid_state")

        participants: list[ParticipantStateSnapshot] = []
        for participant in session.participants:
            if participant.user_id == giver.user_id:
                participants.append(replace(participant, money_balance=participant.money_balance - offer.amount))
                continue
            if participant.user_id == receiver.user_id:
                participants.append(replace(participant, money_balance=participant.money_balance + offer.amount))
                continue
            participants.append(participant)

        updated = replace(
            session,
            participants=participants,
            pending_money_gift_offers=remaining_offers,
            latest_public_notice=None,
            version=session.version + 1,
        )
        updated = _append_ledger_entries(
            updated,
            [
                _build_ledger_entry(
                    entry_kind="money_gift",
                    amount=offer.amount,
                    from_holder_id=giver.user_id,
                    to_holder_id=receiver.user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    note="Accepted money gift offer.",
                )
            ],
        )
        updated = _append_player_transactions(
            updated,
            [
                _build_player_transaction(
                    transaction_kind="money_gift",
                    sender_user_id=giver.user_id,
                    recipient_user_id=receiver.user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    money_amount=offer.amount,
                )
            ],
        )
        updated = self._resolve_information_winner_if_needed(updated, now_epoch_seconds=now_epoch_seconds)
        self._save_game_session(session, updated)
        return updated

    def kill_game(self, command: KillGameCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        if command.requested_by_user_id != session.moderator_user_id:
            raise PermissionError("Only moderator can kill the game.")
        if session.status == "ended":
            return session
        now_epoch_seconds = self._now_epoch_seconds()
        updated = replace(
            session,
            status="ended",
            phase="ended",
            ended_at_epoch_seconds=now_epoch_seconds,
            latest_public_notice="Game ended by moderator.",
            winning_faction=None,
            winning_user_id=None,
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def submit_accused_selection(self, command: SubmitAccusedSelectionCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        now_epoch_seconds = self._now_epoch_seconds()
        if command.expected_version != session.version:
            raise ConflictProblem(
                detail=(
                    "Game state changed before this mutation was applied. "
                    f"Expected version {command.expected_version}, current is {session.version}."
                ),
                code="version_conflict",
                extensions={
                    "expected_version": command.expected_version,
                    "current_version": session.version,
                },
            )
        if session.phase != "accused_selection" or session.pending_trial is None:
            raise ConflictProblem("Accused selection is only valid during accused_selection phase.", code="invalid_state")
        _raise_if_sergeant_captured(
            session,
            user_id=command.selected_by_user_id,
            now_epoch_seconds=now_epoch_seconds,
        )

        pending_trial = session.pending_trial
        if not pending_trial.accused_selection_cursor:
            raise ConflictProblem("No active accused-selection responder.", code="invalid_state")
        if pending_trial.accused_selection_cursor[0] != command.selected_by_user_id:
            raise PermissionError("Only current accused-selection responder can choose the accused player.")

        accused_participant = next((p for p in session.participants if p.user_id == command.accused_user_id), None)
        if accused_participant is None or accused_participant.life_state != "alive":
            raise ValueError("Accused participant must be alive.")

        excluded_user_ids: set[str] = set()
        captured_user_id = _active_sergeant_capture_target_user_id(session, now_epoch_seconds=now_epoch_seconds)
        if captured_user_id:
            excluded_user_ids.add(captured_user_id)
        jury_user_ids = _select_trial_jury_user_ids(
            session.participants,
            accused_user_id=command.accused_user_id,
            excluded_user_ids=excluded_user_ids,
        )
        next_pending_trial = replace(
            pending_trial,
            accused_user_id=command.accused_user_id,
            accused_by_user_id=command.selected_by_user_id,
            accused_selection_cursor=[],
            accused_selection_deadline_epoch_seconds=None,
            jury_user_ids=jury_user_ids,
            votes=[],
            vote_deadline_epoch_seconds=None,
            resolution=None,
        )
        updated = replace(
            session,
            pending_trial=next_pending_trial,
            phase="trial_voting",
            latest_jury_log_user_ids=list(jury_user_ids),
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def _resolve_boundary_if_needed(
        self, session: GameDetailsSnapshot, *, now_epoch_seconds: int
    ) -> GameDetailsSnapshot:
        if session.phase != "boundary_resolution":
            return session

        winner_faction, winner_user_id = _determine_boundary_winner(session)
        if winner_faction is not None:
            winner_notice = _build_winner_notice(session, winner_faction=winner_faction, winner_user_id=winner_user_id)
            return replace(
                session,
                phase="ended",
                status="ended",
                ended_at_epoch_seconds=now_epoch_seconds,
                winning_faction=winner_faction,
                winning_user_id=winner_user_id,
                latest_public_notice=winner_notice,
                latest_private_notice_user_id=None,
                latest_private_notice_message=None,
                pending_gift_offers=[],
                pending_money_gift_offers=[],
                pending_sale_offers=[],
            )

        continuation_notice, private_notice_user_id, private_notice_message = _build_trial_outcome_notices(
            session.participants,
            session.pending_trial,
            police_leader_user_id=session.current_police_leader_user_id,
            mob_leader_user_id=session.current_mob_leader_user_id,
        )
        return replace(
            session,
            phase="information",
            round_number=session.round_number + 1,
            pending_trial=None,
            latest_public_notice=continuation_notice,
            latest_private_notice_user_id=private_notice_user_id,
            latest_private_notice_message=private_notice_message,
            pending_gift_offers=[],
            pending_money_gift_offers=[],
            pending_sale_offers=[],
        )

    def _resolve_information_winner_if_needed(
        self, session: GameDetailsSnapshot, *, now_epoch_seconds: int
    ) -> GameDetailsSnapshot:
        if session.status != "in_progress":
            return session

        merchant_winner_user_id = _find_merchant_winner_user_id(session.participants)
        if merchant_winner_user_id is None:
            return session

        winner_notice = _build_winner_notice(session, winner_faction="Merchant", winner_user_id=merchant_winner_user_id)
        return replace(
            session,
            phase="ended",
            status="ended",
            ended_at_epoch_seconds=now_epoch_seconds,
            winning_faction="Merchant",
            winning_user_id=merchant_winner_user_id,
            latest_public_notice=winner_notice,
            latest_private_notice_user_id=None,
            latest_private_notice_message=None,
            pending_gift_offers=[],
            pending_money_gift_offers=[],
            pending_sale_offers=[],
        )

    def _now_epoch_seconds(self) -> int:
        return int(self._now_epoch_seconds_provider())

    def _auto_end_if_inactive(
        self,
        session: GameDetailsSnapshot,
        *,
        now_epoch_seconds: int,
    ) -> GameDetailsSnapshot:
        if session.status != "in_progress":
            return session
        last_progressed_at = session.last_progressed_at_epoch_seconds or session.launched_at_epoch_seconds
        if now_epoch_seconds - last_progressed_at < INACTIVITY_AUTO_END_SECONDS:
            return session

        updated = replace(
            session,
            status="ended",
            phase="ended",
            ended_at_epoch_seconds=now_epoch_seconds,
            latest_public_notice="Game automatically ended after 24 hours of inactivity.",
            latest_private_notice_user_id=None,
            latest_private_notice_message=None,
            pending_gift_offers=[],
            pending_money_gift_offers=[],
            pending_sale_offers=[],
            version=session.version + 1,
        )
        self._save_game_session(session, updated)
        return updated

    def _save_game_session(self, previous: GameDetailsSnapshot, updated: GameDetailsSnapshot) -> None:
        final_updated = _resolve_supplier_acquire_state_if_needed(
            updated,
            now_epoch_seconds=self._now_epoch_seconds(),
        )
        final_updated = _apply_cop_last_three_protection_if_needed(
            final_updated,
            now_epoch_seconds=self._now_epoch_seconds(),
        )
        final_updated = _refresh_ledger(final_updated)
        final_updated = replace(
            final_updated,
            last_progressed_at_epoch_seconds=self._now_epoch_seconds(),
        )
        if final_updated is not updated:
            for field in fields(GameDetailsSnapshot):
                object.__setattr__(updated, field.name, getattr(final_updated, field.name))
        self._repository.save_game_session(final_updated)
        self._sync_room_lifecycle_if_needed(previous, final_updated)

    def _sync_room_lifecycle_if_needed(self, previous: GameDetailsSnapshot, updated: GameDetailsSnapshot) -> None:
        if self._room_lifecycle_outbound_port is None:
            return
        if previous.status == "ended":
            return
        if updated.status != "ended":
            return
        self._room_lifecycle_outbound_port.mark_room_ended_for_game(
            room_id=updated.room_id,
            game_id=updated.game_id,
        )


def _validate_expected_version(expected_version: int, current_version: int) -> None:
    if expected_version != current_version:
        raise ConflictProblem(
            detail=(
                "Game state changed before this mutation was applied. "
                f"Expected version {expected_version}, current is {current_version}."
            ),
            code="version_conflict",
            extensions={
                "expected_version": expected_version,
                "current_version": current_version,
            },
        )


def _require_active_role_participant(
    session: GameDetailsSnapshot, *, user_id: str, role_name: str
) -> ParticipantStateSnapshot:
    participant = next((candidate for candidate in session.participants if candidate.user_id == user_id), None)
    if participant is None:
        raise ValueError("Participant not found in session.")
    if participant.role_name != role_name:
        raise PermissionError(f"Only {role_name} can use this power.")
    if participant.life_state != "alive":
        raise ConflictProblem("Power is unavailable because you are not alive.", code="invalid_state")
    if session.status != "in_progress":
        raise ConflictProblem("Cannot use powers outside an in-progress game.", code="invalid_state")
    return participant


def _append_notifications(
    notification_feed: list[NotificationEventSnapshot],
    notifications: list[tuple[str, str]],
    *,
    now_epoch_seconds: int,
) -> list[NotificationEventSnapshot]:
    appended = list(notification_feed)
    for user_id, message in notifications:
        appended.append(
            NotificationEventSnapshot(
                event_id=f"evt-{str(uuid4())[:8]}",
                user_id=user_id,
                message=message,
                created_at_epoch_seconds=now_epoch_seconds,
            )
        )
    return appended


def _active_protective_custody_target_user_id(
    session: GameDetailsSnapshot,
    *,
    now_epoch_seconds: int,
) -> str | None:
    target_user_id = session.protective_custody_user_id
    expiry_epoch_seconds = session.protective_custody_expires_at_epoch_seconds
    if not target_user_id or expiry_epoch_seconds is None:
        return None
    if now_epoch_seconds >= expiry_epoch_seconds:
        return None
    target = next((participant for participant in session.participants if participant.user_id == target_user_id), None)
    if target is None or target.life_state != "alive":
        return None
    return target_user_id


def _active_asset_freeze_target_user_id(
    session: GameDetailsSnapshot,
    *,
    now_epoch_seconds: int,
) -> str | None:
    target_user_id = session.asset_freeze_user_id
    expiry_epoch_seconds = session.asset_freeze_expires_at_epoch_seconds
    if not target_user_id or expiry_epoch_seconds is None:
        return None
    if now_epoch_seconds >= expiry_epoch_seconds:
        return None
    target = next((participant for participant in session.participants if participant.user_id == target_user_id), None)
    if target is None or target.life_state != "alive":
        return None
    return target_user_id


def _build_asset_freeze_blocked_message(target_username: str) -> str:
    return (
        f"{target_username}'s accounts have been temporarily frozen by the police department, "
        "no transactions can go through at this time."
    )


def _raise_if_asset_frozen(
    session: GameDetailsSnapshot,
    *,
    user_id: str,
    now_epoch_seconds: int,
) -> None:
    frozen_target_user_id = _active_asset_freeze_target_user_id(
        session,
        now_epoch_seconds=now_epoch_seconds,
    )
    if frozen_target_user_id != user_id:
        return
    participant_name_by_id = _participant_name_by_id(session.participants)
    target_username = participant_name_by_id.get(user_id, user_id)
    raise ConflictProblem(
        _build_asset_freeze_blocked_message(target_username),
        code="invalid_state",
    )


def _active_sergeant_capture_target_user_id(
    session: GameDetailsSnapshot,
    *,
    now_epoch_seconds: int,
) -> str | None:
    target_user_id = session.sergeant_capture_user_id
    expiry_epoch_seconds = session.sergeant_capture_expires_at_epoch_seconds
    if not target_user_id or expiry_epoch_seconds is None:
        return None
    if now_epoch_seconds >= expiry_epoch_seconds:
        return None
    target = next((participant for participant in session.participants if participant.user_id == target_user_id), None)
    if target is None or target.life_state != "alive":
        return None
    return target_user_id


def _raise_if_sergeant_captured(
    session: GameDetailsSnapshot,
    *,
    user_id: str,
    now_epoch_seconds: int,
) -> None:
    captured_user_id = _active_sergeant_capture_target_user_id(
        session,
        now_epoch_seconds=now_epoch_seconds,
    )
    if captured_user_id != user_id:
        return
    raise ConflictProblem("You are in police custody and cannot perform this action right now.", code="invalid_state")


def _resolve_supplier_acquire_state_if_needed(
    session: GameDetailsSnapshot,
    *,
    now_epoch_seconds: int,
) -> GameDetailsSnapshot:
    acquire_state = _supplier_acquire_state(session)
    if acquire_state is None:
        return session
    supplier, target_user_id = acquire_state
    target = next((participant for participant in session.participants if participant.user_id == target_user_id), None)

    cancel_message: str | None = None
    moderator_message: str | None = None
    if supplier.life_state != "alive":
        cancel_message = "Acquire was canceled because you were no longer active."
        moderator_message = f"{supplier.username}'s Acquire was canceled because the Supplier was no longer active."
    elif _active_asset_freeze_target_user_id(session, now_epoch_seconds=now_epoch_seconds) == supplier.user_id:
        cancel_message = "Acquire was canceled because your accounts are frozen."
        moderator_message = f"{supplier.username}'s Acquire was canceled because the Supplier is frozen."
    elif _active_sergeant_capture_target_user_id(session, now_epoch_seconds=now_epoch_seconds) == supplier.user_id:
        cancel_message = "Acquire was canceled because you entered police custody."
        moderator_message = f"{supplier.username}'s Acquire was canceled because the Supplier entered police custody."
    elif target is None or target.life_state != "alive":
        target_label = target.username if target is not None else target_user_id
        cancel_message = f"Acquire failed because {target_label} was eliminated before completing a successful sale."
        moderator_message = f"{supplier.username}'s Acquire failed because {target_label} was eliminated before selling."

    if cancel_message is None or moderator_message is None:
        return session

    return replace(
        session,
        participants=[
            replace(
                participant,
                power_state=replace(participant.power_state, supplier_acquire_target_user_id=None),
            )
            if participant.user_id == supplier.user_id
            else participant
            for participant in session.participants
        ],
        notification_feed=_append_notifications(
            session.notification_feed,
            [
                (supplier.user_id, cancel_message),
                (session.moderator_user_id, moderator_message),
            ],
            now_epoch_seconds=now_epoch_seconds,
        ),
    )


def _adjust_participant_money_balance(
    participants: list[ParticipantStateSnapshot],
    *,
    user_id: str,
    delta: int,
) -> list[ParticipantStateSnapshot]:
    updated: list[ParticipantStateSnapshot] = []
    for participant in participants:
        if participant.user_id == user_id:
            updated.append(replace(participant, money_balance=participant.money_balance + delta))
            continue
        updated.append(participant)
    return updated


def _build_ledger_entry(
    *,
    entry_kind: str,
    amount: int,
    from_holder_id: str,
    to_holder_id: str,
    now_epoch_seconds: int,
    note: str | None = None,
) -> LedgerEntrySnapshot:
    return LedgerEntrySnapshot(
        entry_id=f"led-{str(uuid4())[:8]}",
        entry_kind=entry_kind,
        amount=amount,
        from_holder_id=from_holder_id,
        to_holder_id=to_holder_id,
        created_at_epoch_seconds=now_epoch_seconds,
        note=note,
    )


def _append_ledger_entries(
    session: GameDetailsSnapshot,
    entries: list[LedgerEntrySnapshot],
) -> GameDetailsSnapshot:
    if not entries:
        return session
    return replace(
        session,
        ledger=replace(
            session.ledger,
            entries=[*session.ledger.entries, *entries],
        ),
    )


def _build_player_transaction(
    *,
    transaction_kind: str,
    sender_user_id: str,
    recipient_user_id: str,
    now_epoch_seconds: int,
    money_amount: int = 0,
    item_name: str | None = None,
) -> PlayerTransactionSnapshot:
    return PlayerTransactionSnapshot(
        transaction_id=f"txn-{str(uuid4())[:8]}",
        transaction_kind=transaction_kind,
        sender_user_id=sender_user_id,
        recipient_user_id=recipient_user_id,
        created_at_epoch_seconds=now_epoch_seconds,
        money_amount=money_amount,
        item_name=item_name,
    )


def _append_player_transactions(
    session: GameDetailsSnapshot,
    transactions: list[PlayerTransactionSnapshot],
) -> GameDetailsSnapshot:
    if not transactions:
        return session
    return replace(session, player_transactions=[*session.player_transactions, *transactions])


def _locked_inventory_item_ids_for_participant(
    session: GameDetailsSnapshot,
    *,
    participant_user_id: str,
) -> set[str]:
    locked_item_ids: set[str] = set()
    for offer in session.pending_sale_offers:
        if offer.seller_user_id == participant_user_id:
            locked_item_ids.add(offer.inventory_item_id)
    for offer in session.pending_gift_offers:
        if offer.giver_user_id == participant_user_id:
            locked_item_ids.add(offer.inventory_item_id)
    return locked_item_ids


def _active_gun_runner_charisma_expires_at(
    participant: ParticipantStateSnapshot,
    *,
    now_epoch_seconds: int,
) -> int | None:
    expires_at = participant.power_state.gun_runner_charisma_expires_at_epoch_seconds
    if expires_at is None or now_epoch_seconds >= expires_at:
        return None
    return expires_at


def _apply_gun_runner_charisma_bonus_if_needed(
    session: GameDetailsSnapshot,
    *,
    seller_user_id: str,
    sale_price: int,
    now_epoch_seconds: int,
) -> GameDetailsSnapshot:
    seller = next((participant for participant in session.participants if participant.user_id == seller_user_id), None)
    if seller is None or seller.role_name != "Gun Runner":
        return session
    if _active_gun_runner_charisma_expires_at(seller, now_epoch_seconds=now_epoch_seconds) is None:
        return session

    bonus_amount = _round_money_to_nearest_ten((sale_price * GUN_RUNNER_CHARISMA_BONUS_PERCENT) // 100)
    if bonus_amount <= 0:
        return session

    updated = replace(
        session,
        participants=[
            replace(participant, money_balance=participant.money_balance + bonus_amount)
            if participant.user_id == seller_user_id
            else participant
            for participant in session.participants
        ],
        notification_feed=_append_notifications(
            session.notification_feed,
            [
                (
                    seller_user_id,
                    f"Charisma paid an extra ${bonus_amount} bonus on your accepted sale.",
                ),
                (
                    session.moderator_user_id,
                    f"Gun Runner Charisma paid ${bonus_amount} to {seller.username} on an accepted sale.",
                ),
            ],
            now_epoch_seconds=now_epoch_seconds,
        ),
    )
    return _append_ledger_entries(
        updated,
        [
            _build_ledger_entry(
                entry_kind="gun_runner_charisma_bonus",
                amount=bonus_amount,
                from_holder_id=CENTRAL_SUPPLY_HOLDER_ID,
                to_holder_id=seller_user_id,
                now_epoch_seconds=now_epoch_seconds,
                note="Gun Runner Charisma bonus.",
            )
        ],
    )


def _supplier_acquire_state(
    session: GameDetailsSnapshot,
) -> tuple[ParticipantStateSnapshot, str] | None:
    supplier = next((participant for participant in session.participants if participant.role_name == "Supplier"), None)
    if supplier is None:
        return None
    target_user_id = supplier.power_state.supplier_acquire_target_user_id
    if not target_user_id:
        return None
    return supplier, target_user_id


def _apply_supplier_acquire_if_needed(
    session: GameDetailsSnapshot,
    *,
    seller_user_id: str,
    sale_price: int,
    moderator_user_id: str,
    now_epoch_seconds: int,
) -> GameDetailsSnapshot:
    acquire_state = _supplier_acquire_state(session)
    if acquire_state is None:
        return session
    supplier, target_user_id = acquire_state
    if target_user_id != seller_user_id:
        return session
    if supplier.life_state != "alive":
        return session
    if _active_asset_freeze_target_user_id(session, now_epoch_seconds=now_epoch_seconds) == supplier.user_id:
        return session
    if _active_sergeant_capture_target_user_id(session, now_epoch_seconds=now_epoch_seconds) == supplier.user_id:
        return session

    stolen_amount = _round_money_to_nearest_ten((sale_price * SUPPLIER_ACQUIRE_STEAL_PERCENT) // 100)
    updated = replace(
        session,
        participants=[
            replace(
                participant,
                money_balance=participant.money_balance + stolen_amount,
                power_state=replace(participant.power_state, supplier_acquire_target_user_id=None),
            )
            if participant.user_id == supplier.user_id
            else (
                replace(participant, money_balance=participant.money_balance - stolen_amount)
                if participant.user_id == seller_user_id
                else participant
            )
            for participant in session.participants
        ],
        notification_feed=_append_notifications(
            session.notification_feed,
            [
                (
                    supplier.user_id,
                    f"Acquire stole ${stolen_amount} from {next((participant.username for participant in session.participants if participant.user_id == seller_user_id), seller_user_id)}'s sale.",
                ),
                (
                    seller_user_id,
                    f"Acquire stole ${stolen_amount} from your transaction and redirected it to {supplier.username}.",
                ),
                (
                    moderator_user_id,
                    f"Supplier Acquire stole ${stolen_amount} from {next((participant.username for participant in session.participants if participant.user_id == seller_user_id), seller_user_id)}'s sale and redirected it to {supplier.username}.",
                ),
            ],
            now_epoch_seconds=now_epoch_seconds,
        ),
    )
    return _append_ledger_entries(
        updated,
        [
            _build_ledger_entry(
                entry_kind="supplier_acquire_cut",
                amount=stolen_amount,
                from_holder_id=seller_user_id,
                to_holder_id=supplier.user_id,
                now_epoch_seconds=now_epoch_seconds,
                note="Supplier Acquire sale cut.",
            )
        ],
    )


def _build_detective_transaction_history(session: GameDetailsSnapshot) -> list[PlayerTransactionSnapshot]:
    participant_ids = {participant.user_id for participant in session.participants}
    transaction_by_key: dict[tuple[object, ...], PlayerTransactionSnapshot] = {}

    for transaction in session.player_transactions:
        if transaction.sender_user_id not in participant_ids or transaction.recipient_user_id not in participant_ids:
            continue
        transaction_by_key[_player_transaction_dedupe_key(transaction)] = transaction

    for entry in session.ledger.entries:
        transaction = _player_transaction_from_ledger_entry(entry, participant_ids=participant_ids)
        if transaction is None:
            continue
        transaction_by_key.setdefault(_player_transaction_dedupe_key(transaction), transaction)

    return sorted(
        transaction_by_key.values(),
        key=lambda transaction: transaction.created_at_epoch_seconds,
    )


def _player_transaction_from_ledger_entry(
    entry: LedgerEntrySnapshot,
    *,
    participant_ids: set[str],
) -> PlayerTransactionSnapshot | None:
    if entry.from_holder_id not in participant_ids or entry.to_holder_id not in participant_ids:
        return None
    if entry.entry_kind == "participant_sale":
        return PlayerTransactionSnapshot(
            transaction_id=f"legacy-{entry.entry_id}",
            transaction_kind="sale",
            sender_user_id=entry.to_holder_id,
            recipient_user_id=entry.from_holder_id,
            created_at_epoch_seconds=entry.created_at_epoch_seconds,
            money_amount=entry.amount,
            item_name=_item_name_from_ledger_note(entry.note),
        )
    if entry.entry_kind == "money_gift":
        return PlayerTransactionSnapshot(
            transaction_id=f"legacy-{entry.entry_id}",
            transaction_kind="money_gift",
            sender_user_id=entry.from_holder_id,
            recipient_user_id=entry.to_holder_id,
            created_at_epoch_seconds=entry.created_at_epoch_seconds,
            money_amount=entry.amount,
        )
    return None


def _player_transaction_dedupe_key(transaction: PlayerTransactionSnapshot) -> tuple[object, ...]:
    return (
        transaction.transaction_kind,
        transaction.sender_user_id,
        transaction.recipient_user_id,
        transaction.created_at_epoch_seconds,
        transaction.money_amount,
        transaction.item_name or "",
    )


def _item_name_from_ledger_note(note: str | None) -> str | None:
    if note is None:
        return None
    prefix = "Participant sale: "
    if note.startswith(prefix):
        return note[len(prefix) :].strip() or None
    return None


def _refresh_ledger(session: GameDetailsSnapshot) -> GameDetailsSnapshot:
    expected_participant_total = _expected_participant_currency_total(session.ledger)
    actual_participant_total = sum(max(participant.money_balance, 0) for participant in session.participants)
    if actual_participant_total != expected_participant_total:
        raise ValueError(
            "Gameplay ledger reconciliation failed. "
            f"Expected participant total {expected_participant_total}, actual {actual_participant_total}."
        )
    checksum = _build_ledger_checksum(session)
    return replace(session, ledger=replace(session.ledger, checksum=checksum))


def _expected_participant_currency_total(ledger: LedgerStateSnapshot) -> int:
    total = ledger.circulating_currency_baseline
    for entry in ledger.entries:
        if entry.to_holder_id == CENTRAL_SUPPLY_HOLDER_ID:
            total -= entry.amount
        if entry.from_holder_id == CENTRAL_SUPPLY_HOLDER_ID:
            total += entry.amount
    return total


def _build_ledger_checksum(session: GameDetailsSnapshot) -> str:
    participant_balances = sorted(
        (participant.user_id, participant.money_balance)
        for participant in session.participants
    )
    entry_rows = [
        (
            entry.entry_id,
            entry.entry_kind,
            entry.amount,
            entry.from_holder_id,
            entry.to_holder_id,
            entry.created_at_epoch_seconds,
            entry.note,
        )
        for entry in session.ledger.entries
    ]
    checksum_payload = {
        "baseline": session.ledger.circulating_currency_baseline,
        "participants": participant_balances,
        "entries": entry_rows,
    }
    return hashlib.sha256(str(checksum_payload).encode("utf-8")).hexdigest()


def _current_trial_key(session: GameDetailsSnapshot) -> str:
    pending_trial = session.pending_trial
    if pending_trial is None:
        return ""
    return f"{session.round_number}:{pending_trial.murdered_user_id}:{pending_trial.accused_user_id or 'pending'}"


def _trial_final_vote_deadline_epoch_seconds(pending_trial: TrialStateSnapshot) -> int | None:
    deadlines = [
        deadline
        for deadline in [
            pending_trial.vote_deadline_epoch_seconds,
            pending_trial.gangster_tamper_vote_deadline_epoch_seconds,
        ]
        if deadline is not None
    ]
    if not deadlines:
        return None
    return max(deadlines)


def _is_gangster_tamper_active(
    session: GameDetailsSnapshot,
    pending_trial: TrialStateSnapshot,
    *,
    now_epoch_seconds: int,
) -> bool:
    actor_user_id = pending_trial.gangster_tamper_actor_user_id
    target_user_id = pending_trial.gangster_tamper_target_user_id
    if actor_user_id is None or target_user_id is None:
        return False
    actor = next((participant for participant in session.participants if participant.user_id == actor_user_id), None)
    if actor is None or actor.life_state != "alive":
        return False
    captured_user_id = _active_sergeant_capture_target_user_id(session, now_epoch_seconds=now_epoch_seconds)
    if captured_user_id == actor_user_id:
        return False
    return True


def _counted_trial_votes(
    session: GameDetailsSnapshot,
    pending_trial: TrialStateSnapshot,
    *,
    now_epoch_seconds: int,
) -> list[dict[str, str]]:
    tamper_active = _is_gangster_tamper_active(session, pending_trial, now_epoch_seconds=now_epoch_seconds)
    counted_votes: list[dict[str, str]] = []
    for vote in pending_trial.votes:
        vote_slot = str(vote.get("vote_slot", "jury"))
        user_id = str(vote.get("user_id", ""))
        if vote_slot == "tamper":
            if tamper_active and user_id == pending_trial.gangster_tamper_actor_user_id:
                counted_votes.append(dict(vote))
            continue
        if tamper_active and user_id == pending_trial.gangster_tamper_target_user_id:
            continue
        counted_votes.append(dict(vote))
    return counted_votes


def _apply_cop_last_three_protection_if_needed(
    session: GameDetailsSnapshot,
    *,
    now_epoch_seconds: int,
) -> GameDetailsSnapshot:
    if session.status != "in_progress":
        return session

    cop = next((participant for participant in session.participants if participant.role_name == "Cop"), None)
    if cop is None:
        return session
    if cop.power_state.cop_last_three_protection_used:
        return session
    if cop.life_state != "alive":
        return session

    alive_non_jailed_count = sum(1 for participant in session.participants if participant.life_state == "alive")
    if alive_non_jailed_count > COP_LAST_THREE_THRESHOLD:
        return session

    cop_has_vest = _find_inventory_item(
        session.participants,
        user_id=cop.user_id,
        classification="bulletproof_vest",
    ) is not None
    participants = []
    for participant in session.participants:
        if participant.user_id != cop.user_id:
            participants.append(participant)
            continue
        next_inventory = list(participant.inventory)
        if not cop_has_vest:
            next_inventory.append(_build_bulletproof_vest_inventory_item(session.catalog))
        participants.append(
            replace(
                participant,
                inventory=next_inventory,
                power_state=replace(
                    participant.power_state,
                    cop_last_three_protection_used=True,
                ),
            )
        )

    notification_message = "A police associate insured your protection and gifted you a bulletproof vest."
    notification_feed = _append_notifications(
        session.notification_feed,
        [
            (cop.user_id, notification_message),
            (session.moderator_user_id, f"{cop.username} reached the last three alive and received automatic bulletproof vest protection."),
        ],
        now_epoch_seconds=now_epoch_seconds,
    )
    return replace(
        session,
        participants=participants,
        notification_feed=notification_feed,
    )


def _apply_enforcer_first_kill_bonus_if_needed(
    participants: list[ParticipantStateSnapshot],
    *,
    murderer_user_id: str,
    victim_user_id: str,
    victim_money_balance: int,
    moderator_user_id: str,
    notification_feed: list[NotificationEventSnapshot],
    now_epoch_seconds: int,
) -> tuple[list[ParticipantStateSnapshot], list[NotificationEventSnapshot], list[LedgerEntrySnapshot]]:
    enforcer = next((participant for participant in participants if participant.user_id == murderer_user_id), None)
    if enforcer is None or enforcer.role_name != "Enforcer":
        return participants, notification_feed, []
    if enforcer.life_state != "alive":
        return participants, notification_feed, []
    if enforcer.power_state.enforcer_first_kill_bonus_used:
        return participants, notification_feed, []

    bonus_amount = _round_money_up_to_nearest_ten((victim_money_balance * 50 + 99) // 100)
    updated_participants: list[ParticipantStateSnapshot] = []
    for participant in participants:
        if participant.user_id != enforcer.user_id:
            updated_participants.append(participant)
            continue
        updated_participants.append(
            replace(
                participant,
                money_balance=participant.money_balance + bonus_amount,
                power_state=replace(
                    participant.power_state,
                    enforcer_first_kill_bonus_used=True,
                ),
            )
        )

    victim = next((participant for participant in participants if participant.user_id == victim_user_id), None)
    victim_label = victim.username if victim is not None else victim_user_id
    updated_feed = _append_notifications(
        notification_feed,
        [
            (
                enforcer.user_id,
                f"You received an Enforcer first-kill bonus of ${bonus_amount} after murdering {victim_label}.",
            ),
            (
                moderator_user_id,
                f"Enforcer first-kill bonus of ${bonus_amount} was awarded to {enforcer.username}.",
            ),
        ],
        now_epoch_seconds=now_epoch_seconds,
    )
    ledger_entries = []
    if bonus_amount > 0:
        ledger_entries.append(
            _build_ledger_entry(
                entry_kind="enforcer_bonus",
                amount=bonus_amount,
                from_holder_id=CENTRAL_SUPPLY_HOLDER_ID,
                to_holder_id=enforcer.user_id,
                now_epoch_seconds=now_epoch_seconds,
                note="Enforcer first-kill bonus.",
            )
        )
    return updated_participants, updated_feed, ledger_entries


@dataclass(frozen=True)
class _ConfiscationResult:
    handled: bool
    participants: list[ParticipantStateSnapshot]
    ledger_entries: list[LedgerEntrySnapshot]
    notifications: list[tuple[str, str]]


def _can_activate_police_officer_confiscation(session: GameDetailsSnapshot) -> bool:
    if session.status != "in_progress":
        return False
    if session.phase == "information":
        return True
    if session.phase == "accused_selection":
        return session.pending_trial is not None
    if session.phase == "trial_voting" and session.pending_trial is not None:
        return len(session.pending_trial.votes) < len(session.pending_trial.jury_user_ids)
    return False


def _consume_police_confiscation_if_pending(
    participants: list[ParticipantStateSnapshot],
    *,
    notification_feed: list[NotificationEventSnapshot],
    moderator_user_id: str,
    now_epoch_seconds: int,
    message: str,
) -> tuple[list[ParticipantStateSnapshot], list[NotificationEventSnapshot]]:
    police_officer = next((participant for participant in participants if participant.role_name == "Police Officer"), None)
    if police_officer is None or not police_officer.power_state.police_officer_confiscation_pending:
        return participants, notification_feed
    updated_participants = [
        replace(
            participant,
            power_state=replace(
                participant.power_state,
                police_officer_confiscation_pending=False,
                police_officer_confiscation_used=True,
            ),
        )
        if participant.user_id == police_officer.user_id
        else participant
        for participant in participants
    ]
    updated_feed = _append_notifications(
        notification_feed,
        [
            (police_officer.user_id, message),
            (moderator_user_id, message),
        ],
        now_epoch_seconds=now_epoch_seconds,
    )
    return updated_participants, updated_feed


def _apply_police_officer_confiscation_if_pending(
    participants: list[ParticipantStateSnapshot],
    *,
    accused_user_id: str,
    normal_recipient_user_id: str | None,
    moderator_user_id: str,
    now_epoch_seconds: int,
) -> _ConfiscationResult:
    police_officer = next((participant for participant in participants if participant.role_name == "Police Officer"), None)
    if police_officer is None or not police_officer.power_state.police_officer_confiscation_pending:
        return _ConfiscationResult(False, participants, [], [])

    if police_officer.life_state != "alive":
        updated_participants = [
            replace(
                participant,
                power_state=replace(
                    participant.power_state,
                    police_officer_confiscation_pending=False,
                    police_officer_confiscation_used=True,
                ),
            )
            if participant.user_id == police_officer.user_id
            else participant
            for participant in participants
        ]
        return _ConfiscationResult(
            False,
            updated_participants,
            [],
            [
                (police_officer.user_id, "Confiscation was canceled because you were no longer active when the verdict was returned."),
                (moderator_user_id, "Confiscation was canceled because the Police Officer was no longer active when the verdict was returned."),
            ],
        )

    accused = next((participant for participant in participants if participant.user_id == accused_user_id), None)
    if accused is None:
        return _ConfiscationResult(False, participants, [], [])

    accused_cash = max(accused.money_balance, 0)
    liquidation_total = sum(max(item.acquisition_value, 0) for item in accused.inventory)
    confiscation_total = accused_cash + liquidation_total

    base_participants = [
        replace(
            participant,
            power_state=replace(
                participant.power_state,
                police_officer_confiscation_pending=False,
                police_officer_confiscation_used=True,
            ),
        )
        if participant.user_id == police_officer.user_id
        else participant
        for participant in participants
    ]

    if confiscation_total <= 0:
        return _ConfiscationResult(
            True,
            base_participants,
            [],
            [
                (police_officer.user_id, "Confiscation found no recoverable resources after the guilty verdict."),
                (moderator_user_id, "Confiscation found no recoverable resources after the guilty verdict."),
            ],
        )

    eligible_police = [
        participant
        for participant in base_participants
        if participant.faction == "Police" and participant.life_state == "alive" and participant.user_id not in {police_officer.user_id, accused_user_id}
    ]
    if eligible_police:
        remaining_pool = confiscation_total - (confiscation_total // 2)
        rounded_share = int(((remaining_pool / len(eligible_police)) + 9) // 10) * 10
        police_shares = {participant.user_id: rounded_share for participant in eligible_police}
        police_total = sum(police_shares.values())
        officer_share = max(0, confiscation_total - police_total)
    else:
        police_shares = {}
        police_total = 0
        officer_share = confiscation_total

    payouts = {police_officer.user_id: officer_share, **police_shares}
    accused_remaining_cash = accused_cash
    ledger_entries: list[LedgerEntrySnapshot] = []
    updated_participants: list[ParticipantStateSnapshot] = []

    for participant in base_participants:
        if participant.user_id == accused_user_id:
            updated_participants.append(replace(participant, money_balance=0, inventory=[]))
            continue
        payout = payouts.get(participant.user_id, 0)
        if payout <= 0:
            updated_participants.append(participant)
            continue
        updated_participants.append(replace(participant, money_balance=participant.money_balance + payout))

        accused_portion = min(accused_remaining_cash, payout)
        if accused_portion > 0:
            accused_remaining_cash -= accused_portion
            ledger_entries.append(
                _build_ledger_entry(
                    entry_kind="conviction_transfer",
                    amount=accused_portion,
                    from_holder_id=accused_user_id,
                    to_holder_id=participant.user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    note="Police confiscation transfer.",
                )
            )
        central_portion = payout - accused_portion
        if central_portion > 0:
            ledger_entries.append(
                _build_ledger_entry(
                    entry_kind="conviction_transfer",
                    amount=central_portion,
                    from_holder_id=CENTRAL_SUPPLY_HOLDER_ID,
                    to_holder_id=participant.user_id,
                    now_epoch_seconds=now_epoch_seconds,
                    note="Police confiscation liquidation.",
                )
            )

    notifications = [
        (
            police_officer.user_id,
            (
                f"You confiscated ${officer_share}."
                if eligible_police
                else f"You confiscated 100 percent of the recovered resources, totaling ${officer_share}."
            ),
        ),
        (
            moderator_user_id,
            f"Police confiscation recovered ${confiscation_total} after the guilty verdict.",
        ),
    ]
    for participant in eligible_police:
        share = police_shares[participant.user_id]
        notifications.append(
            (
                participant.user_id,
                f"The police department confiscated convicted resources and your share was ${share}.",
            )
        )
    if normal_recipient_user_id is not None and normal_recipient_user_id not in {accused_user_id, police_officer.user_id}:
        notifications.append(
            (
                normal_recipient_user_id,
                "The police department confiscated these resources, so you will not receive the convicted player's property.",
            )
        )

    return _ConfiscationResult(True, updated_participants, ledger_entries, notifications)


def _find_faction_leader_user_id(
    participants: list[ParticipantStateSnapshot],
    *,
    faction: str,
    unavailable_user_ids: set[str] | None = None,
) -> str | None:
    unavailable = unavailable_user_ids or set()
    alive = [
        participant
        for participant in participants
        if participant.faction == faction and participant.life_state == "alive" and participant.user_id not in unavailable
    ]
    if not alive:
        return None
    return sorted(alive, key=lambda participant: participant.rank)[0].user_id


def _resolve_next_leader_user_id(
    participants: list[ParticipantStateSnapshot],
    *,
    faction: str,
    current_leader_user_id: str | None,
    unavailable_user_ids: set[str] | None = None,
) -> str | None:
    unavailable = unavailable_user_ids or set()
    if current_leader_user_id:
        current = next((p for p in participants if p.user_id == current_leader_user_id and p.faction == faction), None)
        if current is not None and current.life_state == "alive" and current.user_id not in unavailable:
            return current_leader_user_id
    return _find_faction_leader_user_id(participants, faction=faction, unavailable_user_ids=unavailable)


def _determine_winning_faction(session: GameDetailsSnapshot) -> str | None:
    participants = session.participants
    alive_police = any(p.life_state == "alive" and p.faction == "Police" for p in participants)
    alive_mob = any(p.life_state == "alive" and p.faction == "Mob" for p in participants)
    if not alive_police and alive_mob:
        return "Mob"
    if not alive_mob and alive_police:
        allowed_police_mob_kills = session.total_mob_participants_at_start // 2
        if session.police_mob_kills_count > allowed_police_mob_kills:
            return "Mob"
        return "Police"
    return None


def _determine_boundary_winner(session: GameDetailsSnapshot) -> tuple[str | None, str | None]:
    participants = session.participants
    # Merchant precedence at boundaries: any merchant meeting goal wins immediately.
    merchant_winner_user_id = _find_merchant_winner_user_id(participants)
    if merchant_winner_user_id is not None:
        return "Merchant", merchant_winner_user_id

    faction_winner = _determine_winning_faction(session)
    if faction_winner is not None:
        return faction_winner, None
    return None, None


def _find_merchant_winner_user_id(participants: list[ParticipantStateSnapshot]) -> str | None:
    total_circulating = sum(max(participant.money_balance, 0) for participant in participants)
    goal_bonus = int(total_circulating * MERCHANT_GOAL_ADDITIONAL_PERCENT)
    player_count = max(7, min(len(participants), 25))
    for participant in participants:
        if participant.faction != "Merchant":
            continue
        if participant.life_state != "alive":
            continue
        merchant_goal = _default_starting_balance_for_role(participant.role_name, player_count=player_count) + goal_bonus
        if participant.money_balance >= merchant_goal:
            return participant.user_id
    return None


def _default_starting_balance_for_role(role_name: str, *, player_count: int) -> int:
    return getStartingMoney(player_count, role_name)


def _participant_name_by_id(participants: list[ParticipantStateSnapshot]) -> dict[str, str]:
    return {participant.user_id: participant.username for participant in participants}


def _apply_armed_don_silence_for_upcoming_trial(
    participants: list[ParticipantStateSnapshot],
    *,
    accused_selection_cursor: list[str],
    moderator_user_id: str,
    notification_feed: list[NotificationEventSnapshot],
    now_epoch_seconds: int,
) -> tuple[list[str], list[ParticipantStateSnapshot], list[NotificationEventSnapshot]]:
    don = next(
        (
            participant
            for participant in participants
            if participant.role_name == "Don" and participant.power_state.don_silence_target_user_id
        ),
        None,
    )
    if don is None:
        return [], participants, notification_feed

    target_user_id = str(don.power_state.don_silence_target_user_id)
    participants_without_arm = [
        replace(
            participant,
            power_state=replace(participant.power_state, don_silence_target_user_id=None),
        )
        if participant.user_id == don.user_id
        else participant
        for participant in participants
    ]

    if not accused_selection_cursor:
        return [], participants_without_arm, notification_feed

    target = next((participant for participant in participants_without_arm if participant.user_id == target_user_id), None)
    if target is None or target.life_state != "alive":
        return [], participants_without_arm, notification_feed

    silence_notice = (
        f"{target.username} seems to be afraid to testify at court. "
        f"{target.username} will remain silent during this upcoming trial."
    )
    broadcast_pairs = [(participant.user_id, silence_notice) for participant in participants_without_arm]
    if moderator_user_id not in {participant.user_id for participant in participants_without_arm}:
        broadcast_pairs.append((moderator_user_id, silence_notice))
    next_notifications = _append_notifications(
        notification_feed,
        broadcast_pairs,
        now_epoch_seconds=now_epoch_seconds,
    )
    return [target.user_id], participants_without_arm, next_notifications


def _find_inventory_item(
    participants: list[ParticipantStateSnapshot],
    *,
    user_id: str,
    classification: str,
) -> InventoryItemStateSnapshot | None:
    participant = next((candidate for candidate in participants if candidate.user_id == user_id), None)
    if participant is None:
        return None
    return next((item for item in participant.inventory if item.classification == classification), None)


def _is_gun_attack_classification(attack_classification: str) -> bool:
    return attack_classification in _GUN_ATTACK_CLASSIFICATIONS


def _attack_display_name(catalog: list[CatalogItemStateSnapshot], attack_classification: str) -> str:
    catalog_item = next((item for item in catalog if item.classification == attack_classification), None)
    if catalog_item is not None:
        return catalog_item.display_name
    if attack_classification == "knife":
        return "Knife"
    if attack_classification == "gun_tier_1":
        return "Handgun (Tier 1)"
    if attack_classification == "gun_tier_2":
        return "Pistol (Tier 2)"
    if attack_classification == "gun_tier_3":
        return "Revolver (Tier 3)"
    return attack_classification.replace("_", " ")


def _remove_inventory_item_from_participant(
    participants: list[ParticipantStateSnapshot],
    *,
    user_id: str,
    inventory_item_id: str,
) -> list[ParticipantStateSnapshot]:
    updated: list[ParticipantStateSnapshot] = []
    for participant in participants:
        if participant.user_id == user_id:
            updated.append(
                replace(
                    participant,
                    inventory=[item for item in participant.inventory if item.item_id != inventory_item_id],
                )
            )
            continue
        updated.append(participant)
    return updated


def _select_efj_bribe_recipient(
    participants: list[ParticipantStateSnapshot],
    *,
    accused_user_id: str,
    selector,
) -> ParticipantStateSnapshot | None:
    eligible = [
        participant
        for participant in participants
        if participant.faction == "Police"
        and participant.life_state == "alive"
        and participant.user_id != accused_user_id
    ]
    if not eligible:
        return None
    return cast(ParticipantStateSnapshot, selector(eligible))


def _build_trial_outcome_notices(
    participants: list[ParticipantStateSnapshot],
    pending_trial: TrialStateSnapshot | None,
    *,
    police_leader_user_id: str | None,
    mob_leader_user_id: str | None,
) -> tuple[str | None, str | None, str | None]:
    if pending_trial is None or pending_trial.accused_user_id is None:
        return None, None, None
    if pending_trial.verdict not in {"guilty", "innocent"}:
        return None, None, None
    participant_name_by_id = _participant_name_by_id(participants)
    accused_username = participant_name_by_id.get(pending_trial.accused_user_id, pending_trial.accused_user_id)
    verdict_label = "guilty" if pending_trial.verdict == "guilty" else "not guilty"
    notice = f"{accused_username} was found {verdict_label}."
    private_notice_user_id: str | None = None
    private_notice_message: str | None = None
    if pending_trial.verdict == "guilty":
        if pending_trial.resolution == "efj_saved":
            return f"{accused_username} was found guilty.", None, None
        notice = f"{notice} They are now in jail."
        if pending_trial.resolution == "confiscated":
            return notice, None, None
        transfer_recipient_user_id = (
            police_leader_user_id if pending_trial.conviction_correct else mob_leader_user_id
        )
        if transfer_recipient_user_id is not None and transfer_recipient_user_id != pending_trial.accused_user_id:
            private_notice_user_id = transfer_recipient_user_id
            private_notice_message = f"You received {accused_username}'s inventory."
    return notice, private_notice_user_id, private_notice_message


def _purchase_from_supply(
    session: GameDetailsSnapshot,
    *,
    buyer_user_id: str,
    classification: str,
    role_mode: str,
    now_epoch_seconds: int,
) -> GameDetailsSnapshot:
    catalog_item = next(
        (item for item in session.catalog if item.classification == classification and item.is_active),
        None,
    )
    if catalog_item is None:
        raise ValueError("Requested item is not available in central supply.")

    buyer = next((participant for participant in session.participants if participant.user_id == buyer_user_id), None)
    if buyer is None:
        raise ValueError("Buyer participant not found in session.")

    purchase_price = catalog_item.base_price
    if role_mode == "merchant":
        if buyer.faction != "Merchant":
            raise PermissionError("Only merchants can buy from central supply.")
        if buyer.life_state != "alive":
            raise ConflictProblem("Only alive merchants can buy from central supply.", code="invalid_state")
    elif role_mode == "merchant_wholesale_order":
        if buyer.role_name != "Merchant":
            raise PermissionError("Only Merchant can use Wholesale Order.")
        purchase_price = _round_money_to_nearest_ten(
            (catalog_item.base_price * (100 - MERCHANT_WHOLESALE_DISCOUNT_PERCENT)) // 100
        )
    elif role_mode == "made_man":
        if buyer.role_name != "Made Man":
            raise PermissionError("Only Made Man can use skip middle man.")
    else:
        raise ValueError("Unsupported supply purchase mode.")

    if buyer.money_balance < purchase_price:
        raise ConflictProblem("Insufficient funds for this purchase.", code="invalid_state")

    purchased = InventoryItemStateSnapshot(
        item_id=f"inv-{str(uuid4())[:8]}",
        classification=catalog_item.classification,
        display_name=catalog_item.display_name,
        image_path=catalog_item.image_path,
        acquisition_value=purchase_price,
        resale_price=purchase_price,
    )
    participants: list[ParticipantStateSnapshot] = []
    for participant in session.participants:
        if participant.user_id != buyer_user_id:
            participants.append(participant)
            continue
        next_power_state = participant.power_state
        if role_mode == "made_man":
            next_power_state = replace(next_power_state, made_man_skip_middle_man_used=True)
        elif role_mode == "merchant_wholesale_order":
            next_power_state = replace(next_power_state, merchant_wholesale_order_used=True)
        participants.append(
            replace(
                participant,
                money_balance=participant.money_balance - purchase_price,
                inventory=[*participant.inventory, purchased],
                power_state=next_power_state,
            )
        )

    catalog = _deactivate_supply_catalog_item(session.catalog, classification=classification)
    if classification == "knife":
        catalog = _update_supply_price(catalog, classification="knife", next_price=_next_knife_supply_price(catalog_item.base_price))

    updated = replace(
        session,
        participants=participants,
        catalog=catalog,
        version=session.version + 1,
        latest_public_notice=None,
    )
    updated = _append_ledger_entries(
        updated,
        [
            _build_ledger_entry(
                entry_kind="central_supply_purchase",
                amount=purchase_price,
                from_holder_id=buyer_user_id,
                to_holder_id=CENTRAL_SUPPLY_HOLDER_ID,
                now_epoch_seconds=now_epoch_seconds,
                note=(
                    f"Supply purchase: {catalog_item.display_name}"
                    if role_mode != "merchant_wholesale_order"
                    else f"Wholesale Order purchase: {catalog_item.display_name}"
                ),
            )
        ],
    )
    if role_mode == "made_man":
        updated = replace(
            updated,
            notification_feed=_append_notifications(
                session.notification_feed,
                _build_made_man_skip_middle_man_notifications(
                    session.participants,
                    buyer,
                    catalog_item,
                    moderator_user_id=session.moderator_user_id,
                ),
                now_epoch_seconds=now_epoch_seconds,
            ),
        )
    elif role_mode == "merchant_wholesale_order":
        updated = replace(
            updated,
            notification_feed=_append_notifications(
                session.notification_feed,
                [
                    (buyer.user_id, f"You used Wholesale Order to buy {catalog_item.display_name} for ${purchase_price}."),
                    (
                        session.moderator_user_id,
                        f"{buyer.username} used Wholesale Order to buy {catalog_item.display_name} for ${purchase_price}.",
                    ),
                ],
                now_epoch_seconds=now_epoch_seconds,
            ),
        )
    return updated


def _transfer_inventory_between_participants(
    participants: list[ParticipantStateSnapshot], *, from_user_id: str, to_user_id: str | None
) -> list[ParticipantStateSnapshot]:
    if to_user_id is None or to_user_id == from_user_id:
        return participants

    source = next((participant for participant in participants if participant.user_id == from_user_id), None)
    target = next((participant for participant in participants if participant.user_id == to_user_id), None)
    if source is None or target is None:
        return participants
    if target.life_state != "alive":
        return participants

    transferred_inventory = list(source.inventory)
    transferred_money = source.money_balance
    updated: list[ParticipantStateSnapshot] = []
    for participant in participants:
        if participant.user_id == from_user_id:
            updated.append(replace(participant, inventory=[], money_balance=0))
            continue
        if participant.user_id == to_user_id:
            updated.append(
                replace(
                    participant,
                    inventory=[*participant.inventory, *transferred_inventory],
                    money_balance=participant.money_balance + transferred_money,
                )
            )
            continue
        updated.append(participant)
    return updated


def _deactivate_supply_catalog_item(
    catalog: list[CatalogItemStateSnapshot],
    *,
    classification: str,
) -> list[CatalogItemStateSnapshot]:
    updated = list(catalog)
    for idx, item in enumerate(updated):
        if item.classification != classification:
            continue
        updated[idx] = replace(item, is_active=False)
        break
    return updated


def _reactivate_supply_catalog_item(
    catalog: list[CatalogItemStateSnapshot],
    inventory_item: InventoryItemStateSnapshot,
) -> list[CatalogItemStateSnapshot]:
    updated = list(catalog)
    for idx, item in enumerate(updated):
        if item.classification != inventory_item.classification:
            continue
        updated[idx] = replace(item, is_active=True, base_price=inventory_item.acquisition_value)
        return updated
    updated.append(
        CatalogItemStateSnapshot(
            classification=inventory_item.classification,
            display_name=inventory_item.display_name,
            base_price=inventory_item.acquisition_value,
            image_path=inventory_item.image_path,
            is_active=True,
        )
    )
    return updated


def _update_supply_price(
    catalog: list[CatalogItemStateSnapshot],
    *,
    classification: str,
    next_price: int,
) -> list[CatalogItemStateSnapshot]:
    updated = list(catalog)
    for idx, item in enumerate(updated):
        if item.classification != classification:
            continue
        updated[idx] = replace(item, base_price=next_price)
        break
    return updated


def _build_made_man_skip_middle_man_notifications(
    participants: list[ParticipantStateSnapshot],
    buyer: ParticipantStateSnapshot,
    catalog_item: CatalogItemStateSnapshot,
    *,
    moderator_user_id: str,
) -> list[tuple[str, str]]:
    notifications = [
        (buyer.user_id, f"You used Skip Middle Man to buy {catalog_item.display_name} directly from central supply."),
    ]
    merchant_roles = {"Merchant", "Gun Runner", "Arms Dealer", "Smuggler", "Supplier"}
    flavor_text = (
        f"Central supply was burglarized. {catalog_item.display_name} is missing from stock."
    )
    for participant in participants:
        if participant.role_name in merchant_roles and participant.life_state == "alive":
            notifications.append((participant.user_id, flavor_text))
    notifications.append((moderator_user_id, flavor_text))
    return notifications


def _build_winner_notice(
    session: GameDetailsSnapshot, *, winner_faction: str, winner_user_id: str | None
) -> str:
    participants = session.participants
    if winner_faction == "Mob" and _is_police_brutality_mob_win(session):
        return "Mob wins. Police Department Shut Down Due to Police Brutality. Department Overrun by Mob."
    if winner_faction == "Merchant" and winner_user_id is not None:
        participant_name_by_id = _participant_name_by_id(participants)
        winner_name = participant_name_by_id.get(winner_user_id, winner_user_id)
        return f"Game ended. {winner_name} (Merchant) wins."
    return f"Game ended. {winner_faction} wins."


def _is_police_brutality_mob_win(session: GameDetailsSnapshot) -> bool:
    alive_police = any(p.life_state == "alive" and p.faction == "Police" for p in session.participants)
    alive_mob = any(p.life_state == "alive" and p.faction == "Mob" for p in session.participants)
    if not alive_police or alive_mob:
        return False
    allowed_police_mob_kills = session.total_mob_participants_at_start // 2
    return session.police_mob_kills_count > allowed_police_mob_kills


def _has_active_trial(pending_trial: TrialStateSnapshot | None) -> bool:
    if pending_trial is None:
        return False
    if pending_trial.verdict is not None:
        return False
    return pending_trial.resolution is None


def _round_money_to_nearest_ten(value: int) -> int:
    remainder = value % 10
    if remainder >= 5:
        return value + (10 - remainder)
    return value - remainder


def _round_money_up_to_nearest_ten(value: int) -> int:
    if value <= 0:
        return 0
    remainder = value % 10
    if remainder == 0:
        return value
    return value + (10 - remainder)


def _build_bulletproof_vest_inventory_item(
    catalog: list[CatalogItemStateSnapshot],
) -> InventoryItemStateSnapshot:
    vest_catalog_item = next((item for item in catalog if item.classification == "bulletproof_vest"), None)
    if vest_catalog_item is None:
        return InventoryItemStateSnapshot(
            item_id=f"inv-{str(uuid4())[:8]}",
            classification="bulletproof_vest",
            display_name="Bulletproof Vest",
            image_path="/static/items/defaults/default_bulletproof_vest.svg",
            acquisition_value=50,
            resale_price=50,
        )
    return InventoryItemStateSnapshot(
        item_id=f"inv-{str(uuid4())[:8]}",
        classification=vest_catalog_item.classification,
        display_name=vest_catalog_item.display_name,
        image_path=vest_catalog_item.image_path,
        acquisition_value=vest_catalog_item.base_price,
        resale_price=vest_catalog_item.base_price,
    )


def _build_role_starting_loadout(
    *,
    role_name: str,
    catalog: list[CatalogItemStateSnapshot],
    username: str,
    user_id: str,
) -> tuple[list[InventoryItemStateSnapshot], list[CatalogItemStateSnapshot], list[tuple[str, str]]]:
    if role_name == "Arms Dealer":
        gun_catalog_item = next((item for item in catalog if item.classification == "gun_tier_1"), None)
        if gun_catalog_item is None:
            inventory_item = InventoryItemStateSnapshot(
                item_id=f"inv-{str(uuid4())[:8]}",
                classification="gun_tier_1",
                display_name="Handgun (Tier 1)",
                image_path="/static/items/defaults/default_gun_tier_1.svg",
                acquisition_value=150,
                resale_price=150,
            )
            return (
                [inventory_item],
                catalog,
                [(user_id, "You started the game with a Tier 1 gun from your Arms Dealer loadout.")],
            )
        return (
            [
                InventoryItemStateSnapshot(
                    item_id=f"inv-{str(uuid4())[:8]}",
                    classification=gun_catalog_item.classification,
                    display_name=gun_catalog_item.display_name,
                    image_path=gun_catalog_item.image_path,
                    acquisition_value=gun_catalog_item.base_price,
                    resale_price=gun_catalog_item.base_price,
                )
            ],
            _deactivate_supply_catalog_item(catalog, classification="gun_tier_1"),
            [(user_id, "You started the game with a Tier 1 gun from your Arms Dealer loadout.")],
        )
    return _build_starting_inventory_for_role(role_name=role_name, catalog=catalog), catalog, []


def _build_starting_inventory_for_role(
    *, role_name: str, catalog: list[CatalogItemStateSnapshot]
) -> list[InventoryItemStateSnapshot]:
    if role_name != "Knife Hobo":
        return []
    knife_catalog_candidates = [
        item
        for item in catalog
        if item.classification == "knife" or item.classification.startswith("knife_")
    ]
    knife_catalog_item = next(
        iter(sorted(knife_catalog_candidates, key=lambda item: (item.classification, item.base_price))),
        None,
    )
    if knife_catalog_item is None:
        return [
            InventoryItemStateSnapshot(
                item_id=f"inv-{str(uuid4())[:8]}",
                classification="knife",
                display_name="Knife",
                image_path="/static/items/defaults/default_knife.svg",
                acquisition_value=100,
                resale_price=100,
            )
        ]
    return [
        InventoryItemStateSnapshot(
            item_id=f"inv-{str(uuid4())[:8]}",
            classification=knife_catalog_item.classification,
            display_name=knife_catalog_item.display_name,
            image_path=knife_catalog_item.image_path,
            acquisition_value=knife_catalog_item.base_price,
            resale_price=knife_catalog_item.base_price,
        )
    ]


def _next_knife_supply_price(current_price: int) -> int:
    return _round_money_to_nearest_ten(int(current_price * 1.5))


def _select_trial_jury_user_ids(
    participants: list[ParticipantStateSnapshot],
    *,
    accused_user_id: str,
    excluded_user_ids: set[str] | None = None,
) -> list[str]:
    excluded = excluded_user_ids or set()
    eligible = [
        participant
        for participant in participants
        if participant.life_state == "alive" and participant.user_id != accused_user_id and participant.user_id not in excluded
    ]
    if not eligible:
        return []
    if len(eligible) <= DEFAULT_WEIGHTS.jury_min_size:
        ordered = sorted(eligible, key=lambda participant: (participant.rank, participant.username.lower(), participant.user_id))
        return [participant.user_id for participant in ordered]

    target_count = max(1, int(len(eligible) * DEFAULT_WEIGHTS.jury_fraction_of_living_players))
    target_count = max(target_count, min(DEFAULT_WEIGHTS.jury_min_size, len(eligible)))
    target_count = min(target_count, len(eligible))
    if DEFAULT_WEIGHTS.jury_must_be_odd and target_count > 1 and target_count % 2 == 0:
        target_count -= 1
    ordered = sorted(eligible, key=lambda participant: (participant.rank, participant.username.lower(), participant.user_id))
    return [participant.user_id for participant in ordered[:target_count]]
