"""Project setting outbound port and DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RoomProjectSettingsDTO:
    minimum_launch_players: int
    dev_mode: bool
    state_poll_interval_seconds: int
    auto_shuffle_interval_seconds: int


@dataclass(frozen=True)
class MediaProjectSettingsDTO:
    media_root: Path | None
    media_url: str


class ProjectSettingOutboundPort(Protocol):
    def get_room_project_settings(self) -> RoomProjectSettingsDTO:
        ...

    def get_media_project_settings(self) -> MediaProjectSettingsDTO:
        ...
