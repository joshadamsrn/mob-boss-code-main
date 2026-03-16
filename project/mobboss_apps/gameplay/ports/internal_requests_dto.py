"""Request DTOs used by gameplay inbound adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class IndexRequestDTO:
    method: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "IndexRequestDTO":
        return cls(method=_parse_method(payload.get("method"), key="method"))


@dataclass(frozen=True)
class StatusIndexRequestDTO:
    method: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "StatusIndexRequestDTO":
        return cls(method=_parse_method(payload.get("method"), key="method"))


@dataclass(frozen=True)
class GameIdRequestDTO:
    method: str
    game_id: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "GameIdRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
        )


@dataclass(frozen=True)
class ReportDeathRequestDTO:
    method: str
    game_id: str
    murdered_user_id: str
    reported_by_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReportDeathRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            murdered_user_id=_require_non_empty(payload, "murdered_user_id"),
            reported_by_user_id=_require_non_empty(payload, "reported_by_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class AdvanceAccusedSelectionTimeoutRequestDTO:
    method: str
    game_id: str
    requested_by_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AdvanceAccusedSelectionTimeoutRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            requested_by_user_id=_require_non_empty(payload, "requested_by_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


def _require_non_empty(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"Field '{key}' must be non-empty.")
    return value


def _parse_int(raw: Any, *, key: str) -> int:
    if raw is None:
        raise ValueError(f"Field '{key}' must be an integer.")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field '{key}' must be an integer.") from exc


def _parse_method(raw: Any, *, key: str) -> str:
    value = str(raw if raw is not None else "").strip().upper()
    if value not in _ALLOWED_HTTP_METHODS:
        raise ValueError(f"Field '{key}' has unsupported HTTP method: {value!r}")
    return value
