"""Backward-compatible accessors for room service composition."""

from __future__ import annotations

from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.rooms.ports.inbound import RoomsInboundPort


def get_rooms_service() -> RoomsInboundPort:
    """Legacy alias kept for modules that still import this helper."""
    container = get_container()
    return container.rooms_inbound_port

