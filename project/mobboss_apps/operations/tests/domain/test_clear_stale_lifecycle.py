import json
import sqlite3
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.operations.management.commands.clear_stale_lifecycle import (  # noqa: E402
    _find_stale_in_progress_gameplay_sessions,
    _find_stale_in_progress_rooms,
)


class ClearStaleLifecycleTests(unittest.TestCase):
    def test_finds_inactive_gameplay_and_linked_room_after_24_hours(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE rooms (
                room_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                launched_game_id TEXT
            );
            CREATE TABLE gameplay_sessions (
                game_id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                status TEXT NOT NULL,
                phase TEXT NOT NULL,
                version INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )

        payload = {
            "game_id": "g-1",
            "room_id": "r-1",
            "status": "in_progress",
            "phase": "information",
            "version": 5,
            "launched_at_epoch_seconds": 1000,
            "last_progressed_at_epoch_seconds": 1000,
        }
        conn.execute(
            "INSERT INTO rooms(room_id, name, status, launched_game_id) VALUES(?, ?, ?, ?)",
            ("r-1", "Sam's room", "in_progress", "g-1"),
        )
        conn.execute(
            "INSERT INTO gameplay_sessions(game_id, room_id, status, phase, version, payload_json) VALUES(?, ?, ?, ?, ?, ?)",
            ("g-1", "r-1", "in_progress", "information", 5, json.dumps(payload)),
        )

        now_epoch_seconds = 1000 + (24 * 60 * 60) + 1
        stale_games = _find_stale_in_progress_gameplay_sessions(conn, now_epoch_seconds=now_epoch_seconds)
        stale_rooms = _find_stale_in_progress_rooms(conn, now_epoch_seconds=now_epoch_seconds)

        self.assertEqual([(entry.game_id, entry.room_id, entry.reason) for entry in stale_games], [("g-1", "r-1", "inactive_24h")])
        self.assertEqual(
            [(entry.room_id, entry.launched_game_id, entry.reason) for entry in stale_rooms],
            [("r-1", "g-1", "linked_gameplay_inactive_24h")],
        )


if __name__ == "__main__":
    unittest.main()
