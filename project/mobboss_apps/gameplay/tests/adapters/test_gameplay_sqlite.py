import sys
import unittest
from dataclasses import replace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
TMP_ROOT = Path(__file__).resolve().parents[1] / "_tmp"

from project.mobboss_apps.gameplay.adapters.outbound.sqlite_repository import (  # noqa: E402
    SqliteGameplayRepository,
)
from project.mobboss_apps.gameplay.ports.internal import (  # noqa: E402
    CatalogItemStateSnapshot,
    GameDetailsSnapshot,
    LedgerEntrySnapshot,
    LedgerStateSnapshot,
    ParticipantPowerStateSnapshot,
    ParticipantStateSnapshot,
    PlayerTransactionSnapshot,
    TrialStateSnapshot,
)


def _snapshot(
    *,
    game_id: str,
    version: int = 1,
    phase: str = "information",
    pending_trial: TrialStateSnapshot | None = None,
) -> GameDetailsSnapshot:
    return GameDetailsSnapshot(
        game_id=game_id,
        room_id="r-1",
        moderator_user_id="u_mod",
        status="in_progress",
        phase=phase,
        round_number=1,
        version=version,
        launched_at_epoch_seconds=100,
        ended_at_epoch_seconds=None,
        participants=[
            ParticipantStateSnapshot(
                user_id="u_police",
                username="police",
                faction="Police",
                role_name="Chief of Police",
                rank=1,
                life_state="alive",
                money_balance=300,
            ),
            ParticipantStateSnapshot(
                user_id="u_mob",
                username="mob",
                faction="Mob",
                role_name="Mob Boss",
                rank=1,
                life_state="alive",
                money_balance=300,
            ),
        ],
        catalog=[
            CatalogItemStateSnapshot(
                classification="knife",
                display_name="Knife",
                base_price=100,
                image_path="/static/items/defaults/default_knife.svg",
                is_active=True,
            )
        ],
        pending_trial=pending_trial,
        ledger=LedgerStateSnapshot(circulating_currency_baseline=600, checksum="seed-checksum"),
    )


class GameplaySqliteAdapterTests(unittest.TestCase):
    def test_reserve_game_id_increments_per_room(self) -> None:
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        db_path = TMP_ROOT / "gameplay_id_sequence.sqlite3"
        if db_path.exists():
            db_path.unlink()

        repository = SqliteGameplayRepository(db_path=str(db_path))
        try:
            first = repository.reserve_game_id("r-1")
            second = repository.reserve_game_id("r-1")
            third = repository.reserve_game_id("r-2")
        finally:
            repository.close()

        self.assertTrue(first.startswith("r-1-g1-"))
        self.assertTrue(second.startswith("r-1-g2-"))
        self.assertTrue(third.startswith("r-2-g1-"))

        if db_path.exists():
            db_path.unlink()

    def test_save_and_get_round_trip_with_pending_trial(self) -> None:
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        db_path = TMP_ROOT / "gameplay_round_trip.sqlite3"
        if db_path.exists():
            db_path.unlink()

        repository = SqliteGameplayRepository(db_path=str(db_path))
        pending_trial = TrialStateSnapshot(
            murdered_user_id="u_mob",
            murderer_user_id=None,
            accused_user_id=None,
            accused_selection_cursor=["u_police"],
            accused_selection_deadline_epoch_seconds=200,
            jury_user_ids=[],
            vote_deadline_epoch_seconds=None,
            votes=[],
            verdict=None,
            conviction_correct=None,
            resolution=None,
        )
        base_snapshot = _snapshot(game_id="r-1-g1-abc12345", version=2, phase="accused_selection", pending_trial=pending_trial)
        expected = replace(
            base_snapshot,
            participants=[
                replace(
                    base_snapshot.participants[0],
                    power_state=ParticipantPowerStateSnapshot(
                        street_thug_steal_used=True,
                        detective_investigation_used=True,
                        detective_investigation_visible_until_epoch_seconds=300,
                        detective_investigation_target_user_id="u_mob",
                        detective_last_viewed_transaction_total=1,
                        detective_last_viewed_transactions=[
                            PlayerTransactionSnapshot(
                                transaction_id="txn-view-1",
                                transaction_kind="money_gift",
                                sender_user_id="u_police",
                                recipient_user_id="u_mob",
                                created_at_epoch_seconds=222,
                                money_amount=50,
                            )
                        ],
                        inspector_record_inspection_used=True,
                        inspector_record_visible_until_epoch_seconds=310,
                        inspector_record_target_user_id="u_mob",
                        inspector_last_viewed_role_name="Mob Boss",
                        smuggler_smuggle_used=True,
                        gun_runner_charisma_used=True,
                        gun_runner_charisma_expires_at_epoch_seconds=333,
                        supplier_acquire_used=True,
                        supplier_acquire_target_user_id="u_mob",
                        police_officer_confiscation_used=True,
                        police_officer_confiscation_pending=False,
                        cop_last_three_protection_used=True,
                        enforcer_first_kill_bonus_used=True,
                        merchant_wholesale_order_used=True,
                    ),
                ),
                base_snapshot.participants[1],
            ],
            ledger=LedgerStateSnapshot(
                circulating_currency_baseline=600,
                checksum="abc123",
                entries=[
                    LedgerEntrySnapshot(
                        entry_id="led-1",
                        entry_kind="money_gift",
                        amount=50,
                        from_holder_id="u_police",
                        to_holder_id="u_mob",
                        created_at_epoch_seconds=222,
                        note="Accepted money gift offer.",
                    )
                ],
            ),
            player_transactions=[
                PlayerTransactionSnapshot(
                    transaction_id="txn-1",
                    transaction_kind="money_gift",
                    sender_user_id="u_police",
                    recipient_user_id="u_mob",
                    created_at_epoch_seconds=222,
                    money_amount=50,
                )
            ],
            felon_escape_user_id="u_mob",
            felon_escape_expires_at_epoch_seconds=555,
        )

        try:
            repository.save_game_session(expected)
            actual = repository.get_game_session(expected.game_id)
        finally:
            repository.close()

        self.assertEqual(actual, expected)

        if db_path.exists():
            db_path.unlink()

    def test_saved_session_persists_across_repository_instances(self) -> None:
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        db_path = TMP_ROOT / "gameplay_persist.sqlite3"
        if db_path.exists():
            db_path.unlink()

        base = _snapshot(game_id="r-9-g1-abc12345")

        repository_1 = SqliteGameplayRepository(db_path=str(db_path))
        try:
            repository_1.save_game_session(base)
        finally:
            repository_1.close()

        repository_2 = SqliteGameplayRepository(db_path=str(db_path))
        try:
            loaded = repository_2.get_game_session(base.game_id)
            self.assertIsNotNone(loaded)
            updated = replace(
                loaded,
                version=2,
                phase="boundary_resolution",
                pending_trial=TrialStateSnapshot(
                    murdered_user_id="u_mob",
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
            repository_2.save_game_session(updated)
        finally:
            repository_2.close()

        repository_3 = SqliteGameplayRepository(db_path=str(db_path))
        try:
            reloaded = repository_3.get_game_session(base.game_id)
        finally:
            repository_3.close()

        self.assertEqual(reloaded, updated)

        if db_path.exists():
            db_path.unlink()


if __name__ == "__main__":
    unittest.main()
