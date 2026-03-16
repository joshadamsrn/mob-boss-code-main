"""In-memory project setting outbound adapter."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from project.mobboss_apps.mobboss.ports.projectsetting import MediaProjectSettingsDTO, ProjectSettingOutboundPort, RoomProjectSettingsDTO


class MemoryProjectSettingOutboundPortImpl(ProjectSettingOutboundPort):
    DEFAULT_MINIMUM_LAUNCH_PLAYERS = 7
    DEFAULT_STATE_POLL_INTERVAL_SECONDS = 5
    DEFAULT_AUTO_SHUFFLE_INTERVAL_SECONDS = 60

    def __init__(
        self,
        *,
        room_project_settings: RoomProjectSettingsDTO,
        media_project_settings: MediaProjectSettingsDTO,
    ) -> None:
        self._room_project_settings = room_project_settings
        self._media_project_settings = media_project_settings

    @classmethod
    def build_default(cls) -> "MemoryProjectSettingOutboundPortImpl":
        room_dev_mode = False
        room_min_launch_players = cls.DEFAULT_MINIMUM_LAUNCH_PLAYERS
        room_state_poll_interval_seconds = cls.DEFAULT_STATE_POLL_INTERVAL_SECONDS
        room_auto_shuffle_interval_seconds = cls.DEFAULT_AUTO_SHUFFLE_INTERVAL_SECONDS
        media_root: Path | None = Path.cwd() / "media"
        media_url = "/media/"

        try:
            if settings.configured:
                debug_raw = getattr(settings, "DEBUG", False)
                if isinstance(debug_raw, bool):
                    debug_value = debug_raw
                else:
                    debug_value = str(debug_raw).strip().lower() in {"1", "true", "yes", "on"}

                room_dev_raw = getattr(settings, "ROOM_DEV_MODE", debug_value)
                if isinstance(room_dev_raw, bool):
                    room_dev_mode = room_dev_raw
                else:
                    room_dev_mode = str(room_dev_raw).strip().lower() in {"1", "true", "yes", "on"}

                room_min_raw = getattr(settings, "ROOM_MIN_LAUNCH_PLAYERS", room_min_launch_players)
                try:
                    room_min_launch_players = int(room_min_raw)
                except (TypeError, ValueError):
                    room_min_launch_players = cls.DEFAULT_MINIMUM_LAUNCH_PLAYERS

                room_state_poll_raw = getattr(
                    settings,
                    "ROOM_STATE_POLL_INTERVAL_SECONDS",
                    room_state_poll_interval_seconds,
                )
                try:
                    room_state_poll_interval_seconds = int(room_state_poll_raw)
                except (TypeError, ValueError):
                    room_state_poll_interval_seconds = cls.DEFAULT_STATE_POLL_INTERVAL_SECONDS

                room_auto_shuffle_raw = getattr(
                    settings,
                    "ROOM_AUTO_SHUFFLE_INTERVAL_SECONDS",
                    room_auto_shuffle_interval_seconds,
                )
                try:
                    room_auto_shuffle_interval_seconds = int(room_auto_shuffle_raw)
                except (TypeError, ValueError):
                    room_auto_shuffle_interval_seconds = cls.DEFAULT_AUTO_SHUFFLE_INTERVAL_SECONDS

                base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
                media_root = Path(getattr(settings, "MEDIA_ROOT", base_dir / "media"))
                media_url = str(getattr(settings, "MEDIA_URL", media_url))
        except ImproperlyConfigured:
            pass

        room_min_launch_players = max(1, min(room_min_launch_players, 25))
        if not room_dev_mode and room_min_launch_players < cls.DEFAULT_MINIMUM_LAUNCH_PLAYERS:
            room_min_launch_players = cls.DEFAULT_MINIMUM_LAUNCH_PLAYERS
        room_state_poll_interval_seconds = max(cls.DEFAULT_STATE_POLL_INTERVAL_SECONDS, room_state_poll_interval_seconds)
        room_auto_shuffle_interval_seconds = max(10, room_auto_shuffle_interval_seconds)

        return cls(
            room_project_settings=RoomProjectSettingsDTO(
                minimum_launch_players=room_min_launch_players,
                dev_mode=room_dev_mode,
                state_poll_interval_seconds=room_state_poll_interval_seconds,
                auto_shuffle_interval_seconds=room_auto_shuffle_interval_seconds,
            ),
            media_project_settings=MediaProjectSettingsDTO(media_root=media_root, media_url=media_url),
        )

    @classmethod
    def build_unittest(cls) -> "MemoryProjectSettingOutboundPortImpl":
        return cls(
            room_project_settings=RoomProjectSettingsDTO(
                minimum_launch_players=1,
                dev_mode=True,
                state_poll_interval_seconds=5,
                auto_shuffle_interval_seconds=10,
            ),
            media_project_settings=MediaProjectSettingsDTO(media_root=None, media_url="/media/"),
        )

    def get_room_project_settings(self) -> RoomProjectSettingsDTO:
        return self._room_project_settings

    def get_media_project_settings(self) -> MediaProjectSettingsDTO:
        return self._media_project_settings

