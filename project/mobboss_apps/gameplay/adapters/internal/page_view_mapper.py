"""Maps internal gameplay snapshots to sanitized HTML page-view DTOs."""

from __future__ import annotations

from dataclasses import dataclass

from project.mobboss_apps.gameplay.ports.internal import GameDetailsSnapshot
from project.mobboss_apps.mobboss.src.starting_money import getStartingMoney

MERCHANT_GOAL_ADDITIONAL_PERCENT = 0.40


@dataclass(frozen=True)
class GameplayParticipantRowDTO:
    user_id: str
    username: str
    life_state: str
    status_label: str
    is_self: bool
    role_label: str
    inventory_text: str = ""
    money_balance: int | None = None
    merchant_money_goal: int | None = None
    is_juror: bool = False
    murdered_by_username: str | None = None
    accused_by_username: str | None = None
    convicted_by_label: str | None = None


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
    is_ghost_view: bool
    participant_rows: list[GameplayParticipantRowDTO]
    pending_trial: GameplayPendingTrialDTO | None
    can_report_death: bool


def build_gameplay_page_view(snapshot: GameDetailsSnapshot, viewer_user_id: str) -> GameplayPageViewDTO:
    is_moderator = snapshot.moderator_user_id == viewer_user_id
    if is_moderator:
        return _build_moderator_gameplay_page_view(snapshot, viewer_user_id)
    if _viewer_has_ghost_view(snapshot, viewer_user_id):
        return _build_ghost_gameplay_page_view(snapshot, viewer_user_id)
    return _build_player_gameplay_page_view(snapshot, viewer_user_id)


def _build_moderator_gameplay_page_view(snapshot: GameDetailsSnapshot, viewer_user_id: str) -> GameplayPageViewDTO:
    participant_name_by_id = {participant.user_id: participant.username for participant in snapshot.participants}
    goal_bonus = int(snapshot.ledger.circulating_currency_baseline * MERCHANT_GOAL_ADDITIONAL_PERCENT)
    player_count = max(7, min(len(snapshot.participants), 25))
    participant_rows = [
        GameplayParticipantRowDTO(
            user_id=participant.user_id,
            username=participant.username,
            life_state=participant.life_state,
            status_label=_participant_status_label(snapshot, participant.user_id),
            is_self=participant.user_id == viewer_user_id,
            role_label=_participant_role_label(snapshot, participant.user_id, reveal_role=True),
            inventory_text=_inventory_text(participant.inventory),
            money_balance=participant.money_balance,
            merchant_money_goal=(
                getStartingMoney(player_count, participant.role_name) + goal_bonus
                if participant.faction == "Merchant"
                else None
            ),
            is_juror=_is_trial_juror(snapshot, participant.user_id),
            murdered_by_username=_murdered_by_username(snapshot, participant.user_id, participant_name_by_id),
            accused_by_username=_accused_by_username(participant, participant_name_by_id),
            convicted_by_label=_convicted_by_label(participant, participant_name_by_id),
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
        is_ghost_view=False,
        participant_rows=participant_rows,
        pending_trial=pending_trial,
        can_report_death=snapshot.status == "in_progress" and snapshot.pending_trial is None,
    )


def _build_ghost_gameplay_page_view(snapshot: GameDetailsSnapshot, viewer_user_id: str) -> GameplayPageViewDTO:
    moderator_view = _build_moderator_gameplay_page_view(snapshot, viewer_user_id)
    return GameplayPageViewDTO(
        game_id=moderator_view.game_id,
        room_id=moderator_view.room_id,
        status=moderator_view.status,
        phase=moderator_view.phase,
        round_number=moderator_view.round_number,
        version=moderator_view.version,
        viewer_user_id=moderator_view.viewer_user_id,
        is_moderator=False,
        is_ghost_view=True,
        participant_rows=moderator_view.participant_rows,
        pending_trial=moderator_view.pending_trial,
        can_report_death=False,
    )


def _build_player_gameplay_page_view(snapshot: GameDetailsSnapshot, viewer_user_id: str) -> GameplayPageViewDTO:
    participant_rows: list[GameplayParticipantRowDTO] = []
    viewer_is_participant = False
    reveal_all_roles = snapshot.status == "ended"
    for participant in snapshot.participants:
        is_self = participant.user_id == viewer_user_id
        if is_self:
            viewer_is_participant = True
        role_label = "Hidden"
        if is_self or reveal_all_roles:
            role_label = _participant_role_label(snapshot, participant.user_id, reveal_role=True)
        participant_rows.append(
            GameplayParticipantRowDTO(
                user_id=participant.user_id,
                username=participant.username,
                life_state=participant.life_state,
                status_label=_participant_status_label(snapshot, participant.user_id),
                is_self=is_self,
                role_label=role_label,
                inventory_text=_inventory_text(participant.inventory) if is_self else "",
                money_balance=participant.money_balance if is_self else None,
            )
        )

    if not viewer_is_participant:
        raise PermissionError("Only moderator or joined participants can view this game.")

    participant_rows.sort(key=lambda participant: (not participant.is_self, participant.username.lower()))

    return GameplayPageViewDTO(
        game_id=snapshot.game_id,
        room_id=snapshot.room_id,
        status=snapshot.status,
        phase=snapshot.phase,
        round_number=snapshot.round_number,
        version=snapshot.version,
        viewer_user_id=viewer_user_id,
        is_moderator=False,
        is_ghost_view=False,
        participant_rows=participant_rows,
        pending_trial=None,
        can_report_death=False,
    )


def _viewer_has_ghost_view(snapshot: GameDetailsSnapshot, viewer_user_id: str) -> bool:
    participant = next((candidate for candidate in snapshot.participants if candidate.user_id == viewer_user_id), None)
    if participant is None:
        return False
    if (
        snapshot.status == "in_progress"
        and participant.role_name == "Felon"
        and participant.life_state == "jailed"
        and snapshot.felon_escape_user_id == participant.user_id
        and snapshot.felon_escape_expires_at_epoch_seconds is not None
    ):
        return False
    return participant.life_state in {"dead", "jailed"}


def _participant_role_label(snapshot: GameDetailsSnapshot, user_id: str, *, reveal_role: bool) -> str:
    participant = next(candidate for candidate in snapshot.participants if candidate.user_id == user_id)
    if not reveal_role:
        return "Hidden"

    if participant.faction == "Merchant":
        label = f"Role: {participant.role_name}"
    else:
        label = f"Faction: {participant.faction} / Role: {participant.role_name}"
    if (
        snapshot.current_police_leader_user_id == participant.user_id
        and participant.life_state == "alive"
        and participant.role_name != "Chief of Police"
    ):
        label = f"{label} [Acting Chief of Police]"
    if (
        snapshot.current_mob_leader_user_id == participant.user_id
        and participant.life_state == "alive"
        and participant.role_name != "Mob Boss"
    ):
        label = f"{label} [Mob Boss]"
    return label


def _participant_status_label(snapshot: GameDetailsSnapshot, user_id: str) -> str:
    participant = next(candidate for candidate in snapshot.participants if candidate.user_id == user_id)
    if (
        participant.life_state == "alive"
        and snapshot.phase == "trial_voting"
        and snapshot.pending_trial is not None
        and user_id in snapshot.pending_trial.silenced_user_ids
    ):
        return "silenced"
    if (
        participant.life_state == "alive"
        and snapshot.phase == "trial_voting"
        and snapshot.pending_trial is not None
        and snapshot.pending_trial.accused_user_id == participant.user_id
    ):
        return "on_trial"
    return participant.life_state


def _inventory_text(inventory: list[object]) -> str:
    if not inventory:
        return "None"
    names = [str(getattr(item, "display_name", "")).strip() for item in inventory]
    present = [name for name in names if name]
    if not present:
        return "None"
    return ", ".join(present)


def _is_trial_juror(snapshot: GameDetailsSnapshot, user_id: str) -> bool:
    if snapshot.phase != "trial_voting" or snapshot.pending_trial is None:
        return False
    return user_id in snapshot.pending_trial.jury_user_ids


def _murdered_by_username(
    snapshot: GameDetailsSnapshot,
    user_id: str,
    participant_name_by_id: dict[str, str],
) -> str | None:
    participant = next(candidate for candidate in snapshot.participants if candidate.user_id == user_id)
    if participant.life_state != "dead" or not participant.murdered_by_user_id:
        return None
    return participant_name_by_id.get(participant.murdered_by_user_id, participant.murdered_by_user_id)


def _convicted_by_label(participant: object, participant_name_by_id: dict[str, str]) -> str | None:
    life_state = str(getattr(participant, "life_state", ""))
    if life_state != "jailed":
        return None
    convicted_by_user_ids = getattr(participant, "convicted_by_user_ids", [])
    if not convicted_by_user_ids:
        return None
    names = [participant_name_by_id.get(user_id, user_id) for user_id in convicted_by_user_ids]
    return ", ".join(names)


def _accused_by_username(participant: object, participant_name_by_id: dict[str, str]) -> str | None:
    life_state = str(getattr(participant, "life_state", ""))
    if life_state != "jailed":
        return None
    accused_by_user_id = getattr(participant, "accused_by_user_id", None)
    if not accused_by_user_id:
        return None
    return participant_name_by_id.get(accused_by_user_id, accused_by_user_id)
