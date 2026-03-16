"""SQLite room repository adapter implementation."""

from project.mobboss_apps.rooms.adapters.outbound.sqlite_repository import SqliteRoomsRepository


class SqliteRoomsOutboundPortImpl(SqliteRoomsRepository):
    """Backward-compatible impl alias with *_impl naming."""

