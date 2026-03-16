import sys
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.gameplay.ports.internal import (  # noqa: E402
    GameDetailsSnapshot,
    ParticipantStateSnapshot,
    TrialStateSnapshot,
)
from project.mobboss_apps.gameplay.v1_views import (  # noqa: E402
    AdvanceAccusedSelectionTimeoutView,
    GameDetailView,
    ReportDeathView,
)
from project.mobboss_apps.mobboss.exceptions import ConflictProblem  # noqa: E402


def _game_snapshot() -> GameDetailsSnapshot:
    return GameDetailsSnapshot(
        game_id="g-1",
        room_id="r-1",
        moderator_user_id="u_mod",
        status="in_progress",
        phase="information",
        round_number=1,
        version=1,
        launched_at_epoch_seconds=100,
        ended_at_epoch_seconds=None,
        participants=[
            ParticipantStateSnapshot(
                user_id="u_p1",
                username="p1",
                faction="Police",
                role_name="Police Chief",
                rank=1,
                life_state="alive",
                money_balance=300,
            ),
            ParticipantStateSnapshot(
                user_id="u_p2",
                username="p2",
                faction="Mob",
                role_name="Mob Boss",
                rank=1,
                life_state="alive",
                money_balance=300,
            ),
        ],
        catalog=[],
        pending_trial=None,
    )


class _StubGameplayInboundPort:
    def __init__(self, snapshot: GameDetailsSnapshot) -> None:
        self.snapshot = snapshot
        self.report_commands = []

    def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
        return self.snapshot

    def report_death(self, command) -> GameDetailsSnapshot:
        self.report_commands.append(command)
        self.snapshot = GameDetailsSnapshot(
            game_id=self.snapshot.game_id,
            room_id=self.snapshot.room_id,
            moderator_user_id=self.snapshot.moderator_user_id,
            status=self.snapshot.status,
            phase="accused_selection",
            round_number=self.snapshot.round_number,
            version=self.snapshot.version + 1,
            launched_at_epoch_seconds=self.snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=self.snapshot.ended_at_epoch_seconds,
            participants=[
                self.snapshot.participants[0],
                ParticipantStateSnapshot(
                    user_id="u_p2",
                    username="p2",
                    faction="Mob",
                    role_name="Mob Boss",
                    rank=1,
                    life_state="dead",
                    money_balance=300,
                ),
            ],
            catalog=self.snapshot.catalog,
            pending_trial=TrialStateSnapshot(
                murdered_user_id=command.murdered_user_id,
                murderer_user_id=None,
                accused_user_id=None,
                accused_selection_cursor=["u_p1"],
                accused_selection_deadline_epoch_seconds=None,
                jury_user_ids=[],
                vote_deadline_epoch_seconds=None,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution=None,
            ),
        )
        return self.snapshot

    def advance_accused_selection_timeout(self, command) -> GameDetailsSnapshot:
        if command.requested_by_user_id != "u_mod":
            raise PermissionError("Only moderator can advance accused-selection timeout.")
        self.report_commands.append(command)
        self.snapshot = GameDetailsSnapshot(
            game_id=self.snapshot.game_id,
            room_id=self.snapshot.room_id,
            moderator_user_id=self.snapshot.moderator_user_id,
            status=self.snapshot.status,
            phase="boundary_resolution",
            round_number=self.snapshot.round_number,
            version=self.snapshot.version + 1,
            launched_at_epoch_seconds=self.snapshot.launched_at_epoch_seconds,
            ended_at_epoch_seconds=self.snapshot.ended_at_epoch_seconds,
            participants=self.snapshot.participants,
            catalog=self.snapshot.catalog,
            pending_trial=TrialStateSnapshot(
                murdered_user_id="u_p2",
                murderer_user_id=None,
                accused_user_id=None,
                accused_selection_cursor=[],
                accused_selection_deadline_epoch_seconds=None,
                jury_user_ids=[],
                vote_deadline_epoch_seconds=None,
                votes=[],
                verdict=None,
                conviction_correct=None,
                resolution="no_conviction",
            ),
        )
        return self.snapshot


class _StubContainer:
    def __init__(self, gameplay_inbound_port: _StubGameplayInboundPort) -> None:
        self.gameplay_inbound_port = gameplay_inbound_port


class GameplayV1ViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.snapshot = _game_snapshot()
        self.gameplay = _StubGameplayInboundPort(self.snapshot)
        self.container = _StubContainer(self.gameplay)
        self.moderator = type("U", (), {"is_authenticated": True, "id": "u_mod", "username": "moderator"})()
        self.player = type("U", (), {"is_authenticated": True, "id": "u_p1", "username": "p1"})()

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_game_detail_moderator_sees_full_participant_roles(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.get("/gameplay/v1/games/g-1")
        request.user = self.moderator

        response = GameDetailView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        self.assertEqual(payload["game_id"], "g-1")
        self.assertEqual(payload["participants"][0]["faction"], "Police")
        self.assertEqual(payload["participants"][1]["role_name"], "Mob Boss")

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_game_detail_player_sees_only_self_role_details(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.get("/gameplay/v1/games/g-1")
        request.user = self.player

        response = GameDetailView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        first = next(participant for participant in payload["participants"] if participant["user_id"] == "u_p1")
        second = next(participant for participant in payload["participants"] if participant["user_id"] == "u_p2")
        self.assertEqual(first["faction"], "Police")
        self.assertNotIn("faction", second)
        self.assertNotIn("role_name", second)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_report_death_requires_moderator(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/report-death",
            data='{"murdered_user_id":"u_p2","expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = ReportDeathView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self.gameplay.report_commands), 0)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_report_death_updates_game_when_requested_by_moderator(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/report-death",
            data='{"murdered_user_id":"u_p2","expected_version":1}',
            content_type="application/json",
        )
        request.user = self.moderator

        response = ReportDeathView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        self.assertEqual(payload["phase"], "accused_selection")
        self.assertEqual(payload["version"], 2)
        self.assertEqual(len(self.gameplay.report_commands), 1)
        self.assertEqual(self.gameplay.report_commands[0].expected_version, 1)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_report_death_requires_expected_version(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/report-death",
            data='{"murdered_user_id":"u_p2"}',
            content_type="application/json",
        )
        request.user = self.moderator

        response = ReportDeathView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.gameplay.report_commands), 0)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_advance_accused_timeout_requires_expected_version(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/advance-accused-selection-timeout",
            data="{}",
            content_type="application/json",
        )
        request.user = self.moderator

        response = AdvanceAccusedSelectionTimeoutView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 422)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_advance_accused_timeout_updates_state_for_moderator(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/advance-accused-selection-timeout",
            data='{"expected_version":1}',
            content_type="application/json",
        )
        request.user = self.moderator

        response = AdvanceAccusedSelectionTimeoutView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))["data"]
        self.assertEqual(payload["phase"], "boundary_resolution")
        self.assertEqual(payload["version"], 2)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_advance_accused_timeout_forbidden_for_non_moderator(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/advance-accused-selection-timeout",
            data='{"expected_version":1}',
            content_type="application/json",
        )
        request.user = self.player

        response = AdvanceAccusedSelectionTimeoutView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 403)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_report_death_returns_409_when_service_detects_version_conflict(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/report-death",
            data='{"murdered_user_id":"u_p2","expected_version":1}',
            content_type="application/json",
        )
        request.user = self.moderator

        with patch.object(
            self.gameplay,
            "report_death",
            side_effect=ConflictProblem(
                "stale version",
                code="version_conflict",
                extensions={"expected_version": 1, "current_version": 2},
            ),
        ):
            response = ReportDeathView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(payload["code"], "version_conflict")
        self.assertEqual(payload["expected_version"], 1)
        self.assertEqual(payload["current_version"], 2)

    @patch("project.mobboss_apps.gameplay.v1_views.get_container")
    def test_advance_timeout_returns_409_when_service_detects_version_conflict(self, mock_get_container) -> None:
        mock_get_container.return_value = self.container
        request = self.factory.post(
            "/gameplay/v1/games/g-1/advance-accused-selection-timeout",
            data='{"expected_version":1}',
            content_type="application/json",
        )
        request.user = self.moderator

        with patch.object(
            self.gameplay,
            "advance_accused_selection_timeout",
            side_effect=ConflictProblem(
                "stale version",
                code="version_conflict",
                extensions={"expected_version": 3, "current_version": 4},
            ),
        ):
            response = AdvanceAccusedSelectionTimeoutView.as_view()(request, game_id="g-1")

        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(payload["code"], "version_conflict")
        self.assertEqual(payload["expected_version"], 3)
        self.assertEqual(payload["current_version"], 4)


if __name__ == "__main__":
    unittest.main()
