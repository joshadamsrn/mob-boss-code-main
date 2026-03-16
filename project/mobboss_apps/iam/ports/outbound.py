"""Outbound ports: external resource contracts."""

from __future__ import annotations

from typing import Any, Protocol

from django.http import HttpRequest


class IamOutboundPort(Protocol):
    def build_login_form(self, request: HttpRequest, data: dict[str, str] | None = None) -> Any:
        ...

    def build_signup_form(self, data: dict[str, str] | None = None) -> Any:
        ...

    def login(self, request: HttpRequest, user: Any) -> None:
        ...

    def logout(self, request: HttpRequest) -> None:
        ...
