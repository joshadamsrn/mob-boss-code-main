"""SQLite query helpers for gameplay persistence."""

from __future__ import annotations

import sqlite3
from typing import Any


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gameplay_sessions (
            game_id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            status TEXT NOT NULL,
            phase TEXT NOT NULL,
            version INTEGER NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS gameplay_game_sequence (
            room_id TEXT PRIMARY KEY,
            seq INTEGER NOT NULL
        );
        """
    )
    conn.commit()


def reserve_game_sequence(conn: sqlite3.Connection, room_id: str) -> int:
    with conn:
        row = conn.execute(
            "SELECT seq FROM gameplay_game_sequence WHERE room_id = ?",
            (room_id,),
        ).fetchone()
        if row is None:
            seq = 1
            conn.execute(
                "INSERT INTO gameplay_game_sequence(room_id, seq) VALUES(?, ?)",
                (room_id, seq),
            )
        else:
            seq = int(row["seq"]) + 1
            conn.execute(
                "UPDATE gameplay_game_sequence SET seq = ? WHERE room_id = ?",
                (seq, room_id),
            )
    return seq


def upsert_game_session(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO gameplay_sessions(game_id, room_id, status, phase, version, payload_json)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id) DO UPDATE SET
                room_id=excluded.room_id,
                status=excluded.status,
                phase=excluded.phase,
                version=excluded.version,
                payload_json=excluded.payload_json
            """,
            (
                record["game_id"],
                record["room_id"],
                record["status"],
                record["phase"],
                record["version"],
                record["payload_json"],
            ),
        )


def get_game_session(conn: sqlite3.Connection, game_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT game_id, room_id, status, phase, version, payload_json
        FROM gameplay_sessions
        WHERE game_id = ?
        """,
        (game_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "game_id": row["game_id"],
        "room_id": row["room_id"],
        "status": row["status"],
        "phase": row["phase"],
        "version": int(row["version"]),
        "payload_json": row["payload_json"],
    }
