from django.http import HttpRequest, HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

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

