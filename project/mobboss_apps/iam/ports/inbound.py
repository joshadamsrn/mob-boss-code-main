"""Inbound ports: system stimulation contracts."""

from __future__ import annotations

from typing import Protocol

from django.http import HttpRequest

from project.mobboss_apps.iam.ports.internal import IamAuthPageResult, IamLogoutResult
from project.mobboss_apps.iam.ports.internal_requests_dto import (
    AuthIndexRequestDTO,
    LoginRequestDTO,
    LogoutRequestDTO,
    SignupRequestDTO,
)


class IamInboundPort(Protocol):
    def handle_auth_page(
        self,
        *,
        request: HttpRequest,
        request_dto: AuthIndexRequestDTO,
        login_dto: LoginRequestDTO,
        signup_dto: SignupRequestDTO,
    ) -> IamAuthPageResult:
        ...

    def handle_logout(self, *, request: HttpRequest, request_dto: LogoutRequestDTO) -> IamLogoutResult:
        ...

