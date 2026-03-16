"""Request DTOs used by web inbound adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class LobbyIndexRequestDTO:
    method: str
    user_id: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LobbyIndexRequestDTO":
        method = _parse_method(payload.get("method"), key="method")
        user_id = str(payload.get("user_id", "")).strip()
        if not user_id:
            raise ValueError("Field 'user_id' must be non-empty.")
        return cls(method=method, user_id=user_id)


@dataclass(frozen=True)
class StatusIndexRequestDTO:
    method: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "StatusIndexRequestDTO":
        return cls(method=_parse_method(payload.get("method"), key="method"))


def _parse_method(raw: Any, *, key: str) -> str:
    value = str(raw if raw is not None else "").strip().upper()
    if value not in _ALLOWED_HTTP_METHODS:
        raise ValueError(f"Field '{key}' has unsupported HTTP method: {value!r}")
    return value
