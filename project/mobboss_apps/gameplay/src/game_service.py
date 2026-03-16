"""Gameplay use-case service.

Authoritative invariants for this slice:
- one-trial-per-murder: `report_death` is blocked while any trial is pending.
- boundary-only win checks: phase transitions may move to `boundary_resolution`,
  but this service does not evaluate final win conditions mid-mutation.
- role-leak safety: this service stores full internal truth; visibility filtering is
  enforced in the API/web projection layer.
"""

from __future__ import annotations

from dataclasses import replace
import time
from typing import cast

from project.mobboss_apps.gameplay.ports.inbound import GameplayInboundPort
from project.mobboss_apps.gameplay.ports.internal import (
    AdvanceAccusedSelectionTimeoutCommand,
    CatalogItemStateSnapshot,
    GameDetailsSnapshot,
    GamePhase,
    ParticipantStateSnapshot,
    ReportDeathCommand,
    StartSessionFromRoomCommand,
    TrialStateSnapshot,
)
from project.mobboss_apps.gameplay.ports.outbound import GameplayOutboundPort
from project.mobboss_apps.mobboss.exceptions import ConflictProblem

ACCUSED_SELECTION_TIMEOUT_SECONDS = 15


class GameplayService(GameplayInboundPort):
    def __init__(self, repository: GameplayOutboundPort, *, now_epoch_seconds_provider=None) -> None:
        self._repository = repository
        self._now_epoch_seconds_provider = now_epoch_seconds_provider or (lambda: int(time.time()))

    def start_session_from_room(self, command: StartSessionFromRoomCommand) -> GameDetailsSnapshot:
        if not command.participants:
            raise ValueError("Cannot start game session without participants.")

        game_id = self._repository.reserve_game_id(command.room_id)
        participants = [
            ParticipantStateSnapshot(
                user_id=participant.user_id,
                username=participant.username,
                faction=participant.faction,
                role_name=participant.role_name,
                rank=participant.rank,
                life_state="alive",
                money_balance=participant.starting_balance,
            )
            for participant in command.participants
        ]
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
        )
        self._repository.save_game_session(session)
        return session

    def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
        session = self._repository.get_game_session(game_id)
        if session is None:
            raise ValueError("Game session not found.")
        return session

    def report_death(self, command: ReportDeathCommand) -> GameDetailsSnapshot:
        session = self.get_game_details(command.game_id)
        if command.reported_by_user_id != session.moderator_user_id:
            raise PermissionError("Only moderator can report deaths.")
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
        if session.pending_trial is not None:
            raise ConflictProblem("Cannot report death while a trial is pending.", code="invalid_state")

        participant_exists = False
        updated_participants: list[ParticipantStateSnapshot] = []
        for participant in session.participants:
            if participant.user_id == command.murdered_user_id:
                participant_exists = True
                if participant.life_state != "alive":
                    raise ValueError("Reported participant is not alive.")
                updated_participants.append(replace(participant, life_state="dead"))
                continue
            updated_participants.append(participant)

        if not participant_exists:
            raise ValueError("Murdered participant not found in session.")

        accused_selection_cursor = [
            participant.user_id
            for participant in sorted(
                updated_participants,
                key=lambda candidate: candidate.rank,
            )
            if participant.faction == "Police" and participant.life_state == "alive"
        ]
        now_epoch_seconds = self._now_epoch_seconds()
        pending_trial = TrialStateSnapshot(
            murdered_user_id=command.murdered_user_id,
            murderer_user_id=None,
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
        )
        next_phase = cast(GamePhase, "accused_selection" if accused_selection_cursor else "boundary_resolution")
        # Invariant: boundary-only win checks happen in a dedicated boundary phase,
        # never inline inside death-report mutation flow.
        updated = replace(
            session,
            participants=updated_participants,
            pending_trial=pending_trial,
            phase=next_phase,
            version=session.version + 1,
        )
        self._repository.save_game_session(updated)
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
        self._repository.save_game_session(updated)
        return updated

    def _now_epoch_seconds(self) -> int:
        return int(self._now_epoch_seconds_provider())

