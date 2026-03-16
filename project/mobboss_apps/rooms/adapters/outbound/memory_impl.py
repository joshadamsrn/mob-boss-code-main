"""In-memory room repository adapter implementation."""

from project.mobboss_apps.rooms.adapters.outbound.memory_repository import MemoryRoomsRepository


class MemoryRoomsOutboundPortImpl(MemoryRoomsRepository):
    """Backward-compatible impl alias with *_impl naming."""

