"""Internal ports: gameplay DTOs and data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FactionName = Literal["Police", "Mob", "Merchant"]
LifeState = Literal["alive", "dead", "jailed"]
GamePhase = Literal["information", "accused_selection", "trial_voting", "boundary_resolution", "ended"]
GameStatus = Literal["in_progress", "paused", "ended"]
TrialVerdict = Literal["guilty", "innocent"]

RoleName = Literal[
    "Police Chief",
    "Police Deputy",
    "Police Detective",
    "Mob Boss",
    "Mob Member",
    "Knife Hobo",
    "Merchant",
]


@dataclass(frozen=True)
class StartSessionParticipantInput:
    user_id: str
    username: str
    faction: FactionName
    role_name: RoleName
    rank: int
    starting_balance: int


@dataclass(frozen=True)
class StartSessionCatalogItemInput:
    classification: str
    display_name: str
    base_price: int
    image_path: str
    is_active: bool


@dataclass(frozen=True)
class StartSessionFromRoomCommand:
    room_id: str
    moderator_user_id: str
    launched_at_epoch_seconds: int
    participants: list[StartSessionParticipantInput]
    catalog: list[StartSessionCatalogItemInput]


@dataclass(frozen=True)
class ReportDeathCommand:
    game_id: str
    murdered_user_id: str
    reported_by_user_id: str
    expected_version: int


@dataclass(frozen=True)
class AdvanceAccusedSelectionTimeoutCommand:
    game_id: str
    requested_by_user_id: str
    expected_version: int


@dataclass(frozen=True)
class TrialStateSnapshot:
    murdered_user_id: str
    murderer_user_id: str | None
    accused_user_id: str | None
    accused_selection_cursor: list[str]
    accused_selection_deadline_epoch_seconds: int | None
    jury_user_ids: list[str]
    vote_deadline_epoch_seconds: int | None
    votes: list[dict[str, str]]
    verdict: TrialVerdict | None
    conviction_correct: bool | None
    resolution: str | None


@dataclass(frozen=True)
class ParticipantStateSnapshot:
    user_id: str
    username: str
    faction: FactionName
    role_name: RoleName
    rank: int
    life_state: LifeState
    money_balance: int


@dataclass(frozen=True)
class CatalogItemStateSnapshot:
    classification: str
    display_name: str
    base_price: int
    image_path: str
    is_active: bool


@dataclass(frozen=True)
class GameDetailsSnapshot:
    game_id: str
    room_id: str
    moderator_user_id: str
    status: GameStatus
    phase: GamePhase
    round_number: int
    version: int
    launched_at_epoch_seconds: int
    ended_at_epoch_seconds: int | None
    participants: list[ParticipantStateSnapshot]
    catalog: list[CatalogItemStateSnapshot]
    pending_trial: TrialStateSnapshot | None


# Backward-compatible alias used by older call sites.
GameSessionSnapshot = GameDetailsSnapshot
