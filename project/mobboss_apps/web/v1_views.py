from django.http import HttpRequest, JsonResponse

from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.mobboss.decorators import problem_details
from project.mobboss_apps.web.ports.internal_requests_dto import StatusIndexRequestDTO


@problem_details
def index(request: HttpRequest) -> JsonResponse:
    StatusIndexRequestDTO.from_payload({"method": request.method})
    _container = get_container()
    return JsonResponse({"status": "ok"})


