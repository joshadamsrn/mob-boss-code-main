"""SQLite gameplay repository adapter implementation."""

from project.mobboss_apps.gameplay.adapters.outbound.sqlite_repository import (
    SqliteGameplayRepository,
)


class SqliteGameplayOutboundPortImpl(SqliteGameplayRepository):
    """Backward-compatible impl alias with *_impl naming."""

