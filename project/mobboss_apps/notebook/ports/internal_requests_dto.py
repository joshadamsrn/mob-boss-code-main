"""Request DTOs used by notebook inbound adapters."""

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


def _parse_method(raw: Any, *, key: str) -> str:
    value = str(raw if raw is not None else "").strip().upper()
    if value not in _ALLOWED_HTTP_METHODS:
        raise ValueError(f"Field '{key}' has unsupported HTTP method: {value!r}")
    return value
