"""Maps internal gameplay snapshots to sanitized HTML page-view DTOs."""

from __future__ import annotations

from dataclasses import dataclass

from project.mobboss_apps.gameplay.ports.internal import GameDetailsSnapshot


@dataclass(frozen=True)
class GameplayParticipantRowDTO:
    user_id: str
    username: str
    life_state: str
    is_self: bool
    role_label: str


@dataclass(frozen=True)
class GameplayPendingTrialDTO:
    murdered_user_id: str
    current_responder_user_id: str | None
    accused_selection_deadline_epoch_seconds: int | None


@dataclass(frozen=True)
class GameplayPageViewDTO:
    game_id: str
    room_id: str
    status: str
    phase: str
    round_number: int
    version: int
    viewer_user_id: str
    is_moderator: bool
    participant_rows: list[GameplayParticipantRowDTO]
    pending_trial: GameplayPendingTrialDTO | None
    can_report_death: bool


def build_gameplay_page_view(snapshot: GameDetailsSnapshot, viewer_user_id: str) -> GameplayPageViewDTO:
    is_moderator = snapshot.moderator_user_id == viewer_user_id
    if is_moderator:
        return _build_moderator_gameplay_page_view(snapshot, viewer_user_id)
    return _build_player_gameplay_page_view(snapshot, viewer_user_id)


def _build_moderator_gameplay_page_view(snapshot: GameDetailsSnapshot, viewer_user_id: str) -> GameplayPageViewDTO:
    participant_rows = [
        GameplayParticipantRowDTO(
            user_id=participant.user_id,
            username=participant.username,
            life_state=participant.life_state,
            is_self=participant.user_id == viewer_user_id,
            role_label=f"{participant.faction} / {participant.role_name} ({participant.rank})",
        )
        for participant in snapshot.participants
    ]

    pending_trial = None
    if snapshot.pending_trial is not None:
        current_responder_user_id = None
        if snapshot.pending_trial.accused_selection_cursor:
            current_responder_user_id = snapshot.pending_trial.accused_selection_cursor[0]
        pending_trial = GameplayPendingTrialDTO(
            murdered_user_id=snapshot.pending_trial.murdered_user_id,
            current_responder_user_id=current_responder_user_id,
            accused_selection_deadline_epoch_seconds=snapshot.pending_trial.accused_selection_deadline_epoch_seconds,
        )

    return GameplayPageViewDTO(
        game_id=snapshot.game_id,
        room_id=snapshot.room_id,
        status=snapshot.status,
        phase=snapshot.phase,
        round_number=snapshot.round_number,
        version=snapshot.version,
        viewer_user_id=viewer_user_id,
        is_moderator=True,
        participant_rows=participant_rows,
        pending_trial=pending_trial,
        can_report_death=snapshot.status == "in_progress" and snapshot.pending_trial is None,
    )


def _build_player_gameplay_page_view(snapshot: GameDetailsSnapshot, viewer_user_id: str) -> GameplayPageViewDTO:
    participant_rows: list[GameplayParticipantRowDTO] = []
    viewer_is_participant = False
    for participant in snapshot.participants:
        is_self = participant.user_id == viewer_user_id
        if is_self:
            viewer_is_participant = True
        role_label = "Hidden"
        if is_self:
            role_label = f"{participant.faction} / {participant.role_name} ({participant.rank})"
        participant_rows.append(
            GameplayParticipantRowDTO(
                user_id=participant.user_id,
                username=participant.username,
                life_state=participant.life_state,
                is_self=is_self,
                role_label=role_label,
            )
        )

    if not viewer_is_participant:
        raise PermissionError("Only moderator or joined participants can view this game.")

    return GameplayPageViewDTO(
        game_id=snapshot.game_id,
        room_id=snapshot.room_id,
        status=snapshot.status,
        phase=snapshot.phase,
        round_number=snapshot.round_number,
        version=snapshot.version,
        viewer_user_id=viewer_user_id,
        is_moderator=False,
        participant_rows=participant_rows,
        pending_trial=None,
        can_report_death=False,
    )
