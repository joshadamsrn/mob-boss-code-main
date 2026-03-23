"""Dependency composition root for the mobboss app."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from project.mobboss_apps.economy.adapters.outbound.catalog_defaults_json_file_impl import (
    JsonFileEconomyCatalogDefaultsOutboundPortImpl,
)
from project.mobboss_apps.economy.adapters.outbound.catalog_defaults_memory_impl import (
    MemoryEconomyCatalogDefaultsOutboundPortImpl,
)
from project.mobboss_apps.economy.ports.outbound import EconomyCatalogDefaultsOutboundPort
from project.mobboss_apps.gameplay.adapters.outbound.memory_impl import (
    MemoryGameplayOutboundPortImpl,
)
from project.mobboss_apps.gameplay.adapters.outbound.room_lifecycle_impl import (
    RoomsLifecycleSyncOutboundPortImpl,
)
from project.mobboss_apps.gameplay.adapters.outbound.sqlite_impl import (
    SqliteGameplayOutboundPortImpl,
)
from project.mobboss_apps.gameplay.ports.inbound import GameplayInboundPort
from project.mobboss_apps.gameplay.ports.outbound import GameplayOutboundPort
from project.mobboss_apps.gameplay.src.game_service import GameplayService
from project.mobboss_apps.iam.adapters.outbound.django_auth_impl import (
    DjangoIamOutboundPortImpl,
)
from project.mobboss_apps.iam.adapters.outbound.memory_impl import (
    MemoryIamOutboundPortImpl,
)
from project.mobboss_apps.iam.ports.inbound import IamInboundPort
from project.mobboss_apps.iam.ports.outbound import IamOutboundPort
from project.mobboss_apps.iam.src.iam_service import IamService
from project.mobboss_apps.mobboss.adapters.outbound.credentials_memory_impl import (
    MemoryCredentialsOutboundPortImpl,
)
from project.mobboss_apps.mobboss.adapters.outbound.projectsetting_memory_impl import (
    MemoryProjectSettingOutboundPortImpl,
)
from project.mobboss_apps.mobboss.ports.credentials import CredentialsOutboundPort
from project.mobboss_apps.mobboss.ports.projectsetting import ProjectSettingOutboundPort
from project.mobboss_apps.mobboss.src.weights import DEFAULT_WEIGHTS, Weights
from project.mobboss_apps.rooms.adapters.outbound.media.filesystem_impl import (
    FilesystemRoomItemMediaOutboundPortImpl,
)
from project.mobboss_apps.rooms.adapters.outbound.media.memory_impl import (
    MemoryRoomItemMediaOutboundPortImpl,
)
from project.mobboss_apps.rooms.adapters.outbound.memory_impl import (
    MemoryRoomsOutboundPortImpl,
)
from project.mobboss_apps.rooms.adapters.outbound.sqlite_impl import (
    SqliteRoomsOutboundPortImpl,
)
from project.mobboss_apps.rooms.ports.inbound import RoomsInboundPort
from project.mobboss_apps.rooms.ports.outbound import (
    RoomItemMediaOutboundPort,
    RoomsOutboundPort,
)
from project.mobboss_apps.rooms.src.room_service import RoomsService

ContainerMode = Literal["default", "unittest"]


@dataclass(frozen=True)
class Container:
    """Runtime dependency container for the app."""

    mode: ContainerMode
    database_url: str
    weights: Weights
    credentials_outbound_port: CredentialsOutboundPort
    projectsetting_outbound_port: ProjectSettingOutboundPort
    economy_catalog_defaults_outbound_port: EconomyCatalogDefaultsOutboundPort
    gameplay_outbound_port: GameplayOutboundPort
    gameplay_inbound_port: GameplayInboundPort
    iam_outbound_port: IamOutboundPort
    iam_inbound_port: IamInboundPort
    rooms_outbound_port: RoomsOutboundPort
    rooms_inbound_port: RoomsInboundPort
    room_item_media_outbound_port: RoomItemMediaOutboundPort
    room_min_launch_players: int
    room_dev_mode: bool
    room_state_poll_interval_seconds: int
    room_auto_shuffle_interval_seconds: int


def get_container(mode: ContainerMode = "default") -> Container:
    return _get_cached_container(mode)


@lru_cache(maxsize=2)
def _get_cached_container(mode: ContainerMode) -> Container:
    if mode == "default":
        return compose_default_container()
    if mode == "unittest":
        return compose_unittest_container()
    raise ValueError(f"Unsupported container mode: {mode!r}")


def compose_default_container() -> Container:
    # --- Credentials ---
    credentials_outbound_port = MemoryCredentialsOutboundPortImpl.build_default()
    database_credentials = credentials_outbound_port.get_database_credentials()

    # --- Project Settings ---
    projectsetting_outbound_port = MemoryProjectSettingOutboundPortImpl.build_default()
    room_project_settings = projectsetting_outbound_port.get_room_project_settings()
    media_project_settings = projectsetting_outbound_port.get_media_project_settings()

    # --- Outbound Adapters ---
    iam_outbound_port = DjangoIamOutboundPortImpl()
    database_path = database_credentials.database_url.removeprefix("sqlite:///")
    gameplay_outbound_port = SqliteGameplayOutboundPortImpl(db_path=database_path)
    rooms_outbound_port = SqliteRoomsOutboundPortImpl(
        db_path=database_path,
        room_media_root=media_project_settings.media_root,
    )
    room_item_media_outbound_port = FilesystemRoomItemMediaOutboundPortImpl(
        media_root=media_project_settings.media_root or (Path.cwd() / "media"),
        media_url=media_project_settings.media_url,
    )
    economy_defaults_json_path = Path(__file__).resolve().parents[1] / "economy" / "src" / "default_item_catalog.json"
    economy_catalog_defaults_outbound_port = JsonFileEconomyCatalogDefaultsOutboundPortImpl(
        defaults_json_path=economy_defaults_json_path
    )

    # --- Inbound Services ---
    iam_inbound_port = IamService(auth_gateway=iam_outbound_port)
    gameplay_inbound_port = GameplayService(
        repository=gameplay_outbound_port,
        room_lifecycle_outbound_port=RoomsLifecycleSyncOutboundPortImpl(rooms_repository=rooms_outbound_port),
    )
    rooms_inbound_port = RoomsService(
        repository=rooms_outbound_port,
        minimum_launch_players=room_project_settings.minimum_launch_players,
        gameplay_inbound_port=gameplay_inbound_port,
    )

    # --- Container ---
    return Container(
        mode="default",
        database_url=database_credentials.database_url,
        weights=DEFAULT_WEIGHTS,
        credentials_outbound_port=credentials_outbound_port,
        projectsetting_outbound_port=projectsetting_outbound_port,
        economy_catalog_defaults_outbound_port=economy_catalog_defaults_outbound_port,
        gameplay_outbound_port=gameplay_outbound_port,
        gameplay_inbound_port=gameplay_inbound_port,
        iam_outbound_port=iam_outbound_port,
        iam_inbound_port=iam_inbound_port,
        rooms_outbound_port=rooms_outbound_port,
        rooms_inbound_port=rooms_inbound_port,
        room_item_media_outbound_port=room_item_media_outbound_port,
        room_min_launch_players=room_project_settings.minimum_launch_players,
        room_dev_mode=room_project_settings.dev_mode,
        room_state_poll_interval_seconds=room_project_settings.state_poll_interval_seconds,
        room_auto_shuffle_interval_seconds=room_project_settings.auto_shuffle_interval_seconds,
    )


def compose_unittest_container() -> Container:
    # --- Credentials ---
    credentials_outbound_port = MemoryCredentialsOutboundPortImpl.build_unittest()
    database_credentials = credentials_outbound_port.get_database_credentials()

    # --- Project Settings ---
    projectsetting_outbound_port = MemoryProjectSettingOutboundPortImpl.build_unittest()
    room_project_settings = projectsetting_outbound_port.get_room_project_settings()
    media_project_settings = projectsetting_outbound_port.get_media_project_settings()

    # --- Outbound Adapters ---
    iam_outbound_port = MemoryIamOutboundPortImpl()
    gameplay_outbound_port = MemoryGameplayOutboundPortImpl()
    rooms_outbound_port = MemoryRoomsOutboundPortImpl(room_media_root=media_project_settings.media_root)
    room_item_media_outbound_port = MemoryRoomItemMediaOutboundPortImpl(media_url=media_project_settings.media_url)
    economy_catalog_defaults_outbound_port = MemoryEconomyCatalogDefaultsOutboundPortImpl()

    # --- Inbound Services ---
    iam_inbound_port = IamService(auth_gateway=iam_outbound_port)
    gameplay_inbound_port = GameplayService(
        repository=gameplay_outbound_port,
        room_lifecycle_outbound_port=RoomsLifecycleSyncOutboundPortImpl(rooms_repository=rooms_outbound_port),
    )
    rooms_inbound_port = RoomsService(
        repository=rooms_outbound_port,
        minimum_launch_players=room_project_settings.minimum_launch_players,
        gameplay_inbound_port=gameplay_inbound_port,
    )

    # --- Container ---
    return Container(
        mode="unittest",
        database_url=database_credentials.database_url,
        weights=DEFAULT_WEIGHTS,
        credentials_outbound_port=credentials_outbound_port,
        projectsetting_outbound_port=projectsetting_outbound_port,
        economy_catalog_defaults_outbound_port=economy_catalog_defaults_outbound_port,
        gameplay_outbound_port=gameplay_outbound_port,
        gameplay_inbound_port=gameplay_inbound_port,
        iam_outbound_port=iam_outbound_port,
        iam_inbound_port=iam_inbound_port,
        rooms_outbound_port=rooms_outbound_port,
        rooms_inbound_port=rooms_inbound_port,
        room_item_media_outbound_port=room_item_media_outbound_port,
        room_min_launch_players=room_project_settings.minimum_launch_players,
        room_dev_mode=room_project_settings.dev_mode,
        room_state_poll_interval_seconds=room_project_settings.state_poll_interval_seconds,
        room_auto_shuffle_interval_seconds=room_project_settings.auto_shuffle_interval_seconds,
    )
