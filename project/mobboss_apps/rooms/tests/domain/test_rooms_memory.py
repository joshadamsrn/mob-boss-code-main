import sys
import unittest
from dataclasses import dataclass, replace
import shutil
import time
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
TMP_ROOT = Path(__file__).resolve().parents[1] / "_tmp"
FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"

from project.mobboss_apps.rooms.adapters.outbound.memory_repository import (  # noqa: E402
    MemoryRoomsRepository,
)
from project.mobboss_apps.rooms.ports.internal import (  # noqa: E402
    AssignRoomRoleCommand,
    CreateRoomCommand,
    DeleteRoomCommand,
    DeactivateRoomItemCommand,
    JoinRoomCommand,
    LeaveRoomCommand,
    LaunchGameFromRoomCommand,
    MIN_REQUIRED_ROOM_ITEMS,
    REQUIRED_ROOM_ITEM_CLASSIFICATIONS,
    SetMobSecretWordCommand,
    SetMemberBalanceCommand,
    SetRoomReadinessCommand,
    ShuffleRoomRolesCommand,
    UpsertRoomItemCommand,
)
from project.mobboss_apps.rooms.src.room_service import (  # noqa: E402
    MAX_ROOM_PLAYERS,
    RoomsService,
    minimum_launch_starting_balance,
)


def _load_json_fixture(name: str) -> dict:
    return json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))


def _join_members_from_fixture(service: RoomsService, room_id: str, fixture_name: str) -> None:
    payload = _load_json_fixture(fixture_name)
    for member in payload.get("members", []):
        service.join_room(
            JoinRoomCommand(
                room_id=room_id,
                user_id=str(member["user_id"]),
                username=str(member["username"]),
            )
        )


@dataclass
class _StartedGame:
    game_id: str


@dataclass
class _GameDetails:
    status: str


class _StubGameplayInboundPort:
    def __init__(self, game_id: str = "game-1") -> None:
        self.game_id = game_id
        self.commands = []

    def start_session_from_room(self, command):
        self.commands.append(command)
        return _StartedGame(game_id=self.game_id)

    def get_game_details(self, game_id: str):
        return _GameDetails(status="in_progress")


class RoomMemoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = MemoryRoomsRepository()
        self.service = RoomsService(self.repo)
        room = self.service.create_room(CreateRoomCommand(name="Test Room", creator_user_id="u_mod", creator_username="mod"))
        self.room_id = room.room_id

    def test_minimum_launch_starting_balance_is_seven_player_baseline(self) -> None:
        self.assertEqual(minimum_launch_starting_balance(), 730)

    def test_creator_becomes_moderator_and_joined_member(self) -> None:
        details = self.service.get_room_details(self.room_id)

        self.assertEqual(details.moderator_user_id, "u_mod")
        self.assertEqual(len(details.members), 1)
        self.assertEqual(details.members[0].membership_status, "joined")
        self.assertIsNone(details.members[0].assigned_role)
        self.assertEqual(len(details.items), MIN_REQUIRED_ROOM_ITEMS)
        required = {item.classification for item in details.items if item.classification in REQUIRED_ROOM_ITEM_CLASSIFICATIONS}
        self.assertEqual(required, set(REQUIRED_ROOM_ITEM_CLASSIFICATIONS))

    def test_roles_auto_assign_as_members_join(self) -> None:
        _join_members_from_fixture(self.service, self.room_id, "join_members_1_to_7.json")

        details = self.service.get_room_details(self.room_id)
        joined = [m for m in details.members if m.membership_status == "joined"]
        participants = [m for m in joined if m.user_id != "u_mod"]
        moderator = next(m for m in joined if m.user_id == "u_mod")

        self.assertEqual(len(joined), 8)
        self.assertEqual(len(participants), 7)
        self.assertIsNone(moderator.assigned_role)
        self.assertTrue(all(member.assigned_role is not None for member in participants))

        factions = [m.assigned_role.faction for m in participants if m.assigned_role is not None]
        self.assertEqual(factions.count("Police"), 3)
        self.assertEqual(factions.count("Mob"), 3)
        self.assertEqual(factions.count("Merchant"), 1)

    def test_required_role_titles_are_always_present_for_seven_player_game(self) -> None:
        _join_members_from_fixture(self.service, self.room_id, "join_members_1_to_7.json")

        details = self.service.get_room_details(self.room_id)
        role_names = {
            member.assigned_role.role_name
            for member in details.members
            if member.membership_status == "joined" and member.assigned_role is not None
        }
        self.assertIn("Chief of Police", role_names)
        self.assertIn("Mob Boss", role_names)
        self.assertIn("Knife Hobo", role_names)
        self.assertIn("Merchant", role_names)

    def test_only_moderator_can_assign_role(self) -> None:
        self.service.join_room(JoinRoomCommand(room_id=self.room_id, user_id="u_1", username="p1"))

        with self.assertRaises(PermissionError):
            self.service.assign_room_role(
                AssignRoomRoleCommand(
                    room_id=self.room_id,
                    moderator_user_id="u_1",
                    target_user_id="u_1",
                    faction="Police",
                    role_name="Deputy",
                    rank=2,
                )
            )

        with self.assertRaises(ValueError):
            self.service.assign_room_role(
                AssignRoomRoleCommand(
                    room_id=self.room_id,
                    moderator_user_id="u_mod",
                    target_user_id="u_mod",
                    faction="Police",
                    role_name="Chief of Police",
                    rank=1,
                )
            )

        details = self.service.assign_room_role(
            AssignRoomRoleCommand(
                room_id=self.room_id,
                moderator_user_id="u_mod",
                target_user_id="u_1",
                faction="Police",
                role_name="Deputy",
                rank=2,
            )
        )
        member = next(m for m in details.members if m.user_id == "u_1")
        assert member.assigned_role is not None
        self.assertEqual(member.assigned_role.role_name, "Deputy")

    def test_moderator_sets_member_balance_with_nearest_ten_rounding(self) -> None:
        self.service.join_room(JoinRoomCommand(room_id=self.room_id, user_id="u_2", username="p2"))

        details = self.service.set_member_balance(
            SetMemberBalanceCommand(
                room_id=self.room_id,
                moderator_user_id="u_mod",
                target_user_id="u_2",
                starting_balance=125,
            )
        )
        member = next(m for m in details.members if m.user_id == "u_2")
        self.assertEqual(member.starting_balance, 130)

        with self.assertRaises(ValueError):
            self.service.set_member_balance(
                SetMemberBalanceCommand(
                    room_id=self.room_id,
                    moderator_user_id="u_mod",
                    target_user_id="u_mod",
                    starting_balance=200,
                )
            )

    def test_item_upsert_is_classification_locked(self) -> None:
        details = self.service.upsert_room_item(
            UpsertRoomItemCommand(
                room_id=self.room_id,
                moderator_user_id="u_mod",
                classification="knife",
                display_name="Knife",
                base_price=118,
            )
        )
        knife = next(i for i in details.items if i.classification == "knife")
        self.assertEqual(knife.base_price, 120)

        with self.assertRaises(ValueError):
            self.service.upsert_room_item(
                UpsertRoomItemCommand(
                    room_id=self.room_id,
                    moderator_user_id="u_mod",
                    classification="laser",
                    display_name="Laser",
                    base_price=500,
                )
            )

    def test_required_items_cannot_be_deactivated(self) -> None:
        with self.assertRaises(ValueError):
            self.service.deactivate_room_item(
                DeactivateRoomItemCommand(
                    room_id=self.room_id,
                    moderator_user_id="u_mod",
                    classification="knife",
                )
            )

    def test_moderator_can_create_and_update_catalog_item_image_and_price(self) -> None:
        details = self.service.upsert_room_item(
            UpsertRoomItemCommand(
                room_id=self.room_id,
                moderator_user_id="u_mod",
                classification="bulletproof_vest",
                display_name="Vest",
                base_price=451,
            )
        )
        item = next(i for i in details.items if i.classification == "bulletproof_vest")
        self.assertEqual(item.display_name, "Vest")
        self.assertEqual(item.base_price, 450)
        self.assertEqual(item.image_path, "/static/items/defaults/default_bulletproof_vest.png")
        self.assertTrue(item.is_active)

        details = self.service.upsert_room_item(
            UpsertRoomItemCommand(
                room_id=self.room_id,
                moderator_user_id="u_mod",
                classification="bulletproof_vest",
                display_name="Armor Vest",
                base_price=589,
                image_path="/media/games/g1/items/vest.jpg",
            )
        )
        item = next(i for i in details.items if i.classification == "bulletproof_vest")
        self.assertEqual(item.display_name, "Armor Vest")
        self.assertEqual(item.base_price, 590)
        self.assertEqual(item.image_path, "/media/games/g1/items/vest.jpg")

    def test_participant_cannot_manage_room_catalog(self) -> None:
        self.service.join_room(JoinRoomCommand(room_id=self.room_id, user_id="u_5", username="p5"))

        with self.assertRaises(PermissionError):
            self.service.upsert_room_item(
                UpsertRoomItemCommand(
                    room_id=self.room_id,
                    moderator_user_id="u_5",
                    classification="knife",
                    display_name="Knife",
                    base_price=100,
                )
            )

    def test_participant_can_set_own_readiness_only(self) -> None:
        self.service.join_room(JoinRoomCommand(room_id=self.room_id, user_id="u_3", username="p3"))
        self.service.join_room(JoinRoomCommand(room_id=self.room_id, user_id="u_4", username="p4"))

        details = self.service.set_room_readiness(
            SetRoomReadinessCommand(
                room_id=self.room_id,
                requested_by_user_id="u_3",
                user_id="u_3",
                is_ready=True,
            )
        )
        member_3 = next(m for m in details.members if m.user_id == "u_3")
        self.assertTrue(member_3.is_ready)

        with self.assertRaises(PermissionError):
            self.service.set_room_readiness(
                SetRoomReadinessCommand(
                    room_id=self.room_id,
                    requested_by_user_id="u_3",
                    user_id="u_4",
                    is_ready=True,
                )
            )

        details = self.service.set_room_readiness(
            SetRoomReadinessCommand(
                room_id=self.room_id,
                requested_by_user_id="u_mod",
                user_id="u_4",
                is_ready=True,
            )
        )
        member_4 = next(m for m in details.members if m.user_id == "u_4")
        self.assertTrue(member_4.is_ready)

        with self.assertRaises(ValueError):
            self.service.set_room_readiness(
                SetRoomReadinessCommand(
                    room_id=self.room_id,
                    requested_by_user_id="u_mod",
                    user_id="u_mod",
                    is_ready=False,
                )
            )

    def test_join_rejects_new_player_when_room_is_full(self) -> None:
        for idx in range(1, MAX_ROOM_PLAYERS + 1):
            self.service.join_room(
                JoinRoomCommand(
                    room_id=self.room_id,
                    user_id=f"u_{idx}",
                    username=f"p{idx}",
                )
            )

        with self.assertRaises(ValueError) as ctx:
            self.service.join_room(
                JoinRoomCommand(
                    room_id=self.room_id,
                    user_id="u_overflow",
                    username="overflow",
                )
            )

        self.assertEqual(str(ctx.exception), "Room is full.")
        details = self.service.get_room_details(self.room_id)
        joined_players = [
            member
            for member in details.members
            if member.membership_status == "joined" and member.user_id != details.moderator_user_id
        ]
        self.assertEqual(len(joined_players), MAX_ROOM_PLAYERS)

    def test_moderator_can_set_secret_mob_word(self) -> None:
        details = self.service.set_mob_secret_word(
            SetMobSecretWordCommand(
                room_id=self.room_id,
                moderator_user_id="u_mod",
                secret_mob_word="RAVEN",
            )
        )
        self.assertEqual(details.secret_mob_word, "RAVEN")

    def test_only_moderator_can_set_secret_mob_word(self) -> None:
        self.service.join_room(JoinRoomCommand(room_id=self.room_id, user_id="u_3", username="p3"))

        with self.assertRaises(PermissionError):
            self.service.set_mob_secret_word(
                SetMobSecretWordCommand(
                    room_id=self.room_id,
                    moderator_user_id="u_3",
                    secret_mob_word="OWL",
                )
            )

    def test_secret_mob_word_rejects_blank_values(self) -> None:
        with self.assertRaises(ValueError):
            self.service.set_mob_secret_word(
                SetMobSecretWordCommand(
                    room_id=self.room_id,
                    moderator_user_id="u_mod",
                    secret_mob_word="   ",
                )
            )

    def test_launch_requires_moderator_and_min_joined_members(self) -> None:
        _join_members_from_fixture(self.service, self.room_id, "join_members_1_to_6.json")

        with self.assertRaises(PermissionError):
            self.service.launch_game_from_room(
                LaunchGameFromRoomCommand(room_id=self.room_id, requested_by_user_id="u_1")
            )

        with self.assertRaises(ValueError):
            self.service.launch_game_from_room(
                LaunchGameFromRoomCommand(room_id=self.room_id, requested_by_user_id="u_mod")
            )

        self.service.join_room(JoinRoomCommand(room_id=self.room_id, user_id="u_7", username="p7"))
        game_id = self.service.launch_game_from_room(
            LaunchGameFromRoomCommand(room_id=self.room_id, requested_by_user_id="u_mod")
        )
        self.assertTrue(game_id.startswith(self.room_id))
        self.assertEqual(self.service.get_room_details(self.room_id).status, "in_progress")

    def test_launch_respects_custom_minimum_launch_players(self) -> None:
        repo = MemoryRoomsRepository()
        service = RoomsService(repo, minimum_launch_players=2)
        room = service.create_room(
            CreateRoomCommand(name="Dev Launch Room", creator_user_id="u_mod", creator_username="mod")
        )

        service.join_room(JoinRoomCommand(room_id=room.room_id, user_id="u_1", username="p1"))
        with self.assertRaises(ValueError):
            service.launch_game_from_room(
                LaunchGameFromRoomCommand(room_id=room.room_id, requested_by_user_id="u_mod")
            )

        service.join_room(JoinRoomCommand(room_id=room.room_id, user_id="u_2", username="p2"))
        game_id = service.launch_game_from_room(
            LaunchGameFromRoomCommand(room_id=room.room_id, requested_by_user_id="u_mod")
        )

        self.assertTrue(game_id.startswith(room.room_id))
        self.assertEqual(service.get_room_details(room.room_id).status, "in_progress")

    def test_launch_uses_gameplay_handoff_when_gameplay_service_is_configured(self) -> None:
        repo = MemoryRoomsRepository()
        gameplay = _StubGameplayInboundPort(game_id="game-r-1")
        service = RoomsService(repo, gameplay_inbound_port=gameplay)
        room = service.create_room(
            CreateRoomCommand(name="Handoff Room", creator_user_id="u_mod", creator_username="mod")
        )

        _join_members_from_fixture(service, room.room_id, "join_members_1_to_7.json")

        game_id = service.launch_game_from_room(
            LaunchGameFromRoomCommand(room_id=room.room_id, requested_by_user_id="u_mod")
        )

        self.assertEqual(game_id, "game-r-1")
        self.assertEqual(len(gameplay.commands), 1)
        start_command = gameplay.commands[0]
        self.assertEqual(start_command.room_id, room.room_id)
        self.assertEqual(start_command.moderator_user_id, "u_mod")
        self.assertEqual(len(start_command.participants), 7)
        self.assertGreaterEqual(len(start_command.catalog), MIN_REQUIRED_ROOM_ITEMS)
        self.assertEqual(service.get_room_details(room.room_id).status, "in_progress")

    def test_launch_applies_player_count_pricing_and_preserves_manual_override(self) -> None:
        repo = MemoryRoomsRepository()
        gameplay = _StubGameplayInboundPort(game_id="game-r-price")
        service = RoomsService(repo, gameplay_inbound_port=gameplay)
        room = service.create_room(
            CreateRoomCommand(name="Pricing Room", creator_user_id="u_mod", creator_username="mod")
        )
        _join_members_from_fixture(service, room.room_id, "join_members_1_to_7.json")

        service.upsert_room_item(
            UpsertRoomItemCommand(
                room_id=room.room_id,
                moderator_user_id="u_mod",
                classification="gun_tier_1",
                display_name="Handgun (Tier 1)",
                base_price=999,
            )
        )
        service.upsert_room_item(
            UpsertRoomItemCommand(
                room_id=room.room_id,
                moderator_user_id="u_mod",
                classification="gun_tier_2",
                display_name="Pistol (Tier 2)",
                base_price=100,
            )
        )
        service.upsert_room_item(
            UpsertRoomItemCommand(
                room_id=room.room_id,
                moderator_user_id="u_mod",
                classification="gun_tier_3",
                display_name="Revolver (Tier 3)",
                base_price=100,
            )
        )
        service.upsert_room_item(
            UpsertRoomItemCommand(
                room_id=room.room_id,
                moderator_user_id="u_mod",
                classification="bulletproof_vest",
                display_name="Bulletproof Vest",
                base_price=100,
            )
        )
        service.upsert_room_item(
            UpsertRoomItemCommand(
                room_id=room.room_id,
                moderator_user_id="u_mod",
                classification="escape_from_jail",
                display_name="Escape From Jail",
                base_price=100,
            )
        )
        service.upsert_room_item(
            UpsertRoomItemCommand(
                room_id=room.room_id,
                moderator_user_id="u_mod",
                classification="knife_1",
                display_name="Knife 1",
                base_price=100,
            )
        )

        service.launch_game_from_room(
            LaunchGameFromRoomCommand(room_id=room.room_id, requested_by_user_id="u_mod")
        )
        start_command = gameplay.commands[0]
        price_by_classification = {item.classification: item.base_price for item in start_command.catalog}

        self.assertEqual(price_by_classification["gun_tier_1"], 1000)
        self.assertEqual(price_by_classification["gun_tier_2"], 20)
        self.assertEqual(price_by_classification["gun_tier_3"], 50)
        self.assertEqual(price_by_classification["bulletproof_vest"], 40)
        self.assertEqual(price_by_classification["escape_from_jail"], 40)
        self.assertEqual(price_by_classification["knife_1"], 80)

    def test_only_moderator_can_delete_room(self) -> None:
        self.service.join_room(JoinRoomCommand(room_id=self.room_id, user_id="u_6", username="p6"))

        with self.assertRaises(PermissionError):
            self.service.delete_room(
                DeleteRoomCommand(room_id=self.room_id, requested_by_user_id="u_6")
            )

        self.service.delete_room(DeleteRoomCommand(room_id=self.room_id, requested_by_user_id="u_mod"))
        with self.assertRaises(ValueError):
            self.service.get_room_details(self.room_id)

    def test_moderator_leave_closes_room(self) -> None:
        self.service.join_room(JoinRoomCommand(room_id=self.room_id, user_id="u_7", username="p7"))

        closed = self.service.leave_room(LeaveRoomCommand(room_id=self.room_id, user_id="u_mod"))

        self.assertEqual(closed.status, "ended")
        self.assertTrue(all(member.membership_status == "left" for member in closed.members))
        self.assertEqual(self.service.list_active_rooms(), [])

    def test_moderator_can_shuffle_role_assignments(self) -> None:
        _join_members_from_fixture(self.service, self.room_id, "join_members_1_to_7.json")

        before = self.service.get_room_details(self.room_id)
        before_map = {
            m.user_id: (m.assigned_role.faction, m.assigned_role.role_name, m.assigned_role.rank)
            for m in before.members
            if m.membership_status == "joined" and m.assigned_role is not None
        }

        after = self.service.shuffle_room_roles(
            ShuffleRoomRolesCommand(room_id=self.room_id, moderator_user_id="u_mod", seed=42)
        )
        after_map = {
            m.user_id: (m.assigned_role.faction, m.assigned_role.role_name, m.assigned_role.rank)
            for m in after.members
            if m.membership_status == "joined" and m.assigned_role is not None
        }

        self.assertEqual(sorted(before_map.values()), sorted(after_map.values()))
        self.assertNotEqual(before_map, after_map)

    def test_list_active_rooms_prunes_orphan_room_missing_joined_moderator(self) -> None:
        self.service.join_room(JoinRoomCommand(room_id=self.room_id, user_id="u_8", username="p8"))
        details = self.service.get_room_details(self.room_id)
        corrupted_members = [
            replace(member, membership_status="left", is_ready=False, assigned_role=None)
            if member.user_id == "u_mod"
            else member
            for member in details.members
        ]
        self.repo.save_room(replace(details, members=corrupted_members))

        listed = self.service.list_active_rooms()
        self.assertEqual(listed, [])

        closed = self.service.get_room_details(self.room_id)
        self.assertEqual(closed.status, "ended")
        self.assertTrue(all(member.membership_status == "left" for member in closed.members))

    def test_list_active_rooms_auto_closes_lobby_rooms_older_than_two_hours(self) -> None:
        details = self.service.get_room_details(self.room_id)
        stale = replace(details, opened_at_epoch_seconds=int(time.time()) - (2 * 60 * 60 + 1))
        self.repo.save_room(stale)

        listed = self.service.list_active_rooms()
        self.assertEqual(listed, [])

        closed = self.service.get_room_details(self.room_id)
        self.assertEqual(closed.status, "ended")
        self.assertTrue(all(member.membership_status == "left" for member in closed.members))

    def test_moderator_close_auto_cleans_room_media_directory(self) -> None:
        media_root = TMP_ROOT / "media_memory_cleanup"
        if media_root.exists():
            shutil.rmtree(media_root, ignore_errors=True)
        repo = MemoryRoomsRepository(room_media_root=media_root)
        service = RoomsService(repo)
        room_summary = service.create_room(CreateRoomCommand(name="Media Room", creator_user_id="u_mod", creator_username="mod"))
        room_media_dir = media_root / "rooms" / room_summary.room_id / "items"
        room_media_dir.mkdir(parents=True, exist_ok=True)
        (room_media_dir / "test.txt").write_text("x", encoding="utf-8")

        service.leave_room(LeaveRoomCommand(room_id=room_summary.room_id, user_id="u_mod"))
        self.assertFalse((media_root / "rooms" / room_summary.room_id).exists())

        shutil.rmtree(media_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
