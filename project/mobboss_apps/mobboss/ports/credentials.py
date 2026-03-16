"""Credentials outbound port and DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DatabaseCredentialsDTO:
    database_url: str


class CredentialsOutboundPort(Protocol):
    def get_database_credentials(self) -> DatabaseCredentialsDTO:
        ...
