from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.iam.ports.internal_requests_dto import (
    AuthIndexRequestDTO,
    LoginRequestDTO,
    LogoutRequestDTO,
    SignupRequestDTO,
)


def index(request: HttpRequest) -> HttpResponse:
    container = get_container()
    iam_inbound = container.iam_inbound_port

    request_dto = AuthIndexRequestDTO.from_payload({"method": request.method, "action": request.POST.get("action", "")})
    login_dto = LoginRequestDTO.from_payload(
        {
            "username": request.POST.get("username", ""),
            "password": request.POST.get("password", ""),
        }
    )
    signup_dto = SignupRequestDTO.from_payload(
        {
            "username": request.POST.get("username", ""),
            "password1": request.POST.get("password1", ""),
            "password2": request.POST.get("password2", ""),
        }
    )
    result = iam_inbound.handle_auth_page(
        request=request,
        request_dto=request_dto,
        login_dto=login_dto,
        signup_dto=signup_dto,
    )
    if result.redirect_to is not None:
        return redirect(result.redirect_to)

    return render(
        request,
        "iam/auth.html",
        {
            "login_form": result.login_form,
            "signup_form": result.signup_form,
        },
    )


def logout_view(request: HttpRequest) -> HttpResponse:
    container = get_container()
    iam_inbound = container.iam_inbound_port
    dto = LogoutRequestDTO.from_payload({"method": request.method})
    result = iam_inbound.handle_logout(request=request, request_dto=dto)
    return redirect(result.redirect_to)

