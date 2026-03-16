import sys
import unittest
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"

from project.mobboss_apps.gameplay.adapters.outbound.memory_impl import (  # noqa: E402
    MemoryGameplayOutboundPortImpl,
)
from project.mobboss_apps.gameplay.ports.internal import (  # noqa: E402
    AdvanceAccusedSelectionTimeoutCommand,
    ReportDeathCommand,
    StartSessionCatalogItemInput,
    StartSessionFromRoomCommand,
    StartSessionParticipantInput,
)
from project.mobboss_apps.gameplay.src.game_service import GameplayService  # noqa: E402
from project.mobboss_apps.mobboss.exceptions import ConflictProblem  # noqa: E402


def _load_json_fixture(name: str) -> dict:
    return json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))


def _build_start_session_command(name: str) -> StartSessionFromRoomCommand:
    payload = _load_json_fixture(name)
    return StartSessionFromRoomCommand(
        room_id=str(payload["room_id"]),
        moderator_user_id=str(payload["moderator_user_id"]),
        launched_at_epoch_seconds=int(payload["launched_at_epoch_seconds"]),
        participants=[
            StartSessionParticipantInput(
                user_id=str(participant["user_id"]),
                username=str(participant["username"]),
                faction=str(participant["faction"]),
                role_name=str(participant["role_name"]),
                rank=int(participant["rank"]),
                starting_balance=int(participant["starting_balance"]),
            )
            for participant in payload.get("participants", [])
        ],
        catalog=[
            StartSessionCatalogItemInput(
                classification=str(item["classification"]),
                display_name=str(item["display_name"]),
                base_price=int(item["base_price"]),
                image_path=str(item["image_path"]),
                is_active=bool(item["is_active"]),
            )
            for item in payload.get("catalog", [])
        ],
    )


class GameplayServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = MemoryGameplayOutboundPortImpl()
        self.now_epoch_seconds = 1000
        self.service = GameplayService(
            repository=self.repository,
            now_epoch_seconds_provider=lambda: self.now_epoch_seconds,
        )

    def test_start_session_from_room_bootstraps_information_phase_snapshot(self) -> None:
        command = _build_start_session_command("start_session_information.json")

        snapshot = self.service.start_session_from_room(command)

        self.assertTrue(snapshot.game_id.startswith("r-1-g"))
        self.assertEqual(snapshot.room_id, "r-1")
        self.assertEqual(snapshot.status, "in_progress")
        self.assertEqual(snapshot.phase, "information")
        self.assertEqual(snapshot.round_number, 1)
        self.assertEqual(snapshot.version, 1)
        self.assertEqual(snapshot.launched_at_epoch_seconds, 111)
        self.assertEqual(len(snapshot.participants), 2)
        self.assertTrue(all(participant.life_state == "alive" for participant in snapshot.participants))
        self.assertEqual(snapshot.participants[0].money_balance, 300)
        self.assertEqual(snapshot.catalog[0].classification, "knife")

        fetched = self.service.get_game_details(snapshot.game_id)
        self.assertEqual(fetched.game_id, snapshot.game_id)

    def test_report_death_moves_session_to_accused_selection_when_police_alive(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                expected_version=1,
            )
        )

        murdered = next(participant for participant in updated.participants if participant.user_id == "u_mob")
        self.assertEqual(murdered.life_state, "dead")
        self.assertEqual(updated.phase, "accused_selection")
        self.assertEqual(updated.version, 2)
        self.assertIsNotNone(updated.pending_trial)
        self.assertEqual(updated.pending_trial.accused_selection_cursor, ["u_police"])
        self.assertEqual(updated.pending_trial.accused_selection_deadline_epoch_seconds, 1015)
        self.assertIsNone(updated.pending_trial.resolution)

    def test_report_death_without_alive_police_goes_to_no_conviction_branch(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_no_police.json"))

        updated = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_merchant",
                reported_by_user_id="u_mod",
                expected_version=1,
            )
        )

        self.assertEqual(updated.phase, "boundary_resolution")
        self.assertIsNotNone(updated.pending_trial)
        self.assertEqual(updated.pending_trial.accused_selection_cursor, [])
        self.assertEqual(updated.pending_trial.resolution, "no_conviction")

    def test_report_death_rejects_stale_expected_version(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.report_death(
                ReportDeathCommand(
                    game_id=started.game_id,
                    murdered_user_id="u_mob",
                    reported_by_user_id="u_mod",
                    expected_version=started.version + 1,
                )
            )
        self.assertEqual(exc_ctx.exception.code, "version_conflict")
        self.assertEqual(
            exc_ctx.exception.extensions,
            {"expected_version": started.version + 1, "current_version": started.version},
        )

    def test_report_death_requires_moderator_reporter(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))

        with self.assertRaises(PermissionError):
            self.service.report_death(
                ReportDeathCommand(
                    game_id=started.game_id,
                    murdered_user_id="u_mob",
                    reported_by_user_id="u_police",
                    expected_version=started.version,
                )
            )

    def test_report_death_rejects_when_trial_already_pending(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_police_alive.json"))
        after_first = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                expected_version=started.version,
            )
        )

        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.report_death(
                ReportDeathCommand(
                    game_id=after_first.game_id,
                    murdered_user_id="u_police",
                    reported_by_user_id="u_mod",
                    expected_version=after_first.version,
                )
            )
        self.assertEqual(exc_ctx.exception.code, "invalid_state")

    def test_accused_selection_timeout_chain_progresses_in_rank_order(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_two_police.json"))
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                expected_version=started.version,
            )
        )

        self.assertEqual(after_report.phase, "accused_selection")
        self.assertEqual(after_report.pending_trial.accused_selection_cursor, ["u_chief", "u_deputy"])
        self.assertEqual(after_report.pending_trial.accused_selection_deadline_epoch_seconds, 1015)

        self.now_epoch_seconds = 1015
        first_advance = self.service.advance_accused_selection_timeout(
            AdvanceAccusedSelectionTimeoutCommand(
                game_id=after_report.game_id,
                requested_by_user_id="u_mod",
                expected_version=after_report.version,
            )
        )
        self.assertEqual(first_advance.phase, "accused_selection")
        self.assertEqual(first_advance.pending_trial.accused_selection_cursor, ["u_deputy"])
        self.assertEqual(first_advance.pending_trial.accused_selection_deadline_epoch_seconds, 1030)

        self.now_epoch_seconds = 1030
        second_advance = self.service.advance_accused_selection_timeout(
            AdvanceAccusedSelectionTimeoutCommand(
                game_id=first_advance.game_id,
                requested_by_user_id="u_mod",
                expected_version=first_advance.version,
            )
        )
        self.assertEqual(second_advance.phase, "boundary_resolution")
        self.assertEqual(second_advance.status, "in_progress")
        self.assertEqual(second_advance.pending_trial.accused_selection_cursor, [])
        self.assertIsNone(second_advance.pending_trial.accused_selection_deadline_epoch_seconds)
        self.assertEqual(second_advance.pending_trial.resolution, "no_conviction")

    def test_accused_selection_timeout_advance_requires_elapsed_deadline(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_two_police.json"))
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                expected_version=started.version,
            )
        )

        with self.assertRaises(ConflictProblem):
            self.service.advance_accused_selection_timeout(
                AdvanceAccusedSelectionTimeoutCommand(
                    game_id=after_report.game_id,
                    requested_by_user_id="u_mod",
                    expected_version=after_report.version,
                )
            )

    def test_advance_accused_selection_timeout_rejects_stale_expected_version(self) -> None:
        started = self.service.start_session_from_room(_build_start_session_command("start_session_two_police.json"))
        after_report = self.service.report_death(
            ReportDeathCommand(
                game_id=started.game_id,
                murdered_user_id="u_mob",
                reported_by_user_id="u_mod",
                expected_version=started.version,
            )
        )
        self.now_epoch_seconds = 1015

        with self.assertRaises(ConflictProblem) as exc_ctx:
            self.service.advance_accused_selection_timeout(
                AdvanceAccusedSelectionTimeoutCommand(
                    game_id=after_report.game_id,
                    requested_by_user_id="u_mod",
                    expected_version=after_report.version + 1,
                )
            )
        self.assertEqual(exc_ctx.exception.code, "version_conflict")
        self.assertEqual(
            exc_ctx.exception.extensions,
            {"expected_version": after_report.version + 1, "current_version": after_report.version},
        )


if __name__ == "__main__":
    unittest.main()
