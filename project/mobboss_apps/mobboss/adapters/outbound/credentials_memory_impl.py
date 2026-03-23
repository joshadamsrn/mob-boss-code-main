"""In-memory credentials outbound adapter."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from project.mobboss_apps.mobboss.ports.credentials import CredentialsOutboundPort, DatabaseCredentialsDTO


class MemoryCredentialsOutboundPortImpl(CredentialsOutboundPort):
    def __init__(self, *, database_credentials: DatabaseCredentialsDTO) -> None:
        self._database_credentials = database_credentials

    @classmethod
    def build_default(cls) -> "MemoryCredentialsOutboundPortImpl":
        repo_root = Path(__file__).resolve().parents[5]
        database_name = "mobboss.sqlite3"
        try:
            if settings.configured:
                database = settings.DATABASES.get("default")
                if isinstance(database, dict):
                    database_name = str(database.get("NAME", database_name))
        except ImproperlyConfigured:
            pass
        database_path = Path(database_name)
        if not database_path.is_absolute():
            database_path = repo_root / database_path.name
        database_url = f"sqlite:///{database_path}"
        return cls(database_credentials=DatabaseCredentialsDTO(database_url=database_url))

    @classmethod
    def build_unittest(cls) -> "MemoryCredentialsOutboundPortImpl":
        return cls(database_credentials=DatabaseCredentialsDTO(database_url="sqlite://:memory:"))

    def get_database_credentials(self) -> DatabaseCredentialsDTO:
        return self._database_credentials
