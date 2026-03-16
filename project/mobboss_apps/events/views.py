from django.http import HttpRequest, HttpResponse

from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.events.ports.internal_requests_dto import IndexRequestDTO


def index(request: HttpRequest) -> HttpResponse:
    IndexRequestDTO.from_payload({"method": request.method})
    _container = get_container()
    return HttpResponse("ok")


