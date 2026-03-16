from django.http import HttpRequest, HttpResponse

from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.operations.ports.internal_requests_dto import (
    HealthcheckRequestDTO,
    MetricsRequestDTO,
    OperationsIndexRequestDTO,
)


def index(request: HttpRequest) -> HttpResponse:
    OperationsIndexRequestDTO.from_payload({"method": request.method})
    _container = get_container()
    return HttpResponse("operations")


def healthcheck(request: HttpRequest) -> HttpResponse:
    HealthcheckRequestDTO.from_payload({"method": request.method})
    _container = get_container()
    return HttpResponse("ok")


def metrics(request: HttpRequest) -> HttpResponse:
    MetricsRequestDTO.from_payload({"method": request.method})
    _container = get_container()
    return HttpResponse("# metrics placeholder\n", content_type="text/plain; version=0.0.4")


