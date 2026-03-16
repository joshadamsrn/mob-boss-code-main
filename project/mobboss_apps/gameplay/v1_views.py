from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from project.mobboss_apps.gameplay.ports.internal import (
    AdvanceAccusedSelectionTimeoutCommand,
    ReportDeathCommand,
)
from project.mobboss_apps.gameplay.ports.internal_requests_dto import (
    AdvanceAccusedSelectionTimeoutRequestDTO,
    GameIdRequestDTO,
    ReportDeathRequestDTO,
    StatusIndexRequestDTO,
)
from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.mobboss.decorators import problem_details
from project.mobboss_apps.mobboss.exceptions import UnauthorizedProblem


@problem_details
def index(request: HttpRequest) -> JsonResponse:
    StatusIndexRequestDTO.from_payload({"method": request.method})
    _container = get_container()
    return JsonResponse({"status": "ok"})


def _to_participant_dict(participant, *, include_role_details: bool) -> dict:
    data = {
        "user_id": participant.user_id,
        "username": participant.username,
        "life_state": participant.life_state,
    }
    if include_role_details:
        data["faction"] = participant.faction
        data["role_name"] = participant.role_name
        data["rank"] = participant.rank
    return data


def _to_game_view_dict(snapshot, *, viewer_user_id: str, is_moderator: bool) -> dict:
    # Invariant: role leakage is prevented at projection time. Non-moderator viewers
    # only receive role/faction/rank fields for self.
    participants: list[dict] = []
    for participant in snapshot.participants:
        include_role_details = is_moderator or participant.user_id == viewer_user_id
        participants.append(_to_participant_dict(participant, include_role_details=include_role_details))

    payload = {
        "game_id": snapshot.game_id,
        "room_id": snapshot.room_id,
        "status": snapshot.status,
        "phase": snapshot.phase,
        "round_number": snapshot.round_number,
        "version": snapshot.version,
        "launched_at_epoch_seconds": snapshot.launched_at_epoch_seconds,
        "ended_at_epoch_seconds": snapshot.ended_at_epoch_seconds,
        "participants": participants,
    }
    if is_moderator and snapshot.pending_trial is not None:
        payload["pending_trial"] = {
            "murdered_user_id": snapshot.pending_trial.murdered_user_id,
            "murderer_user_id": snapshot.pending_trial.murderer_user_id,
            "accused_user_id": snapshot.pending_trial.accused_user_id,
            "accused_selection_cursor": list(snapshot.pending_trial.accused_selection_cursor),
            "accused_selection_deadline_epoch_seconds": snapshot.pending_trial.accused_selection_deadline_epoch_seconds,
            "jury_user_ids": list(snapshot.pending_trial.jury_user_ids),
            "vote_deadline_epoch_seconds": snapshot.pending_trial.vote_deadline_epoch_seconds,
            "votes": list(snapshot.pending_trial.votes),
            "verdict": snapshot.pending_trial.verdict,
            "conviction_correct": snapshot.pending_trial.conviction_correct,
            "resolution": snapshot.pending_trial.resolution,
        }
    return payload


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


class GameDetailView(BaseJsonView):
    def get(self, request: HttpRequest, game_id: str) -> JsonResponse:
        viewer_user_id = self._require_authenticated_user_id(request)
        dto = GameIdRequestDTO.from_payload({"method": request.method, "game_id": game_id})
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        snapshot = gameplay_inbound.get_game_details(dto.game_id)

        is_moderator = snapshot.moderator_user_id == viewer_user_id
        is_participant = any(participant.user_id == viewer_user_id for participant in snapshot.participants)
        if not is_moderator and not is_participant:
            raise PermissionError("Only moderator or joined participants can view this game.")

        return self._ok(_to_game_view_dict(snapshot, viewer_user_id=viewer_user_id, is_moderator=is_moderator))


class ReportDeathView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        reporter_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["reported_by_user_id"] = reporter_user_id
        dto = ReportDeathRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        snapshot = gameplay_inbound.get_game_details(dto.game_id)
        if snapshot.moderator_user_id != reporter_user_id:
            raise PermissionError("Only moderator can report deaths.")

        updated = gameplay_inbound.report_death(
            ReportDeathCommand(
                game_id=dto.game_id,
                murdered_user_id=dto.murdered_user_id,
                reported_by_user_id=dto.reported_by_user_id,
                expected_version=dto.expected_version,
            )
        )
        return self._ok(_to_game_view_dict(updated, viewer_user_id=reporter_user_id, is_moderator=True))


class AdvanceAccusedSelectionTimeoutView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        requester_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["requested_by_user_id"] = requester_user_id
        dto = AdvanceAccusedSelectionTimeoutRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.advance_accused_selection_timeout(
            AdvanceAccusedSelectionTimeoutCommand(
                game_id=dto.game_id,
                requested_by_user_id=dto.requested_by_user_id,
                expected_version=dto.expected_version,
            )
        )
        return self._ok(_to_game_view_dict(updated, viewer_user_id=requester_user_id, is_moderator=True))


