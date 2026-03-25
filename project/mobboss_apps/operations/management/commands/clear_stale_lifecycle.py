from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from project.mobboss_apps.mobboss.composition import get_container

INACTIVITY_AUTO_END_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class _StaleRoom:
    room_id: str
    launched_game_id: str | None
    reason: str


@dataclass(frozen=True)
class _StaleGameplay:
    game_id: str
    room_id: str
    reason: str


class Command(BaseCommand):
    help = (
        "Clear stale in-progress rooms/gameplay sessions, including 24h inactivity. "
        "Dry-run by default; pass --apply to persist updates."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply lifecycle cleanup updates. Default is dry-run.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        apply_updates = bool(options["apply"])
        container = get_container("default")
        db_url = container.database_url
        if not db_url.startswith("sqlite:///"):
            raise CommandError("clear_stale_lifecycle currently supports sqlite:/// databases only.")
        db_path = db_url.removeprefix("sqlite:///")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        try:
            now_epoch_seconds = int(datetime.now(tz=timezone.utc).timestamp())
            stale_rooms = _find_stale_in_progress_rooms(conn, now_epoch_seconds=now_epoch_seconds)
            stale_gameplay = _find_stale_in_progress_gameplay_sessions(conn, now_epoch_seconds=now_epoch_seconds)

            self.stdout.write(
                f"Detected stale lifecycle records: {len(stale_rooms)} room(s), {len(stale_gameplay)} gameplay session(s)."
            )
            for room in stale_rooms:
                self.stdout.write(
                    f"ROOM stale: room_id={room.room_id} launched_game_id={room.launched_game_id!r} reason={room.reason}"
                )
            for session in stale_gameplay:
                self.stdout.write(
                    f"GAME stale: game_id={session.game_id} room_id={session.room_id} reason={session.reason}"
                )

            if not apply_updates:
                self.stdout.write("Dry-run only. Re-run with --apply to persist cleanup.")
                return

            with conn:
                for room in stale_rooms:
                    _end_room(conn, room.room_id)
                for session in stale_gameplay:
                    _end_gameplay_session(conn, session.game_id)

            self.stdout.write(
                f"Applied cleanup: ended {len(stale_rooms)} room(s) and {len(stale_gameplay)} gameplay session(s)."
            )
        finally:
            conn.close()


def _find_stale_in_progress_rooms(conn: sqlite3.Connection, *, now_epoch_seconds: int) -> list[_StaleRoom]:
    rows = conn.execute(
        """
        SELECT room_id, launched_game_id
        FROM rooms
        WHERE status = 'in_progress'
        """
    ).fetchall()
    stale: list[_StaleRoom] = []

    for row in rows:
        room_id = str(row["room_id"])
        launched_game_id = row["launched_game_id"]
        if launched_game_id is None:
            stale.append(_StaleRoom(room_id=room_id, launched_game_id=None, reason="missing_launched_game_id"))
            continue

        session = conn.execute(
            "SELECT status, payload_json FROM gameplay_sessions WHERE game_id = ?",
            (launched_game_id,),
        ).fetchone()
        if session is None:
            stale.append(
                _StaleRoom(
                    room_id=room_id,
                    launched_game_id=str(launched_game_id),
                    reason="missing_gameplay_session",
                )
            )
            continue
        if str(session["status"]) == "ended":
            stale.append(
                _StaleRoom(
                    room_id=room_id,
                    launched_game_id=str(launched_game_id),
                    reason="linked_gameplay_already_ended",
                )
            )
            continue

        payload = json.loads(str(session["payload_json"]))
        last_progressed_at = _last_progressed_at_epoch_seconds(payload)
        if now_epoch_seconds - last_progressed_at >= INACTIVITY_AUTO_END_SECONDS:
            stale.append(
                _StaleRoom(
                    room_id=room_id,
                    launched_game_id=str(launched_game_id),
                    reason="linked_gameplay_inactive_24h",
                )
            )

    return stale


def _find_stale_in_progress_gameplay_sessions(conn: sqlite3.Connection, *, now_epoch_seconds: int) -> list[_StaleGameplay]:
    rows = conn.execute(
        """
        SELECT game_id, room_id, payload_json
        FROM gameplay_sessions
        WHERE status = 'in_progress'
        """
    ).fetchall()
    stale: list[_StaleGameplay] = []

    for row in rows:
        game_id = str(row["game_id"])
        room_id = str(row["room_id"])
        payload = json.loads(str(row["payload_json"]))
        last_progressed_at = _last_progressed_at_epoch_seconds(payload)
        if now_epoch_seconds - last_progressed_at >= INACTIVITY_AUTO_END_SECONDS:
            stale.append(_StaleGameplay(game_id=game_id, room_id=room_id, reason="inactive_24h"))
            continue

        room = conn.execute(
            "SELECT status, launched_game_id FROM rooms WHERE room_id = ?",
            (room_id,),
        ).fetchone()
        if room is None:
            stale.append(_StaleGameplay(game_id=game_id, room_id=room_id, reason="missing_room"))
            continue

        room_status = str(room["status"])
        room_launched_game_id = room["launched_game_id"]
        if room_status == "ended":
            stale.append(_StaleGameplay(game_id=game_id, room_id=room_id, reason="room_already_ended"))
            continue
        if room_launched_game_id is None:
            stale.append(_StaleGameplay(game_id=game_id, room_id=room_id, reason="room_missing_launched_game_id"))
            continue
        if str(room_launched_game_id) != game_id:
            stale.append(_StaleGameplay(game_id=game_id, room_id=room_id, reason="room_points_to_different_game"))

    return stale


def _end_room(conn: sqlite3.Connection, room_id: str) -> None:
    conn.execute(
        """
        UPDATE rooms
        SET status = 'ended',
            launched_game_id = NULL
        WHERE room_id = ?
        """,
        (room_id,),
    )
    conn.execute(
        """
        UPDATE room_members
        SET membership_status = 'left',
            is_ready = 0,
            assigned_faction = NULL,
            assigned_role_name = NULL,
            assigned_rank = NULL
        WHERE room_id = ?
        """,
        (room_id,),
    )


def _end_gameplay_session(conn: sqlite3.Connection, game_id: str) -> None:
    row = conn.execute(
        """
        SELECT payload_json, version
        FROM gameplay_sessions
        WHERE game_id = ?
        """,
        (game_id,),
    ).fetchone()
    if row is None:
        return

    payload = json.loads(str(row["payload_json"]))
    payload["status"] = "ended"
    payload["phase"] = "ended"
    payload["version"] = int(row["version"]) + 1
    now_epoch_seconds = int(datetime.now(tz=timezone.utc).timestamp())
    payload.setdefault("ended_at_epoch_seconds", now_epoch_seconds)
    payload["last_progressed_at_epoch_seconds"] = now_epoch_seconds

    conn.execute(
        """
        UPDATE gameplay_sessions
        SET status = 'ended',
            phase = 'ended',
            version = ?,
            payload_json = ?
        WHERE game_id = ?
        """,
        (payload["version"], json.dumps(payload, sort_keys=True), game_id),
    )


def _last_progressed_at_epoch_seconds(payload: dict[str, Any]) -> int:
    value = payload.get("last_progressed_at_epoch_seconds")
    if value is not None:
        return int(value)
    return int(payload.get("launched_at_epoch_seconds", 0))
