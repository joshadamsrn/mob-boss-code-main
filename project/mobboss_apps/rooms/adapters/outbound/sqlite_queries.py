"""SQLite query helpers for rooms persistence.

These functions execute SQL and return plain Python dict/list structures.
The repository adapter maps those structures to DTO snapshots.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS rooms (
            room_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            moderator_user_id TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS room_members (
            room_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            membership_status TEXT NOT NULL,
            is_ready INTEGER NOT NULL,
            starting_balance INTEGER NOT NULL,
            assigned_faction TEXT,
            assigned_role_name TEXT,
            assigned_rank INTEGER,
            PRIMARY KEY (room_id, user_id),
            FOREIGN KEY (room_id) REFERENCES rooms(room_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS room_items (
            room_id TEXT NOT NULL,
            classification TEXT NOT NULL,
            display_name TEXT NOT NULL,
            base_price INTEGER NOT NULL,
            image_path TEXT NOT NULL,
            is_active INTEGER NOT NULL,
            PRIMARY KEY (room_id, classification),
            FOREIGN KEY (room_id) REFERENCES rooms(room_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS room_game_sequence (
            room_id TEXT PRIMARY KEY,
            seq INTEGER NOT NULL
        );
        """
    )
    columns = conn.execute("PRAGMA table_info(rooms)").fetchall()
    if "created_at" not in {row["name"] for row in columns}:
        conn.execute("ALTER TABLE rooms ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP")
    conn.commit()


def upsert_room(conn: sqlite3.Connection, room: dict[str, Any]) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO rooms(room_id, name, status, moderator_user_id, created_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(room_id) DO UPDATE SET
                name=excluded.name,
                status=excluded.status,
                moderator_user_id=excluded.moderator_user_id,
                created_at=excluded.created_at
            """,
            (
                room["room_id"],
                room["name"],
                room["status"],
                room["moderator_user_id"],
                room["created_at"],
            ),
        )
        conn.execute("DELETE FROM room_members WHERE room_id = ?", (room["room_id"],))
        conn.execute("DELETE FROM room_items WHERE room_id = ?", (room["room_id"],))

        for member in room["members"]:
            conn.execute(
                """
                INSERT INTO room_members(
                    room_id, user_id, username, membership_status, is_ready, starting_balance,
                    assigned_faction, assigned_role_name, assigned_rank
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    room["room_id"],
                    member["user_id"],
                    member["username"],
                    member["membership_status"],
                    member["is_ready"],
                    member["starting_balance"],
                    member["assigned_faction"],
                    member["assigned_role_name"],
                    member["assigned_rank"],
                ),
            )

        for item in room["items"]:
            conn.execute(
                """
                INSERT INTO room_items(room_id, classification, display_name, base_price, image_path, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    room["room_id"],
                    item["classification"],
                    item["display_name"],
                    item["base_price"],
                    item["image_path"],
                    item["is_active"],
                ),
            )


def get_room(conn: sqlite3.Connection, room_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT room_id, name, status, moderator_user_id, created_at FROM rooms WHERE room_id = ?",
        (room_id,),
    ).fetchone()
    if row is None:
        return None

    members_rows = conn.execute(
        """
        SELECT user_id, username, membership_status, is_ready, starting_balance,
               assigned_faction, assigned_role_name, assigned_rank
        FROM room_members
        WHERE room_id = ?
        ORDER BY username ASC
        """,
        (room_id,),
    ).fetchall()

    item_rows = conn.execute(
        """
        SELECT classification, display_name, base_price, image_path, is_active
        FROM room_items
        WHERE room_id = ?
        ORDER BY classification ASC
        """,
        (room_id,),
    ).fetchall()

    return {
        "room_id": row["room_id"],
        "name": row["name"],
        "status": row["status"],
        "moderator_user_id": row["moderator_user_id"],
        "created_at": row["created_at"],
        "members": [
            {
                "user_id": member["user_id"],
                "username": member["username"],
                "membership_status": member["membership_status"],
                "is_ready": member["is_ready"],
                "starting_balance": member["starting_balance"],
                "assigned_faction": member["assigned_faction"],
                "assigned_role_name": member["assigned_role_name"],
                "assigned_rank": member["assigned_rank"],
            }
            for member in members_rows
        ],
        "items": [
            {
                "classification": item["classification"],
                "display_name": item["display_name"],
                "base_price": item["base_price"],
                "image_path": item["image_path"],
                "is_active": item["is_active"],
            }
            for item in item_rows
        ],
    }


def list_active_rooms(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            r.room_id,
            r.name,
            r.status,
            r.moderator_user_id,
            COALESCE(
                SUM(
                    CASE
                        WHEN m.membership_status = 'joined' AND m.user_id <> r.moderator_user_id THEN 1
                        ELSE 0
                    END
                ),
                0
            ) AS member_count
        FROM rooms r
        LEFT JOIN room_members m ON m.room_id = r.room_id
        WHERE r.status <> 'ended'
        GROUP BY r.room_id, r.name, r.status, r.moderator_user_id
        ORDER BY r.created_at DESC
        """
    ).fetchall()

    return [
        {
            "room_id": row["room_id"],
            "name": row["name"],
            "status": row["status"],
            "moderator_user_id": row["moderator_user_id"],
            "member_count": row["member_count"],
        }
        for row in rows
    ]


def reserve_game_sequence(conn: sqlite3.Connection, room_id: str) -> int:
    with conn:
        row = conn.execute(
            "SELECT seq FROM room_game_sequence WHERE room_id = ?",
            (room_id,),
        ).fetchone()
        if row is None:
            seq = 1
            conn.execute(
                "INSERT INTO room_game_sequence(room_id, seq) VALUES(?, ?)",
                (room_id, seq),
            )
        else:
            seq = int(row["seq"]) + 1
            conn.execute(
                "UPDATE room_game_sequence SET seq = ? WHERE room_id = ?",
                (seq, room_id),
            )
    return seq


def delete_room(conn: sqlite3.Connection, room_id: str) -> None:
    with conn:
        conn.execute("DELETE FROM room_game_sequence WHERE room_id = ?", (room_id,))
        conn.execute("DELETE FROM rooms WHERE room_id = ?", (room_id,))
