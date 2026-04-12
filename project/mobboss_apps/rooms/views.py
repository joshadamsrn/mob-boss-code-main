from __future__ import annotations

from dataclasses import replace
import json
from urllib.parse import quote_plus

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.mobboss.devtools import (
    dev_tools_min_launch_players,
    is_dev_tools_user,
    user_dev_mode_enabled,
)
from project.mobboss_apps.mobboss.moderator_access import (
    grant_moderator_access,
    moderator_access_code_is_valid,
    user_can_create_moderated_room,
)
from project.mobboss_apps.rooms.ports.internal import (
    ITEM_CLASSIFICATIONS,
    ITEM_CLASSIFICATION_DISPLAY_NAMES,
    REQUIRED_ROOM_ITEM_CLASSIFICATIONS,
)
from project.mobboss_apps.rooms.presets import (
    MAX_ROOM_SUPPLY_PRESETS,
    build_preset_payload_from_room_items,
    build_preset_payload_from_rows,
    build_room_items_from_rows,
    default_image_path_for_classification,
    get_room_supply_preset_for_user,
    list_room_supply_presets_for_user,
    normalize_generated_supply_rows,
    preset_rows_from_payload,
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
    SetMobSecretWordRequestDTO,
    SetRoomReadinessRequestDTO,
    ShuffleRolesPageRequestDTO,
    UpsertRoomItemRequestDTO,
)
from project.mobboss_apps.rooms.src.room_service import (
    MERCHANT_ROLE_TITLES,
    MOB_ROLE_TITLES,
    POLICE_ROLE_TITLES,
    RoomsService,
    minimum_launch_starting_balance,
)

DEV_SEAT_USER_ID_PREFIX = "dev-seat-"
_ROLE_ASSIGNMENT_BY_TITLE = {
    **{
        title: {"faction": "Police", "role_name": title, "rank": idx + 1}
        for idx, title in enumerate(POLICE_ROLE_TITLES)
    },
    **{
        title: {"faction": "Mob", "role_name": title, "rank": idx + 1}
        for idx, title in enumerate(MOB_ROLE_TITLES)
    },
    **{
        title: {"faction": "Merchant", "role_name": title, "rank": 1}
        for title in MERCHANT_ROLE_TITLES
    },
}
_ROLE_ASSIGNMENT_CHOICES = list(_ROLE_ASSIGNMENT_BY_TITLE.values())


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


def _resolve_role_assignment_payload(request: HttpRequest) -> dict[str, str]:
    role_name = str(request.POST.get("role_name", "")).strip()
    faction = str(request.POST.get("faction", "")).strip()
    rank = str(request.POST.get("rank", "")).strip()
    if role_name and faction and rank:
        return {"role_name": role_name, "faction": faction, "rank": rank}
    assignment = _ROLE_ASSIGNMENT_BY_TITLE.get(role_name)
    if assignment is None:
        return {"role_name": role_name, "faction": faction, "rank": rank}
    return {
        "role_name": assignment["role_name"],
        "faction": assignment["faction"],
        "rank": str(assignment["rank"]),
    }


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


def _json_error(message: str, *, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message}, status=status)


def _json_ok(data: dict[str, object] | None = None, *, status: int = 200) -> JsonResponse:
    return JsonResponse({"ok": True, "data": data or {}}, status=status)


def _require_moderator_lobby_room(request: HttpRequest, room_id: str, *, container):
    room = container.rooms_inbound_port.get_room_details(room_id)
    if room.moderator_user_id != _current_user_id(request):
        raise PermissionError("Only moderator can manage central supply presets.")
    if room.status != "lobby":
        raise ValueError("Central supply presets can only be managed while the room is in lobby.")
    return room


def _replace_room_catalog(*, container, room, items) -> None:
    container.rooms_outbound_port.save_room(replace(room, items=list(items)))


def _parse_generated_supply_rows(request: HttpRequest):
    raw_rows = str(request.POST.get("generated_rows", "")).strip()
    if not raw_rows:
        raise ValueError("Generated central supply rows are required.")
    try:
        payload = json.loads(raw_rows)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid generated central supply payload.") from exc
    if not isinstance(payload, list):
        raise ValueError("Generated central supply payload must be a list.")
    dict_rows = [row for row in payload if isinstance(row, dict)]
    if len(dict_rows) != len(payload):
        raise ValueError("Generated central supply payload contains invalid rows.")
    rows = normalize_generated_supply_rows(dict_rows)
    if not rows:
        raise ValueError("At least one central supply item is required.")
    return rows


def _room_rows_with_saved_images(request: HttpRequest, rows, *, room_id: str, container):
    room_rows = []
    room_item_media_outbound = container.room_item_media_outbound_port
    for row in rows:
        upload_key = f"item_image__{row.classification}"
        if upload_key in request.FILES:
            upload = request.FILES[upload_key]
            image_path = room_item_media_outbound.save_room_item_image(
                room_id=room_id,
                classification=row.classification,
                original_filename=upload.name,
                chunks=upload.chunks(),
            )
        else:
            image_path = row.image_path or default_image_path_for_classification(row.classification)
        room_rows.append(replace(row, image_path=image_path))
    return room_rows


def _preset_rows_with_saved_images(request: HttpRequest, rows, *, preset, container):
    preset_rows = []
    room_item_media_outbound = container.room_item_media_outbound_port
    for row in rows:
        upload_key = f"item_image__{row.classification}"
        if upload_key in request.FILES:
            upload = request.FILES[upload_key]
            image_path = room_item_media_outbound.save_preset_item_image(
                user_id=str(request.user.id),
                preset_id=preset.id,
                classification=row.classification,
                original_filename=upload.name,
                chunks=upload.chunks(),
            )
        else:
            source_image_path = row.image_path or default_image_path_for_classification(row.classification)
            image_path = room_item_media_outbound.clone_item_image_to_preset(
                user_id=str(request.user.id),
                preset_id=preset.id,
                classification=row.classification,
                source_image_path=source_image_path,
            ) or source_image_path
        preset_rows.append(replace(row, image_path=image_path or default_image_path_for_classification(row.classification)))
    return preset_rows


def _request_dev_mode_enabled(request: HttpRequest, *, container) -> bool:
    return user_dev_mode_enabled(user=request.user, room_dev_mode=container.room_dev_mode)


def _effective_launch_min_players(request: HttpRequest, *, container) -> int:
    if container.room_dev_mode or not is_dev_tools_user(request.user):
        return container.room_min_launch_players
    return dev_tools_min_launch_players()


def _rooms_inbound_for_launch(request: HttpRequest, *, container):
    if container.room_dev_mode or not is_dev_tools_user(request.user):
        return container.rooms_inbound_port
    return RoomsService(
        repository=container.rooms_outbound_port,
        minimum_launch_players=dev_tools_min_launch_players(),
        gameplay_inbound_port=container.gameplay_inbound_port,
    )


def _set_active_game_session(request: HttpRequest, *, game_id: str, room_id: str) -> None:
    session_store = getattr(request, "session", None)
    if session_store is None:
        return
    session_store["active_game_id"] = game_id
    session_store["active_room_id"] = room_id


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
        if not user_can_create_moderated_room(request.user):
            submitted_code = request.POST.get("moderator_access_code", "")
            if not moderator_access_code_is_valid(submitted_code):
                raise PermissionError("Valid moderator permission code required to create a room.")
            if not grant_moderator_access(request.user):
                raise PermissionError("Unable to save moderator access for this account.")

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
        return redirect("web-lobby")


@login_required(login_url="/auth/")
def detail(request: HttpRequest, room_id: str) -> HttpResponse:
    try:
        actor_user_id = _current_user_id(request)
        detail_dto = RoomDetailRequestDTO.from_payload(
            {
                "room_id": room_id,
                "user_id": actor_user_id,
                "username": request.user.username,
                "autojoin": _parse_bool_flag(request.GET.get("autojoin")),
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
        if room.status == "in_progress":
            if actor_current_member is None:
                messages.info(request, "Game already in progress.")
                return redirect("web-lobby")
            if room.launched_game_id:
                _set_active_game_session(request, game_id=room.launched_game_id, room_id=room.room_id)
                return redirect("gameplay-detail", game_id=room.launched_game_id)


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
        dev_mode_enabled = _request_dev_mode_enabled(request, container=container)

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
        launch_min_players = _effective_launch_min_players(request, container=container)
        total_player_starting_balance = max(
            sum(member.starting_balance for member in player_members),
            minimum_launch_starting_balance(launch_min_players),
        )
        is_joined = current_member is not None
        is_lobby = room.status == "lobby"
        has_min_players = player_count >= launch_min_players
        under_capacity = player_count <= 25
        all_joined_ready = all(member.is_ready for member in player_members)
        secret_word_ready = bool(str(room.secret_mob_word).strip())
        central_supply_ready = any(item.is_active for item in room.items)
        can_launch = (
            actor_is_moderator
            and not is_view_as_mode
            and is_lobby
            and has_min_players
            and under_capacity
            and all_joined_ready
            and secret_word_ready
            and central_supply_ready
        )
        dev_launch_override_active = dev_mode_enabled and launch_min_players != 7
        room_state_poll_interval_seconds = container.room_state_poll_interval_seconds
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
                "fallback_image_path": default_image_path_for_classification(item.classification),
                "classification_display_name": ITEM_CLASSIFICATION_DISPLAY_NAMES.get(
                    item.classification, item.classification
                ),
                "is_required": item.classification in required_item_classifications,
            }
            for idx, item in enumerate(room.items, start=1)
        ]
        central_supply_presets = (
            list_room_supply_presets_for_user(request.user)
            if actor_is_moderator and is_lobby and not is_view_as_mode
            else []
        )

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
                "secret_word_ready": secret_word_ready,
                "central_supply_ready": central_supply_ready,
                "can_launch": can_launch,
                "dev_mode_enabled": dev_mode_enabled,
                "can_manage_dev_seats": can_manage_dev_seats,
                "dev_seat_user_ids": dev_seat_user_ids,
                "dev_seat_members": dev_seat_members,
                "view_tabs": view_tabs,
                "role_assignment_choices": _ROLE_ASSIGNMENT_CHOICES,
                "room_state_poll_interval_seconds": room_state_poll_interval_seconds,
                "central_supply_presets": central_supply_presets,
                "max_room_supply_presets": MAX_ROOM_SUPPLY_PRESETS,
            },
        )
    except Exception as exc:
        raise


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
        if not _request_dev_mode_enabled(request, container=container):
            raise PermissionError("Dev seat controls are disabled.")
        rooms_inbound = container.rooms_inbound_port
        room = rooms_inbound.get_room_details(room_id)
        if room.moderator_user_id != actor_user_id:
            raise PermissionError("Only moderator can add dev seats.")
        if room.status != "lobby":
            raise ValueError("Dev seats can only be managed in lobby.")

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
            raise ValueError("Target is not a dev seat.")
        container = get_container()
        if not _request_dev_mode_enabled(request, container=container):
            raise PermissionError("Dev seat controls are disabled.")
        rooms_inbound = container.rooms_inbound_port
        room = rooms_inbound.get_room_details(room_id)
        if room.moderator_user_id != actor_user_id:
            raise PermissionError("Only moderator can remove dev seats.")
        if room.status != "lobby":
            raise ValueError("Dev seats can only be managed in lobby.")

        leave_dto = LeaveRoomRequestDTO.from_payload({"room_id": room_id, "user_id": seat_user_id})
        rooms_inbound.leave_room(leave_dto.to_command())
        messages.success(request, "Dev seat removed.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_room_detail_with_context(request, room_id=room_id)


@login_required(login_url="/auth/")
def mark_all_ready(request: HttpRequest, room_id: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("rooms-detail", room_id=room_id)
    try:
        actor_user_id = _current_user_id(request)
        container = get_container()
        if not _request_dev_mode_enabled(request, container=container):
            raise PermissionError("Dev ready controls are disabled.")
        rooms_inbound = container.rooms_inbound_port
        room = rooms_inbound.get_room_details(room_id)
        if room.moderator_user_id != actor_user_id:
            raise PermissionError("Only moderator can mark all players ready.")
        if room.status != "lobby":
            raise ValueError("Ready controls can only be used in lobby.")

        ready_count = 0
        for member in room.members:
            if member.user_id == room.moderator_user_id or member.membership_status != "joined" or member.is_ready:
                continue
            dto = SetRoomReadinessRequestDTO.from_payload(
                {
                    "room_id": room_id,
                    "requested_by_user_id": actor_user_id,
                    "user_id": member.user_id,
                    "is_ready": "true",
                }
            )
            rooms_inbound.set_room_readiness(dto.to_command())
            ready_count += 1
        messages.success(request, f"Marked {ready_count} player(s) ready.")
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
        container = get_container()
        if not _request_dev_mode_enabled(request, container=container):
            raise ValueError("Role assignment is only available in dev mode.")
        resolved_role = _resolve_role_assignment_payload(request)
        payload = {
            "room_id": room_id,
            "moderator_user_id": _current_user_id(request),
            "target_user_id": request.POST.get("target_user_id", ""),
            "faction": resolved_role["faction"],
            "role_name": resolved_role["role_name"],
            "rank": resolved_role["rank"] or "1",
        }
        dto = AssignRoomRoleRequestDTO.from_payload(payload)
        rooms_inbound = container.rooms_inbound_port
        rooms_inbound.assign_room_role(dto.to_command())
        messages.success(request, "Role assigned.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_room_detail_with_context(request, room_id=room_id)


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
            image_path = str(request.POST.get("image_path", "")).strip()
            if not image_path:
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
def replace_catalog(request: HttpRequest, room_id: str) -> JsonResponse:
    if request.method != "POST":
        return _json_error("POST required.", status=405)
    try:
        container = get_container()
        room = _require_moderator_lobby_room(request, room_id, container=container)
        rows = _parse_generated_supply_rows(request)
        room_rows = _room_rows_with_saved_images(request, rows, room_id=room_id, container=container)
        _replace_room_catalog(container=container, room=room, items=build_room_items_from_rows(room_rows))
        return _json_ok({"saved_count": len(room_rows)})
    except Exception as exc:
        return _json_error(str(exc))


@login_required(login_url="/auth/")
def save_catalog_as_preset(request: HttpRequest, room_id: str) -> JsonResponse:
    if request.method != "POST":
        return _json_error("POST required.", status=405)
    try:
        preset_name = str(request.POST.get("preset_name", "")).strip()
        if not preset_name:
            raise ValueError("Preset name is required.")

        existing_presets = list_room_supply_presets_for_user(request.user)
        if len(existing_presets) >= MAX_ROOM_SUPPLY_PRESETS:
            raise ValueError(f"You can save up to {MAX_ROOM_SUPPLY_PRESETS} presets. Overwrite one or cancel.")

        container = get_container()
        room = _require_moderator_lobby_room(request, room_id, container=container)
        rows = _parse_generated_supply_rows(request)
        from rooms.models import RoomSupplyPreset

        preset = RoomSupplyPreset.objects.create(user_id=request.user.id, name=preset_name, payload={})
        preset_rows = _preset_rows_with_saved_images(request, rows, preset=preset, container=container)
        room_rows = [replace(row, image_path=row.image_path) for row in preset_rows]
        preset.payload = build_preset_payload_from_rows(preset_rows)
        preset.save(update_fields=["payload", "updated_at"])

        _replace_room_catalog(container=container, room=room, items=build_room_items_from_rows(room_rows))
        return _json_ok({"preset_id": preset.id, "preset_name": preset.name, "saved_count": len(room_rows)}, status=201)
    except Exception as exc:
        return _json_error(str(exc))


@login_required(login_url="/auth/")
def rename_preset(request: HttpRequest, room_id: str, preset_id: int) -> JsonResponse:
    if request.method != "POST":
        return _json_error("POST required.", status=405)
    try:
        _require_moderator_lobby_room(request, room_id, container=get_container())
        preset = get_room_supply_preset_for_user(request.user, preset_id)
        preset_name = str(request.POST.get("preset_name", "")).strip()
        if not preset_name:
            raise ValueError("Preset name is required.")
        preset.name = preset_name
        preset.save(update_fields=["name", "updated_at"])
        return _json_ok({"preset_id": preset.id, "preset_name": preset.name})
    except Exception as exc:
        return _json_error(str(exc))


@login_required(login_url="/auth/")
def delete_preset(request: HttpRequest, room_id: str, preset_id: int) -> JsonResponse:
    if request.method != "POST":
        return _json_error("POST required.", status=405)
    try:
        _require_moderator_lobby_room(request, room_id, container=get_container())
        preset = get_room_supply_preset_for_user(request.user, preset_id)
        preset.delete()
        return _json_ok({"preset_id": preset_id, "deleted": True})
    except Exception as exc:
        return _json_error(str(exc))


@login_required(login_url="/auth/")
def overwrite_preset(request: HttpRequest, room_id: str, preset_id: int) -> JsonResponse:
    if request.method != "POST":
        return _json_error("POST required.", status=405)
    try:
        container = get_container()
        room = _require_moderator_lobby_room(request, room_id, container=container)
        preset = get_room_supply_preset_for_user(request.user, preset_id)

        rows = []
        raw_rows = str(request.POST.get("generated_rows", "")).strip()
        if raw_rows:
            rows = _parse_generated_supply_rows(request)
        else:
            payload = build_preset_payload_from_room_items(room.items)
            rows = preset_rows_from_payload(payload)
        if not rows:
            raise ValueError("No central supply items are available to overwrite this preset.")

        preset_rows = _preset_rows_with_saved_images(request, rows, preset=preset, container=container)
        preset.payload = build_preset_payload_from_rows(preset_rows)
        preset.save(update_fields=["payload", "updated_at"])
        return _json_ok({"preset_id": preset.id, "preset_name": preset.name})
    except Exception as exc:
        return _json_error(str(exc))


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
def set_mob_secret_word(request: HttpRequest, room_id: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("rooms-detail", room_id=room_id)
    try:
        dto = SetMobSecretWordRequestDTO.from_payload(
            {
                "room_id": room_id,
                "moderator_user_id": _current_user_id(request),
                "secret_mob_word": request.POST.get("secret_mob_word", ""),
            }
        )
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        rooms_inbound.set_mob_secret_word(dto.to_command())
        messages.success(request, "Secret mob word saved.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_room_detail_with_context(request, room_id=room_id)


@login_required(login_url="/auth/")
def launch_game(request: HttpRequest, room_id: str) -> HttpResponse:
    try:
        dto = LaunchGameFromRoomRequestDTO.from_payload({"room_id": room_id, "requested_by_user_id": _current_user_id(request)})
        container = get_container()
        rooms_inbound = _rooms_inbound_for_launch(request, container=container)
        game_id = rooms_inbound.launch_game_from_room(dto.to_command())
        _set_active_game_session(request, game_id=game_id, room_id=room_id)
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
