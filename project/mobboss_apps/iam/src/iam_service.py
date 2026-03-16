"""IAM use-case service."""

from __future__ import annotations

from django.http import HttpRequest

from project.mobboss_apps.iam.ports.inbound import IamInboundPort
from project.mobboss_apps.iam.ports.internal import IamAuthPageResult, IamLogoutResult
from project.mobboss_apps.iam.ports.internal_requests_dto import (
    AuthIndexRequestDTO,
    LoginRequestDTO,
    LogoutRequestDTO,
    SignupRequestDTO,
)
from project.mobboss_apps.iam.ports.outbound import IamOutboundPort


class IamService(IamInboundPort):
    def __init__(self, auth_gateway: IamOutboundPort) -> None:
        self._auth_gateway = auth_gateway

    def handle_auth_page(
        self,
        *,
        request: HttpRequest,
        request_dto: AuthIndexRequestDTO,
        login_dto: LoginRequestDTO,
        signup_dto: SignupRequestDTO,
    ) -> IamAuthPageResult:
        if request.user.is_authenticated:
            return IamAuthPageResult(login_form=None, signup_form=None, redirect_to="web-lobby")

        login_form = self._auth_gateway.build_login_form(request=request)
        signup_form = self._auth_gateway.build_signup_form()

        if request_dto.method == "POST":
            if request_dto.action == "login":
                login_form = self._auth_gateway.build_login_form(request=request, data=login_dto.to_form_data())
                if login_form.is_valid():
                    self._auth_gateway.login(request, login_form.get_user())
                    return IamAuthPageResult(login_form=login_form, signup_form=signup_form, redirect_to="web-lobby")
            elif request_dto.action == "signup":
                signup_form = self._auth_gateway.build_signup_form(data=signup_dto.to_form_data())
                if signup_form.is_valid():
                    user = signup_form.save()
                    self._auth_gateway.login(request, user)
                    return IamAuthPageResult(login_form=login_form, signup_form=signup_form, redirect_to="web-lobby")

        self._style_form_controls(login_form)
        self._style_form_controls(signup_form)
        return IamAuthPageResult(login_form=login_form, signup_form=signup_form)

    def handle_logout(self, *, request: HttpRequest, request_dto: LogoutRequestDTO) -> IamLogoutResult:
        if request_dto.method == "POST":
            self._auth_gateway.logout(request)
            return IamLogoutResult(redirect_to="iam-auth")
        return IamLogoutResult(redirect_to="web-lobby")

    @staticmethod
    def _style_form_controls(form) -> None:
        for field in form.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} form-control".strip()

