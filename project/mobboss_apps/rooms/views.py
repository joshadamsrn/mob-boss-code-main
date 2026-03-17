from __future__ import annotations

from urllib.parse import quote_plus

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.rooms.ports.internal import (
    ITEM_CLASSIFICATIONS,
    ITEM_CLASSIFICATION_DISPLAY_NAMES,
    REQUIRED_ROOM_ITEM_CLASSIFICATIONS,
)
from project.mobboss_apps.rooms.ports.internal_requests_dto import (
    AssignRoomRoleRequestDTO,
    CreateRoomRequestDTO,
    DeactivateRoomItemRequestDTO,
    DeleteRoomRequestDTO,
    JoinRoomRequestDTO,
    LaunchGameFromRoomRequestDTO,
    LeaveRoomRequestDTO,
    RoomsIndexRequestDTO,
    RoomDetailRequestDTO,
    SetMemberBalanceRequestDTO,
    SetRoomReadinessRequestDTO,
    ShuffleRolesPageRequestDTO,
    UpsertRoomItemRequestDTO,
)
from project.mobboss_apps.rooms.src.room_service import minimum_launch_starting_balance

DEV_SEAT_USER_ID_PREFIX = "dev-seat-"


def _current_user_id(request: HttpRequest) -> str:
    return str(request.user.id or request.user.username)


def _is_dev_seat_user_id(user_id: str) -> bool:
    return str(user_id).startswith(DEV_SEAT_USER_ID_PREFIX)


def _next_dev_seat_number(members: list) -> int:
    highest = 0
    for member in members:
        user_id = str(member.user_id)
        if not _is_dev_seat_user_id(user_id):
            continue
        suffix = user_id[len(DEV_SEAT_USER_ID_PREFIX) :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return highest + 1


def _build_dev_seat_user_id(number: int) -> str:
    return f"{DEV_SEAT_USER_ID_PREFIX}{number:02d}"


def _parse_bool_flag(raw_value: object) -> bool:
    value = str(raw_value if raw_value is not None else "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _room_detail_url(room_id: str, as_user_id: str = "", simulate_actions: bool = False) -> str:
    query_parts: list[str] = []
    if as_user_id:
        query_parts.append(f"as_user_id={quote_plus(as_user_id)}")
    if simulate_actions:
        query_parts.append("simulate_actions=1")
    if query_parts:
        return f"/rooms/{room_id}/?{'&'.join(query_parts)}"
    return f"/rooms/{room_id}/"


def _redirect_to_room_detail_with_context(request: HttpRequest, room_id: str) -> HttpResponse:
    as_user_id = str(request.POST.get("as_user_id", request.GET.get("as_user_id", ""))).strip()
    simulate_actions = _parse_bool_flag(request.POST.get("simulate_actions", request.GET.get("simulate_actions", "")))
    return redirect(_room_detail_url(room_id=room_id, as_user_id=as_user_id, simulate_actions=simulate_actions))


@login_required(login_url="/auth/")
def index(request: HttpRequest) -> HttpResponse:
    RoomsIndexRequestDTO.from_payload({"method": request.method, "user_id": _current_user_id(request)})
    _container = get_container()
    return redirect("web-lobby")


@login_required(login_url="/auth/")
def create_room(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("web-lobby")

    try:
        payload = {
            "name": request.POST.get("name", ""),
            "creator_user_id": _current_user_id(request),
            "creator_username": request.user.username,
        }
        dto = CreateRoomRequestDTO.from_payload(payload)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        room = rooms_inbound.create_room(dto.to_command())
        messages.success(request, "Room created.")
        return redirect("rooms-detail", room_id=room.room_id)
    except Exception as exc:
        messages.error(request, str(exc))


@login_required(login_url="/auth/")
def detail(request: HttpRequest, room_id: str) -> HttpResponse:
    try:
        actor_user_id = _current_user_id(request)
        detail_dto = RoomDetailRequestDTO.from_payload(
            {
                "room_id": room_id,
                "user_id": actor_user_id,
                "username": request.user.username,
                "autojoin": request.GET.get("autojoin", ""),
            }
        )
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        room_item_media_outbound = container.room_item_media_outbound_port
        room = rooms_inbound.get_room_details(detail_dto.room_id)
        actor_is_moderator = room.moderator_user_id == actor_user_id
        if room.status == "ended":
            messages.info(request, "Room closed.")
            return redirect("web-lobby")
        joined_members = [member for member in room.members if member.membership_status == "joined"]
        actor_current_member = next((member for member in joined_members if member.user_id == actor_user_id), None)

        autojoin_requested = detail_dto.autojoin_requested
        if autojoin_requested and not actor_is_moderator and room.status == "lobby" and actor_current_member is None:
            try:
                join_dto = JoinRoomRequestDTO.from_payload(
                    {"room_id": detail_dto.room_id, "user_id": actor_user_id, "username": detail_dto.username}
                )
                rooms_inbound.join_room(join_dto.to_command())
                return redirect("rooms-detail", room_id=detail_dto.room_id)
            except Exception as exc:
                messages.error(request, str(exc))
                room = rooms_inbound.get_room_details(detail_dto.room_id)

        joined_members = [member for member in room.members if member.membership_status == "joined"]
        actor_current_member = next((member for member in joined_members if member.user_id == actor_user_id), None)
        dev_mode_enabled = container.room_dev_mode

        requested_view_as_user_id = str(request.GET.get("as_user_id", "")).strip()
        requested_simulate_actions = _parse_bool_flag(request.GET.get("simulate_actions", ""))
        allowed_view_as_user_ids = {member.user_id for member in joined_members}
        current_user_id = actor_user_id
        if actor_is_moderator and dev_mode_enabled and requested_view_as_user_id in allowed_view_as_user_ids:
            current_user_id = requested_view_as_user_id
        is_view_as_mode = current_user_id != actor_user_id
        simulate_actions_enabled = actor_is_moderator and dev_mode_enabled and is_view_as_mode and requested_simulate_actions

        current_member = next((member for member in joined_members if member.user_id == current_user_id), None)
        is_moderator = room.moderator_user_id == current_user_id
        total_joined_count = len(joined_members)
        player_members = [member for member in joined_members if member.user_id != room.moderator_user_id]
        moderator_member = next((member for member in room.members if member.user_id == room.moderator_user_id), None)
        player_member_rows = [member for member in room.members if member.user_id != room.moderator_user_id]
        player_count = len(player_members)
        launch_min_players = container.room_min_launch_players
        total_player_starting_balance = max(
            sum(member.starting_balance for member in player_members),
            minimum_launch_starting_balance(launch_min_players),
        )
        is_joined = current_member is not None
        is_lobby = room.status == "lobby"
        has_min_players = player_count >= launch_min_players
        under_capacity = player_count <= 25
        all_joined_ready = all(member.is_ready for member in player_members)
        can_launch = actor_is_moderator and not is_view_as_mode and is_lobby and has_min_players and under_capacity and all_joined_ready
        dev_launch_override_active = container.room_dev_mode and launch_min_players != 7
        room_state_poll_interval_seconds = container.room_state_poll_interval_seconds
        room_auto_shuffle_interval_seconds = container.room_auto_shuffle_interval_seconds
        waitlist = []
        dev_seat_user_ids = [member.user_id for member in room.members if _is_dev_seat_user_id(member.user_id)]
        dev_seat_members = [
            member for member in player_members if member.user_id in dev_seat_user_ids and member.membership_status == "joined"
        ]
        can_manage_dev_seats = actor_is_moderator and dev_mode_enabled and is_lobby and not is_view_as_mode

        view_tabs: list[dict[str, str | bool]] = []
        if actor_is_moderator and dev_mode_enabled:
            view_tabs.append(
                {
                    "label": "Moderator",
                    "href": _room_detail_url(room.room_id),
                    "is_active": not is_view_as_mode,
                }
            )
            for member in player_members:
                label = member.username
                if member.user_id in dev_seat_user_ids:
                    label = f"{label} [Dev]"
                view_tabs.append(
                    {
                        "label": label,
                        "href": _room_detail_url(
                            room.room_id,
                            as_user_id=member.user_id,
                            simulate_actions=simulate_actions_enabled,
                        ),
                        "is_active": member.user_id == current_user_id,
                    }
                )

        viewing_user_label = current_member.username if current_member else current_user_id
        required_item_classifications = set(REQUIRED_ROOM_ITEM_CLASSIFICATIONS)
        catalog_items = [
            {
                "index": idx,
                "item": item,
                "full_image_path": item.image_path,
                "tile_image_path": room_item_media_outbound.resolve_room_item_tile_image_url(item.image_path),
                "classification_display_name": ITEM_CLASSIFICATION_DISPLAY_NAMES.get(
                    item.classification, item.classification
                ),
                "is_required": item.classification in required_item_classifications,
            }
            for idx, item in enumerate(room.items, start=1)
        ]

        return render(
            request,
            "rooms/detail.html",
            {
                "room": room,
                "is_moderator": is_moderator,
                "actor_is_moderator": actor_is_moderator,
                "is_joined": is_joined,
                "current_user_id": current_user_id,
                "is_view_as_mode": is_view_as_mode,
                "simulate_actions_enabled": simulate_actions_enabled,
                "viewing_user_label": viewing_user_label,
                "current_member": current_member,
                "joined_members": joined_members,
                "moderator_member": moderator_member,
                "player_member_rows": player_member_rows,
                "joined_count": total_joined_count,
                "player_count": player_count,
                "total_player_starting_balance": total_player_starting_balance,
                "waitlist": waitlist,
                "waitlist_count": len(waitlist),
                "catalog_items": catalog_items,
                "item_classifications": ITEM_CLASSIFICATIONS,
                "is_lobby": is_lobby,
                "launch_min_players": launch_min_players,
                "dev_launch_override_active": dev_launch_override_active,
                "has_min_players": has_min_players,
                "under_capacity": under_capacity,
                "all_joined_ready": all_joined_ready,
                "can_launch": can_launch,
                "dev_mode_enabled": dev_mode_enabled,
                "can_manage_dev_seats": can_manage_dev_seats,
                "dev_seat_user_ids": dev_seat_user_ids,
                "dev_seat_members": dev_seat_members,
                "view_tabs": view_tabs,
                "room_state_poll_interval_seconds": room_state_poll_interval_seconds,
                "room_auto_shuffle_interval_seconds": room_auto_shuffle_interval_seconds,
            },
        )
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect("web-lobby")


@login_required(login_url="/auth/")
def join_room(request: HttpRequest, room_id: str) -> HttpResponse:
    try:
        dto = JoinRoomRequestDTO.from_payload(
            {"room_id": room_id, "user_id": _current_user_id(request), "username": request.user.username}
        )
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        rooms_inbound.join_room(dto.to_command())
        messages.success(request, "Joined room.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("rooms-detail", room_id=room_id)


@login_required(login_url="/auth/")
def leave_room(request: HttpRequest, room_id: str) -> HttpResponse:
    try:
        dto = LeaveRoomRequestDTO.from_payload({"room_id": room_id, "user_id": _current_user_id(request)})
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        rooms_inbound.leave_room(dto.to_command())
        messages.success(request, "Left room.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("web-lobby")


@login_required(login_url="/auth/")
def add_dev_seat(request: HttpRequest, room_id: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("rooms-detail", room_id=room_id)
    try:
        actor_user_id = _current_user_id(request)
        container = get_container()
        if not container.room_dev_mode:
            messages.error(request, str(exc)) PermissionError("Dev seat controls are disabled.")
        rooms_inbound = container.rooms_inbound_port
        room = rooms_inbound.get_room_details(room_id)
        if room.moderator_user_id != actor_user_id:
            messages.error(request, str(exc)) PermissionError("Only moderator can add dev seats.")
        if room.status != "lobby":
            messages.error(request, str(exc)) ValueError("Dev seats can only be managed in lobby.")

        seat_number = _next_dev_seat_number(room.members)
        seat_user_id = _build_dev_seat_user_id(seat_number)
        seat_name = str(request.POST.get("seat_name", "")).strip() or f"Dev Seat {seat_number:02d}"
        join_dto = JoinRoomRequestDTO.from_payload(
            {
                "room_id": room_id,
                "user_id": seat_user_id,
                "username": seat_name,
            }
        )
        rooms_inbound.join_room(join_dto.to_command())
        messages.success(request, f"Added {seat_name}.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_room_detail_with_context(request, room_id=room_id)


@login_required(login_url="/auth/")
def remove_dev_seat(request: HttpRequest, room_id: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("rooms-detail", room_id=room_id)
    try:
        actor_user_id = _current_user_id(request)
        seat_user_id = str(request.POST.get("user_id", "")).strip()
        if not _is_dev_seat_user_id(seat_user_id):
            messages.error(request, str(exc)) ValueError("Target is not a dev seat.")
        container = get_container()
        if not container.room_dev_mode:
            messages.error(request, str(exc)) PermissionError("Dev seat controls are disabled.")
        rooms_inbound = container.rooms_inbound_port
        room = rooms_inbound.get_room_details(room_id)
        if room.moderator_user_id != actor_user_id:
            messages.error(request, str(exc)) PermissionError("Only moderator can remove dev seats.")
        if room.status != "lobby":
            messages.error(request, str(exc)) ValueError("Dev seats can only be managed in lobby.")

        leave_dto = LeaveRoomRequestDTO.from_payload({"room_id": room_id, "user_id": seat_user_id})
        rooms_inbound.leave_room(leave_dto.to_command())
        messages.success(request, "Dev seat removed.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_room_detail_with_context(request, room_id=room_id)


@login_required(login_url="/auth/")
def set_ready(request: HttpRequest, room_id: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("rooms-detail", room_id=room_id)
    try:
        payload = {
            "room_id": room_id,
            "requested_by_user_id": _current_user_id(request),
            "user_id": request.POST.get("user_id", _current_user_id(request)),
            "is_ready": request.POST.get("is_ready", "false"),
        }
        dto = SetRoomReadinessRequestDTO.from_payload(payload)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        rooms_inbound.set_room_readiness(dto.to_command())
        messages.success(request, "Readiness updated.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_room_detail_with_context(request, room_id=room_id)


@login_required(login_url="/auth/")
def assign_role(request: HttpRequest, room_id: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("rooms-detail", room_id=room_id)
    try:
        payload = {
            "room_id": room_id,
            "moderator_user_id": _current_user_id(request),
            "target_user_id": request.POST.get("target_user_id", ""),
            "faction": request.POST.get("faction", ""),
            "role_name": request.POST.get("role_name", ""),
            "rank": request.POST.get("rank", "1"),
        }
        dto = AssignRoomRoleRequestDTO.from_payload(payload)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        rooms_inbound.assign_room_role(dto.to_command())
        messages.success(request, "Role assigned.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("rooms-detail", room_id=room_id)


@login_required(login_url="/auth/")
def set_balance(request: HttpRequest, room_id: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("rooms-detail", room_id=room_id)
    try:
        payload = {
            "room_id": room_id,
            "moderator_user_id": _current_user_id(request),
            "target_user_id": request.POST.get("target_user_id", ""),
            "starting_balance": request.POST.get("starting_balance", "0"),
        }
        dto = SetMemberBalanceRequestDTO.from_payload(payload)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        rooms_inbound.set_member_balance(dto.to_command())
        messages.success(request, "Balance updated.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("rooms-detail", room_id=room_id)


@login_required(login_url="/auth/")
def upsert_item(request: HttpRequest, room_id: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("rooms-detail", room_id=room_id)
    try:
        base_payload = {
            "room_id": room_id,
            "moderator_user_id": _current_user_id(request),
            "classification": request.POST.get("classification", "").strip(),
            "display_name": request.POST.get("display_name", ""),
            "base_price": request.POST.get("base_price", "0"),
            "image_path": "",
        }
        base_dto = UpsertRoomItemRequestDTO.from_payload(base_payload)

        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        room_item_media_outbound = container.room_item_media_outbound_port
        image_path = ""
        if "item_image" in request.FILES:
            upload = request.FILES["item_image"]
            image_path = room_item_media_outbound.save_room_item_image(
                room_id=base_dto.room_id,
                classification=base_dto.classification,
                original_filename=upload.name,
                chunks=upload.chunks(),
            )
        else:
            room = rooms_inbound.get_room_details(base_dto.room_id)
            existing_item = next((item for item in room.items if item.classification == base_dto.classification), None)
            if existing_item is not None:
                image_path = existing_item.image_path

        dto = UpsertRoomItemRequestDTO.from_payload(
            {
                "room_id": base_dto.room_id,
                "moderator_user_id": base_dto.moderator_user_id,
                "classification": base_dto.classification,
                "display_name": base_dto.display_name,
                "base_price": base_dto.base_price,
                "image_path": image_path,
            }
        )
        rooms_inbound.upsert_room_item(dto.to_command())
        messages.success(request, "Catalog item saved.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("rooms-detail", room_id=room_id)


@login_required(login_url="/auth/")
def deactivate_item(request: HttpRequest, room_id: str, classification: str) -> HttpResponse:
    try:
        dto = DeactivateRoomItemRequestDTO.from_payload(
            {"room_id": room_id, "moderator_user_id": _current_user_id(request), "classification": classification}
        )
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        rooms_inbound.deactivate_room_item(dto.to_command())
        messages.success(request, "Catalog item deactivated.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("rooms-detail", room_id=room_id)


@login_required(login_url="/auth/")
def launch_game(request: HttpRequest, room_id: str) -> HttpResponse:
    try:
        dto = LaunchGameFromRoomRequestDTO.from_payload({"room_id": room_id, "requested_by_user_id": _current_user_id(request)})
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        game_id = rooms_inbound.launch_game_from_room(dto.to_command())
        messages.success(request, f"Game launched: {game_id}")
        return redirect("gameplay-detail", game_id=game_id)
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("rooms-detail", room_id=room_id)


@login_required(login_url="/auth/")
def delete_room(request: HttpRequest, room_id: str) -> HttpResponse:
    try:
        dto = DeleteRoomRequestDTO.from_payload({"room_id": room_id, "requested_by_user_id": _current_user_id(request)})
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        rooms_inbound.delete_room(dto.to_command())
        messages.success(request, "Room deleted.")
        return redirect("web-lobby")
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect("rooms-detail", room_id=room_id)


@login_required(login_url="/auth/")
def shuffle_roles(request: HttpRequest, room_id: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("rooms-detail", room_id=room_id)
    payload = {
        "room_id": room_id,
        "moderator_user_id": _current_user_id(request),
        "seed": request.POST.get("seed"),
        "is_silent": (
            request.POST.get("silent", "").lower() == "true"
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        ),
    }
    dto = ShuffleRolesPageRequestDTO.from_payload(payload)
    is_silent = dto.is_silent
    try:
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        rooms_inbound.shuffle_room_roles(dto.to_command())
        if is_silent:
            return HttpResponse(status=204)
        messages.success(request, "Roles shuffled.")
    except Exception as exc:
        if is_silent:
            return HttpResponse(str(exc), status=400)
        messages.error(request, str(exc))
    return redirect("rooms-detail", room_id=room_id)

