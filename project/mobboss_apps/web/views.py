from django.http import HttpRequest, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render

from project.mobboss_apps.gameplay.ports.internal import (
    AdvanceAccusedSelectionTimeoutCommand,
    KillGameCommand,
    ModeratorAddFundsCommand,
    ModeratorTransferFundsCommand,
    ModeratorTransferInventoryItemCommand,
    ReportDeathCommand,
)

from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.mobboss.moderator_access import user_can_create_moderated_room
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
            "moderator_access_unlocked": user_can_create_moderated_room(request.user),
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


def _resolve_return_target(request: HttpRequest, *, user_id: str) -> tuple[str, str]:
    active_room = _resolve_active_moderated_game_for_user(user_id)
    request_session = getattr(request, "session", None)
    active_game_id = str(request_session.get("active_game_id", "")).strip() if request_session is not None else ""
    active_game_status = ""
    if not active_game_id and active_room is not None and active_room.launched_game_id:
        active_game_id = active_room.launched_game_id
    if active_game_id:
        try:
            container = get_container()
            gameplay_inbound = container.gameplay_inbound_port
            session = gameplay_inbound.get_game_details(active_game_id)
            active_game_status = str(session.status or "").strip()
        except Exception:
            active_game_status = ""
    if active_game_id and active_game_status != "ended":
        return (f"/games/{active_game_id}/", "Return to Game")
    return ("/", "Return to Lobby")


@login_required(login_url="/auth/")
def options(request: HttpRequest) -> HttpResponse:
    user_id = str(request.user.id or request.user.username)
    active_room = _resolve_active_moderated_game_for_user(user_id)
    request_session = getattr(request, "session", None)
    active_game_id = str(request_session.get("active_game_id", "")).strip() if request_session is not None else ""
    if not active_game_id and active_room is not None and active_room.launched_game_id:
        active_game_id = active_room.launched_game_id
    moderator_report_death_players = []
    moderator_adjustment_players = []
    moderator_transfer_item_rows = []
    can_report_death = False
    if active_game_id:
        try:
            container = get_container()
            gameplay_inbound = container.gameplay_inbound_port
            session = gameplay_inbound.get_game_details(active_game_id)
            if active_room is not None and active_room.launched_game_id == active_game_id:
                moderator_adjustment_players = sorted(
                    list(session.participants),
                    key=lambda participant: participant.username.lower(),
                )
                moderator_report_death_players = sorted(
                    [
                        participant
                        for participant in moderator_adjustment_players
                        if participant.life_state == "alive"
                    ],
                    key=lambda participant: participant.username.lower(),
                )
                moderator_transfer_item_rows = sorted(
                    [
                        {
                            "owner_user_id": participant.user_id,
                            "owner_username": participant.username,
                            "item_id": inventory_item.item_id,
                            "item_display_name": inventory_item.display_name,
                        }
                        for participant in moderator_adjustment_players
                        for inventory_item in getattr(participant, "inventory", [])
                    ],
                    key=lambda row: (str(row["owner_username"]).lower(), str(row["item_display_name"]).lower()),
                )
                can_report_death = (
                    session.status == "in_progress"
                    and session.pending_trial is None
                    and bool(moderator_report_death_players)
                )
        except Exception:
            pass
    return_target_href, return_target_label = _resolve_return_target(request, user_id=user_id)
    return render(
        request,
        "web/options.html",
        {
            "active_room": active_room,
            "active_game_id": active_game_id,
            "can_kill_game": active_room is not None and bool(active_room.launched_game_id),
            "can_report_death": can_report_death,
            "moderator_report_death_players": moderator_report_death_players,
            "moderator_adjustment_players": moderator_adjustment_players,
            "moderator_transfer_item_rows": moderator_transfer_item_rows,
            "return_target_href": return_target_href,
            "return_target_label": return_target_label,
        },
    )


@login_required(login_url="/auth/")
def how_to_play(request: HttpRequest) -> HttpResponse:
    user_id = str(request.user.id or request.user.username)
    return_target_href, return_target_label = _resolve_return_target(request, user_id=user_id)
    return render(
        request,
        "web/how_to_play.html",
        {
            "return_target_href": return_target_href,
            "return_target_label": return_target_label,
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


@login_required(login_url="/auth/")
def moderator_add_funds(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("web-options")
    user_id = str(request.user.id or request.user.username)
    active_room = _resolve_active_moderated_game_for_user(user_id)
    if active_room is None or not active_room.launched_game_id:
        messages.error(request, "No active moderated game found.")
        return redirect("web-options")
    recipient_user_id = str(request.POST.get("recipient_user_id", "")).strip()
    amount_raw = str(request.POST.get("amount", "")).strip()
    if not recipient_user_id:
        messages.error(request, "Player is required.")
        return redirect("web-options")
    try:
        amount = int(amount_raw)
    except Exception:
        messages.error(request, "Amount must be a whole number.")
        return redirect("web-options")
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(active_room.launched_game_id)
        gameplay_inbound.moderator_add_funds(
            ModeratorAddFundsCommand(
                game_id=session.game_id,
                requested_by_user_id=user_id,
                recipient_user_id=recipient_user_id,
                amount=amount,
                expected_version=session.version,
            )
        )
        messages.success(request, "Funds added.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("web-options")


@login_required(login_url="/auth/")
def moderator_transfer_funds(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("web-options")
    user_id = str(request.user.id or request.user.username)
    active_room = _resolve_active_moderated_game_for_user(user_id)
    if active_room is None or not active_room.launched_game_id:
        messages.error(request, "No active moderated game found.")
        return redirect("web-options")
    from_user_id = str(request.POST.get("from_user_id", "")).strip()
    to_user_id = str(request.POST.get("to_user_id", "")).strip()
    amount_raw = str(request.POST.get("amount", "")).strip()
    if not from_user_id or not to_user_id:
        messages.error(request, "Source and destination players are required.")
        return redirect("web-options")
    try:
        amount = int(amount_raw)
    except Exception:
        messages.error(request, "Amount must be a whole number.")
        return redirect("web-options")
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(active_room.launched_game_id)
        gameplay_inbound.moderator_transfer_funds(
            ModeratorTransferFundsCommand(
                game_id=session.game_id,
                requested_by_user_id=user_id,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                amount=amount,
                expected_version=session.version,
            )
        )
        messages.success(request, "Funds transferred.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("web-options")


@login_required(login_url="/auth/")
def moderator_transfer_inventory_item(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("web-options")
    user_id = str(request.user.id or request.user.username)
    active_room = _resolve_active_moderated_game_for_user(user_id)
    if active_room is None or not active_room.launched_game_id:
        messages.error(request, "No active moderated game found.")
        return redirect("web-options")
    from_user_id = str(request.POST.get("from_user_id", "")).strip()
    to_user_id = str(request.POST.get("to_user_id", "")).strip()
    inventory_item_id = str(request.POST.get("inventory_item_id", "")).strip()
    if not from_user_id or not to_user_id or not inventory_item_id:
        messages.error(request, "Source, item, and destination are required.")
        return redirect("web-options")
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(active_room.launched_game_id)
        gameplay_inbound.moderator_transfer_inventory_item(
            ModeratorTransferInventoryItemCommand(
                game_id=session.game_id,
                requested_by_user_id=user_id,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                inventory_item_id=inventory_item_id,
                expected_version=session.version,
            )
        )
        messages.success(request, "Item transferred.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("web-options")
