from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from project.mobboss_apps.gameplay.adapters.internal.page_view_mapper import (
    build_gameplay_page_view,
)
from project.mobboss_apps.gameplay.ports.internal import (
    AdvanceAccusedSelectionTimeoutCommand,
    ReportDeathCommand,
)
from project.mobboss_apps.gameplay.ports.internal_requests_dto import (
    AdvanceAccusedSelectionTimeoutRequestDTO,
    GameIdRequestDTO,
    IndexRequestDTO,
    ReportDeathRequestDTO,
)
from project.mobboss_apps.mobboss.composition import get_container


def _current_user_id(request: HttpRequest) -> str:
    return str(request.user.id or request.user.username)


def _game_plan_steps() -> list[dict[str, str]]:
    return [
        {
            "phase": "information",
            "label": "Information",
            "description": "Players gather intel and prepare actions.",
        },
        {
            "phase": "accused_selection",
            "label": "Accused Selection",
            "description": "Police chain responds to identify accused player.",
        },
        {
            "phase": "trial_voting",
            "label": "Trial Voting",
            "description": "Selected jury votes to convict or acquit.",
        },
        {
            "phase": "boundary_resolution",
            "label": "Boundary Resolution",
            "description": "Apply outcomes and evaluate boundary win checks.",
        },
        {
            "phase": "ended",
            "label": "Ended",
            "description": "Game session is complete.",
        },
    ]


@login_required(login_url="/auth/")
def index(request: HttpRequest) -> HttpResponse:
    IndexRequestDTO.from_payload({"method": request.method})
    return redirect("web-lobby")


@login_required(login_url="/auth/")
def detail(request: HttpRequest, game_id: str) -> HttpResponse:
    try:
        dto = GameIdRequestDTO.from_payload({"method": request.method, "game_id": game_id})
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(dto.game_id)
        viewer_user_id = _current_user_id(request)
        page = build_gameplay_page_view(session, viewer_user_id)
        return render(
            request,
            "gameplay/detail.html",
            {
                "page": page,
                "game_plan_steps": _game_plan_steps(),
                "game_state_poll_interval_seconds": container.room_state_poll_interval_seconds,
            },
        )
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect("web-lobby")


@login_required(login_url="/auth/")
def report_death(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("gameplay-detail", game_id=game_id)
    try:
        dto = ReportDeathRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "murdered_user_id": request.POST.get("murdered_user_id", ""),
                "reported_by_user_id": _current_user_id(request),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        gameplay_inbound.report_death(
            ReportDeathCommand(
                game_id=dto.game_id,
                murdered_user_id=dto.murdered_user_id,
                reported_by_user_id=dto.reported_by_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Death reported.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("gameplay-detail", game_id=game_id)


@login_required(login_url="/auth/")
def advance_accused_selection_timeout(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return redirect("gameplay-detail", game_id=game_id)
    try:
        dto = AdvanceAccusedSelectionTimeoutRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "requested_by_user_id": _current_user_id(request),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        gameplay_inbound.advance_accused_selection_timeout(
            AdvanceAccusedSelectionTimeoutCommand(
                game_id=dto.game_id,
                requested_by_user_id=dto.requested_by_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Accused-selection timeout advanced.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("gameplay-detail", game_id=game_id)


