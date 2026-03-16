"""Request DTOs used by iam inbound adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Literal

AuthMethod = Literal["GET", "POST", "OTHER"]
AuthAction = Literal["", "login", "signup"]


@dataclass(frozen=True)
class AuthIndexRequestDTO:
    method: AuthMethod
    action: AuthAction

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AuthIndexRequestDTO":
        raw_method = str(payload.get("method", "")).upper()
        method: AuthMethod
        if raw_method in {"GET", "POST"}:
            method = raw_method  # type: ignore[assignment]
        else:
            method = "OTHER"

        raw_action = str(payload.get("action", "")).strip()
        action: AuthAction
        if raw_action in {"login", "signup"}:
            action = raw_action  # type: ignore[assignment]
        else:
            action = ""

        return cls(method=method, action=action)


@dataclass(frozen=True)
class LoginRequestDTO:
    username: str
    password: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LoginRequestDTO":
        return cls(
            username=str(payload.get("username", "")).strip(),
            password=str(payload.get("password", "")),
        )

    def to_form_data(self) -> dict[str, str]:
        return {"username": self.username, "password": self.password}


@dataclass(frozen=True)
class SignupRequestDTO:
    username: str
    password1: str
    password2: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SignupRequestDTO":
        return cls(
            username=str(payload.get("username", "")).strip(),
            password1=str(payload.get("password1", "")),
            password2=str(payload.get("password2", "")),
        )

    def to_form_data(self) -> dict[str, str]:
        return {"username": self.username, "password1": self.password1, "password2": self.password2}


@dataclass(frozen=True)
class LogoutRequestDTO:
    method: AuthMethod

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LogoutRequestDTO":
        raw_method = str(payload.get("method", "")).upper()
        if raw_method in {"GET", "POST"}:
            return cls(method=raw_method)  # type: ignore[arg-type]
        return cls(method="OTHER")


@dataclass(frozen=True)
class StatusIndexRequestDTO:
    method: AuthMethod

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "StatusIndexRequestDTO":
        raw_method = str(payload.get("method", "")).upper()
        if raw_method in {"GET", "POST"}:
            return cls(method=raw_method)  # type: ignore[arg-type]
        return cls(method="OTHER")
