from django.http import HttpRequest, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render
import time

from project.mobboss_apps.gameplay.ports.internal import (
    AdvanceAccusedSelectionTimeoutCommand,
    KillGameCommand,
    ReportDeathCommand,
)

from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.web.ports.internal_requests_dto import LobbyIndexRequestDTO


@login_required(login_url="/auth/")
def index(request: HttpRequest) -> HttpResponse:
    _dto = LobbyIndexRequestDTO.from_payload(
        {"method": request.method, "user_id": str(request.user.id or request.user.username)}
    )
    container = get_container()
    rooms_inbound = container.rooms_inbound_port
    rooms = rooms_inbound.list_active_rooms()
    lobby_rooms = [room for room in rooms if room.status == "lobby"]
    in_progress_rooms = [room for room in rooms if room.status == "in_progress"]
    return render(
        request,
        "web/lobby.html",
        {
            "lobby_rooms": lobby_rooms,
            "in_progress_rooms": in_progress_rooms,
        },
    )


def _resolve_active_moderated_game_for_user(user_id: str):
    container = get_container()
    rooms_inbound = container.rooms_inbound_port
    rooms = rooms_inbound.list_active_rooms()
    for room_summary in rooms:
        if room_summary.status != "in_progress":
            continue
        if room_summary.moderator_user_id != user_id:
            continue
        room_details = rooms_inbound.get_room_details(room_summary.room_id)
        if room_details.launched_game_id:
            return room_details
    return None


@login_required(login_url="/auth/")
def options(request: HttpRequest) -> HttpResponse:
    user_id = str(request.user.id or request.user.username)
    active_room = _resolve_active_moderated_game_for_user(user_id)
    request_session = getattr(request, "session", None)
    active_game_id = str(request_session.get("active_game_id", "")).strip() if request_session is not None else ""
    if not active_game_id and active_room is not None and active_room.launched_game_id:
        active_game_id = active_room.launched_game_id
    moderator_report_death_players = []
    can_report_death = False
    can_advance_accused_timeout = False
    if active_room is not None and active_room.launched_game_id:
        try:
            container = get_container()
            gameplay_inbound = container.gameplay_inbound_port
            session = gameplay_inbound.get_game_details(active_room.launched_game_id)
            moderator_report_death_players = sorted(
                [
                    participant
                    for participant in session.participants
                    if participant.life_state == "alive"
                ],
                key=lambda participant: participant.username.lower(),
            )
            can_report_death = (
                session.status == "in_progress"
                and session.pending_trial is None
                and bool(moderator_report_death_players)
            )
            deadline = (
                session.pending_trial.accused_selection_deadline_epoch_seconds
                if session.pending_trial is not None
                else None
            )
            can_advance_accused_timeout = (
                session.status == "in_progress"
                and session.phase == "accused_selection"
                and session.pending_trial is not None
                and deadline is not None
                and int(time.time()) >= deadline
            )
        except Exception:
            can_advance_accused_timeout = False
    return render(
        request,
        "web/options.html",
        {
            "active_room": active_room,
            "active_game_id": active_game_id,
            "can_kill_game": active_room is not None and bool(active_room.launched_game_id),
            "can_advance_accused_timeout": can_advance_accused_timeout,
            "can_report_death": can_report_death,
            "moderator_report_death_players": moderator_report_death_players,
        },
    )


@login_required(login_url="/auth/")
def kill_game(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("web-options")
    user_id = str(request.user.id or request.user.username)
    active_room = _resolve_active_moderated_game_for_user(user_id)
    if active_room is None or not active_room.launched_game_id:
        messages.error(request, "No active moderated game found to kill.")
        return redirect("web-options")
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        gameplay_inbound.kill_game(
            KillGameCommand(
                game_id=active_room.launched_game_id,
                requested_by_user_id=user_id,
            )
        )
        messages.success(request, "Game killed.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("web-options")


@login_required(login_url="/auth/")
def advance_accused_timeout(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("web-options")
    user_id = str(request.user.id or request.user.username)
    active_room = _resolve_active_moderated_game_for_user(user_id)
    if active_room is None or not active_room.launched_game_id:
        messages.error(request, "No active moderated game found.")
        return redirect("web-options")
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(active_room.launched_game_id)
        gameplay_inbound.advance_accused_selection_timeout(
            AdvanceAccusedSelectionTimeoutCommand(
                game_id=session.game_id,
                requested_by_user_id=user_id,
                expected_version=session.version,
            )
        )
        messages.success(request, "Accused-selection timeout advanced.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("web-options")


@login_required(login_url="/auth/")
def moderator_report_death(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("web-options")
    user_id = str(request.user.id or request.user.username)
    active_room = _resolve_active_moderated_game_for_user(user_id)
    if active_room is None or not active_room.launched_game_id:
        messages.error(request, "No active moderated game found.")
        return redirect("web-options")
    murdered_user_id = str(request.POST.get("murdered_user_id", "")).strip()
    murderer_user_id = str(request.POST.get("murderer_user_id", "")).strip()
    attack_classification = str(request.POST.get("attack_classification", "")).strip()
    if not murdered_user_id:
        messages.error(request, "Murdered Player is required.")
        return redirect("web-options")
    if not attack_classification:
        messages.error(request, "Attack Type is required.")
        return redirect("web-options")
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(active_room.launched_game_id)
        gameplay_inbound.report_death(
            ReportDeathCommand(
                game_id=session.game_id,
                murdered_user_id=murdered_user_id,
                reported_by_user_id=user_id,
                expected_version=session.version,
                murderer_user_id=murderer_user_id,
                attack_classification=attack_classification,
            )
        )
        messages.success(request, "Death reported.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("web-options")
