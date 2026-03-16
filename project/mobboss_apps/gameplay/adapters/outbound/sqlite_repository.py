"""SQLite outbound adapter for gameplay sessions."""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from project.mobboss_apps.gameplay.adapters.outbound import sqlite_queries
from project.mobboss_apps.gameplay.ports.internal import (
    CatalogItemStateSnapshot,
    GameDetailsSnapshot,
    ParticipantStateSnapshot,
    TrialStateSnapshot,
)
from project.mobboss_apps.gameplay.ports.outbound import GameplayOutboundPort


class SqliteGameplayRepository(GameplayOutboundPort):
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        sqlite_queries.ensure_schema(self._conn)

    def reserve_game_id(self, room_id: str) -> str:
        seq = sqlite_queries.reserve_game_sequence(self._conn, room_id)
        token = str(uuid4())[:8]
        return f"{room_id}-g{seq}-{token}"

    def save_game_session(self, snapshot: GameDetailsSnapshot) -> None:
        sqlite_queries.upsert_game_session(self._conn, _snapshot_to_record(snapshot))

    def get_game_session(self, game_id: str) -> GameDetailsSnapshot | None:
        record = sqlite_queries.get_game_session(self._conn, game_id)
        if record is None:
            return None
        return _record_to_snapshot(record)

    def close(self) -> None:
        self._conn.close()


def _snapshot_to_record(snapshot: GameDetailsSnapshot) -> dict[str, object]:
    payload = {
        "game_id": snapshot.game_id,
        "room_id": snapshot.room_id,
        "moderator_user_id": snapshot.moderator_user_id,
        "status": snapshot.status,
        "phase": snapshot.phase,
        "round_number": snapshot.round_number,
        "version": snapshot.version,
        "launched_at_epoch_seconds": snapshot.launched_at_epoch_seconds,
        "ended_at_epoch_seconds": snapshot.ended_at_epoch_seconds,
        "participants": [
            {
                "user_id": participant.user_id,
                "username": participant.username,
                "faction": participant.faction,
                "role_name": participant.role_name,
                "rank": participant.rank,
                "life_state": participant.life_state,
                "money_balance": participant.money_balance,
            }
            for participant in snapshot.participants
        ],
        "catalog": [
            {
                "classification": item.classification,
                "display_name": item.display_name,
                "base_price": item.base_price,
                "image_path": item.image_path,
                "is_active": item.is_active,
            }
            for item in snapshot.catalog
        ],
        "pending_trial": (
            None
            if snapshot.pending_trial is None
            else {
                "murdered_user_id": snapshot.pending_trial.murdered_user_id,
                "murderer_user_id": snapshot.pending_trial.murderer_user_id,
                "accused_user_id": snapshot.pending_trial.accused_user_id,
                "accused_selection_cursor": list(snapshot.pending_trial.accused_selection_cursor),
                "accused_selection_deadline_epoch_seconds": snapshot.pending_trial.accused_selection_deadline_epoch_seconds,
                "jury_user_ids": list(snapshot.pending_trial.jury_user_ids),
                "vote_deadline_epoch_seconds": snapshot.pending_trial.vote_deadline_epoch_seconds,
                "votes": list(snapshot.pending_trial.votes),
                "verdict": snapshot.pending_trial.verdict,
                "conviction_correct": snapshot.pending_trial.conviction_correct,
                "resolution": snapshot.pending_trial.resolution,
            }
        ),
    }
    return {
        "game_id": snapshot.game_id,
        "room_id": snapshot.room_id,
        "status": snapshot.status,
        "phase": snapshot.phase,
        "version": snapshot.version,
        "payload_json": json.dumps(payload, sort_keys=True),
    }


def _record_to_snapshot(record: dict[str, object]) -> GameDetailsSnapshot:
    payload = json.loads(str(record["payload_json"]))

    pending_trial_payload = payload.get("pending_trial")
    pending_trial = None
    if pending_trial_payload is not None:
        pending_trial = TrialStateSnapshot(
            murdered_user_id=str(pending_trial_payload["murdered_user_id"]),
            murderer_user_id=_as_optional_str(pending_trial_payload.get("murderer_user_id")),
            accused_user_id=_as_optional_str(pending_trial_payload.get("accused_user_id")),
            accused_selection_cursor=[str(user_id) for user_id in pending_trial_payload.get("accused_selection_cursor", [])],
            accused_selection_deadline_epoch_seconds=_as_optional_int(
                pending_trial_payload.get("accused_selection_deadline_epoch_seconds")
            ),
            jury_user_ids=[str(user_id) for user_id in pending_trial_payload.get("jury_user_ids", [])],
            vote_deadline_epoch_seconds=_as_optional_int(pending_trial_payload.get("vote_deadline_epoch_seconds")),
            votes=[dict(vote) for vote in pending_trial_payload.get("votes", [])],
            verdict=_as_optional_str(pending_trial_payload.get("verdict")),
            conviction_correct=_as_optional_bool(pending_trial_payload.get("conviction_correct")),
            resolution=_as_optional_str(pending_trial_payload.get("resolution")),
        )

    return GameDetailsSnapshot(
        game_id=str(payload["game_id"]),
        room_id=str(payload["room_id"]),
        moderator_user_id=str(payload["moderator_user_id"]),
        status=str(payload["status"]),
        phase=str(payload["phase"]),
        round_number=int(payload["round_number"]),
        version=int(payload["version"]),
        launched_at_epoch_seconds=int(payload["launched_at_epoch_seconds"]),
        ended_at_epoch_seconds=_as_optional_int(payload.get("ended_at_epoch_seconds")),
        participants=[
            ParticipantStateSnapshot(
                user_id=str(participant["user_id"]),
                username=str(participant["username"]),
                faction=str(participant["faction"]),
                role_name=str(participant["role_name"]),
                rank=int(participant["rank"]),
                life_state=str(participant["life_state"]),
                money_balance=int(participant["money_balance"]),
            )
            for participant in payload.get("participants", [])
        ],
        catalog=[
            CatalogItemStateSnapshot(
                classification=str(item["classification"]),
                display_name=str(item["display_name"]),
                base_price=int(item["base_price"]),
                image_path=str(item["image_path"]),
                is_active=bool(item["is_active"]),
            )
            for item in payload.get("catalog", [])
        ],
        pending_trial=pending_trial,
    )


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)
