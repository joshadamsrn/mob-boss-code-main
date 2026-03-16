"""Django auth outbound adapter implementation."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from django.http import HttpRequest

from project.mobboss_apps.iam.ports.outbound import IamOutboundPort

if TYPE_CHECKING:
    from django.contrib.auth.forms import AuthenticationForm, UserCreationForm


class DjangoIamOutboundPortImpl(IamOutboundPort):
    def build_login_form(self, request: HttpRequest, data: dict[str, str] | None = None) -> AuthenticationForm:
        from django.contrib.auth.forms import AuthenticationForm

        return AuthenticationForm(request=request, data=data)

    def build_signup_form(self, data: dict[str, str] | None = None) -> UserCreationForm:
        from django.contrib.auth.forms import UserCreationForm

        return UserCreationForm(data)

    def login(self, request: HttpRequest, user: Any) -> None:
        from django.contrib.auth import login as django_login

        django_login(request, user)

    def logout(self, request: HttpRequest) -> None:
        from django.contrib.auth import logout as django_logout

        django_logout(request)

