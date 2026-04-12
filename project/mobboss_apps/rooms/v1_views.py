from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.mobboss.devtools import user_dev_mode_enabled
from project.mobboss_apps.mobboss.decorators import problem_details
from project.mobboss_apps.mobboss.exceptions import UnauthorizedProblem
from project.mobboss_apps.rooms.ports.internal_requests_dto import (
    AssignRoomRoleRequestDTO,
    CatalogItemImageRequestDTO,
    CreateRoomRequestDTO,
    DeactivateRoomItemRequestDTO,
    DeleteRoomRequestDTO,
    JoinRoomRequestDTO,
    LaunchGameFromRoomRequestDTO,
    LeaveRoomRequestDTO,
    RoomIdRequestDTO,
    SetMemberBalanceRequestDTO,
    SetMobSecretWordRequestDTO,
    SetRoomReadinessRequestDTO,
    ShuffleRoomRolesRequestDTO,
    UpsertRoomItemRequestDTO,
)


@method_decorator(problem_details, name="dispatch")
class BaseJsonView(View):
    @staticmethod
    def _ok(data: Any, status: int = 200) -> JsonResponse:
        return JsonResponse({"data": data, "error": None}, status=status)

    @staticmethod
    def _require_authenticated_user_id(request: HttpRequest) -> str:
        if not request.user.is_authenticated:
            raise UnauthorizedProblem()
        return str(request.user.id or request.user.username)

    @staticmethod
    def _load_json_body(request: HttpRequest) -> dict:
        if not request.body:
            return {}
        try:
            return json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON payload.") from exc


class RoomsCollectionView(BaseJsonView):
    def get(self, request: HttpRequest) -> JsonResponse:
        self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        rooms = rooms_inbound.list_active_rooms()
        return self._ok([_room_summary_to_dict(room) for room in rooms])

    def post(self, request: HttpRequest) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        payload = self._load_json_body(request)
        payload["creator_user_id"] = user_id
        payload["creator_username"] = request.user.username
        dto = CreateRoomRequestDTO.from_payload(payload)
        command = dto.to_command()
        room = rooms_inbound.create_room(command)
        return self._ok(_room_summary_to_dict(room), status=201)


class RoomDetailView(BaseJsonView):
    def get(self, request: HttpRequest, room_id: str) -> JsonResponse:
        self._require_authenticated_user_id(request)
        dto = RoomIdRequestDTO.from_payload({"room_id": room_id})
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        room = rooms_inbound.get_room_details(dto.room_id)
        return self._ok(_room_details_to_dict(room))


class JoinRoomView(BaseJsonView):
    def post(self, request: HttpRequest, room_id: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        payload = self._load_json_body(request)
        payload["room_id"] = room_id
        payload["user_id"] = user_id
        payload["username"] = request.user.username
        dto = JoinRoomRequestDTO.from_payload(payload)
        command = dto.to_command()
        room = rooms_inbound.join_room(command)
        return self._ok(_room_details_to_dict(room))


class LeaveRoomView(BaseJsonView):
    def post(self, request: HttpRequest, room_id: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        payload = self._load_json_body(request)
        payload["room_id"] = room_id
        payload["user_id"] = user_id
        dto = LeaveRoomRequestDTO.from_payload(payload)
        command = dto.to_command()
        room = rooms_inbound.leave_room(command)
        return self._ok(_room_details_to_dict(room))


class ReadinessView(BaseJsonView):
    def post(self, request: HttpRequest, room_id: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        payload = self._load_json_body(request)
        payload["room_id"] = room_id
        payload["requested_by_user_id"] = user_id
        payload.setdefault("user_id", user_id)
        dto = SetRoomReadinessRequestDTO.from_payload(payload)
        command = dto.to_command()
        room = rooms_inbound.set_room_readiness(command)
        return self._ok(_room_details_to_dict(room))


class AssignRoleView(BaseJsonView):
    def post(self, request: HttpRequest, room_id: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        if not user_dev_mode_enabled(user=request.user, room_dev_mode=container.room_dev_mode):
            raise ValueError("Role assignment is only available in dev mode.")
        rooms_inbound = container.rooms_inbound_port
        payload = self._load_json_body(request)
        payload["room_id"] = room_id
        payload["moderator_user_id"] = user_id
        dto = AssignRoomRoleRequestDTO.from_payload(payload)
        command = dto.to_command()
        room = rooms_inbound.assign_room_role(command)
        return self._ok(_room_details_to_dict(room))


class BalanceView(BaseJsonView):
    def post(self, request: HttpRequest, room_id: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        payload = self._load_json_body(request)
        payload["room_id"] = room_id
        payload["moderator_user_id"] = user_id
        dto = SetMemberBalanceRequestDTO.from_payload(payload)
        command = dto.to_command()
        room = rooms_inbound.set_member_balance(command)
        return self._ok(_room_details_to_dict(room))


class CatalogCollectionView(BaseJsonView):
    def get(self, request: HttpRequest, room_id: str) -> JsonResponse:
        self._require_authenticated_user_id(request)
        dto = RoomIdRequestDTO.from_payload({"room_id": room_id})
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        room = rooms_inbound.get_room_details(dto.room_id)
        return self._ok([_item_to_dict(item) for item in room.items])


class CatalogItemUpsertView(BaseJsonView):
    def put(self, request: HttpRequest, room_id: str, classification: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        payload = self._load_json_body(request)
        payload["room_id"] = room_id
        payload["moderator_user_id"] = user_id
        payload["classification"] = classification
        dto = UpsertRoomItemRequestDTO.from_payload(payload)
        command = dto.to_command()
        room = rooms_inbound.upsert_room_item(command)
        return self._ok(_room_details_to_dict(room))


class CatalogItemImageView(BaseJsonView):
    def post(self, request: HttpRequest, room_id: str, classification: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        room_item_media_outbound = container.room_item_media_outbound_port
        if "image" in request.FILES:
            upload = request.FILES["image"]
            image_path = room_item_media_outbound.save_room_item_image(
                room_id=room_id,
                classification=classification,
                original_filename=upload.name,
                chunks=upload.chunks(),
            )
        else:
            payload = self._load_json_body(request)
            image_path = str(payload.get("image_path", "")).strip()

        dto = CatalogItemImageRequestDTO.from_payload(
            {
                "room_id": room_id,
                "moderator_user_id": user_id,
                "classification": classification,
                "image_path": image_path,
            }
        )

        room = rooms_inbound.get_room_details(dto.room_id)
        existing = next((item for item in room.items if item.classification == dto.classification), None)
        if existing is None:
            raise ValueError("Cannot set image for missing catalog item. Create item first.")

        request_dto = dto.to_upsert_item_request(display_name=existing.display_name, base_price=existing.base_price)
        command = request_dto.to_command()
        updated = rooms_inbound.upsert_room_item(command)
        return self._ok(_room_details_to_dict(updated))


class CatalogItemDeactivateView(BaseJsonView):
    def post(self, request: HttpRequest, room_id: str, classification: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        dto = DeactivateRoomItemRequestDTO.from_payload(
            {"room_id": room_id, "moderator_user_id": user_id, "classification": classification}
        )
        command = dto.to_command()
        room = rooms_inbound.deactivate_room_item(command)
        return self._ok(_room_details_to_dict(room))


class SecretMobWordView(BaseJsonView):
    def post(self, request: HttpRequest, room_id: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        payload = self._load_json_body(request)
        payload["room_id"] = room_id
        payload["moderator_user_id"] = user_id
        dto = SetMobSecretWordRequestDTO.from_payload(payload)
        command = dto.to_command()
        room = rooms_inbound.set_mob_secret_word(command)
        return self._ok(_room_details_to_dict(room))


class LaunchGameView(BaseJsonView):
    def post(self, request: HttpRequest, room_id: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        dto = LaunchGameFromRoomRequestDTO.from_payload({"room_id": room_id, "requested_by_user_id": user_id})
        command = dto.to_command()
        game_id = rooms_inbound.launch_game_from_room(command)
        return self._ok({"game_id": game_id})


class DeleteRoomView(BaseJsonView):
    def post(self, request: HttpRequest, room_id: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        dto = DeleteRoomRequestDTO.from_payload({"room_id": room_id, "requested_by_user_id": user_id})
        command = dto.to_command()
        rooms_inbound.delete_room(command)
        return self._ok({"room_id": room_id, "deleted": True})


class ShuffleRolesView(BaseJsonView):
    def post(self, request: HttpRequest, room_id: str) -> JsonResponse:
        user_id = self._require_authenticated_user_id(request)
        container = get_container()
        rooms_inbound = container.rooms_inbound_port
        payload = self._load_json_body(request)
        payload["room_id"] = room_id
        payload["moderator_user_id"] = user_id
        dto = ShuffleRoomRolesRequestDTO.from_payload(payload)
        command = dto.to_command()
        room = rooms_inbound.shuffle_room_roles(command)
        return self._ok(_room_details_to_dict(room))


def _room_summary_to_dict(room) -> dict:
    return {
        "room_id": room.room_id,
        "name": room.name,
        "status": room.status,
        "moderator_user_id": room.moderator_user_id,
        "member_count": room.member_count,
    }


def _room_details_to_dict(room) -> dict:
    return {
        "room_id": room.room_id,
        "name": room.name,
        "status": room.status,
        "moderator_user_id": room.moderator_user_id,
        "members": [
            {
                "user_id": member.user_id,
                "username": member.username,
                "membership_status": member.membership_status,
                "is_ready": member.is_ready,
                "starting_balance": member.starting_balance,
                "assigned_role": (
                    {
                        "faction": member.assigned_role.faction,
                        "role_name": member.assigned_role.role_name,
                        "rank": member.assigned_role.rank,
                    }
                    if member.assigned_role
                    else None
                ),
            }
            for member in room.members
        ],
        "items": [_item_to_dict(item) for item in room.items],
    }


def _item_to_dict(item) -> dict:
    return {
        "classification": item.classification,
        "display_name": item.display_name,
        "base_price": item.base_price,
        "image_path": item.image_path,
        "is_active": item.is_active,
    }
