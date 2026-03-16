import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.rooms.views import (
    _build_dev_seat_user_id,
    _is_dev_seat_user_id,
    _next_dev_seat_number,
)


class _Member:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id


class DevSeatHelperTests(unittest.TestCase):
    def test_build_dev_seat_user_id_zero_pads_suffix(self) -> None:
        self.assertEqual(_build_dev_seat_user_id(3), "dev-seat-03")

    def test_is_dev_seat_user_id_matches_expected_prefix(self) -> None:
        self.assertTrue(_is_dev_seat_user_id("dev-seat-01"))
        self.assertFalse(_is_dev_seat_user_id("u_123"))

    def test_next_dev_seat_number_uses_highest_existing_suffix(self) -> None:
        members = [_Member("u_mod"), _Member("dev-seat-02"), _Member("dev-seat-09"), _Member("dev-seat-bad")]
        self.assertEqual(_next_dev_seat_number(members), 10)


if __name__ == "__main__":
    unittest.main()
