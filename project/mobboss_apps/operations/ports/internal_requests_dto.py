"""Request DTOs used by operations inbound adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class OperationsIndexRequestDTO:
    method: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OperationsIndexRequestDTO":
        return cls(method=_parse_method(payload.get("method"), key="method"))


@dataclass(frozen=True)
class HealthcheckRequestDTO:
    method: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "HealthcheckRequestDTO":
        return cls(method=_parse_method(payload.get("method"), key="method"))


@dataclass(frozen=True)
class MetricsRequestDTO:
    method: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MetricsRequestDTO":
        return cls(method=_parse_method(payload.get("method"), key="method"))


@dataclass(frozen=True)
class OperationsStatusIndexRequestDTO:
    method: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OperationsStatusIndexRequestDTO":
        return cls(method=_parse_method(payload.get("method"), key="method"))


def _parse_method(raw: Any, *, key: str) -> str:
    value = str(raw if raw is not None else "").strip().upper()
    if value not in _ALLOWED_HTTP_METHODS:
        raise ValueError(f"Field '{key}' has unsupported HTTP method: {value!r}")
    return value
