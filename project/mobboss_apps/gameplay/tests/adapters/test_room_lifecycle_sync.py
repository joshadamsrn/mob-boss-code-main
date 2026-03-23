import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.gameplay.adapters.outbound.room_lifecycle_impl import (  # noqa: E402
    RoomsLifecycleSyncOutboundPortImpl,
)
from project.mobboss_apps.rooms.adapters.outbound.memory_impl import (  # noqa: E402
    MemoryRoomsOutboundPortImpl,
)
from project.mobboss_apps.rooms.ports.internal import (  # noqa: E402
    CreateRoomCommand,
    JoinRoomCommand,
    LaunchGameFromRoomCommand,
)
from project.mobboss_apps.rooms.src.room_service import RoomsService  # noqa: E402


class RoomLifecycleSyncAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rooms_repo = MemoryRoomsOutboundPortImpl()
        self.rooms_service = RoomsService(repository=self.rooms_repo, minimum_launch_players=1)

    def test_mark_room_ended_for_game_ends_only_matching_linked_room(self) -> None:
        room = self.rooms_service.create_room(
            CreateRoomCommand(name="Lifecycle Room", creator_user_id="u_mod", creator_username="mod")
        )
        self.rooms_service.join_room(JoinRoomCommand(room_id=room.room_id, user_id="u_1", username="p1"))
        game_id = self.rooms_service.launch_game_from_room(
            LaunchGameFromRoomCommand(room_id=room.room_id, requested_by_user_id="u_mod")
        )

        adapter = RoomsLifecycleSyncOutboundPortImpl(rooms_repository=self.rooms_repo)
        adapter.mark_room_ended_for_game(room_id=room.room_id, game_id=f"{game_id}-wrong")
        unchanged = self.rooms_repo.get_room(room.room_id)
        assert unchanged is not None
        self.assertEqual(unchanged.status, "in_progress")
        self.assertEqual(unchanged.launched_game_id, game_id)

        adapter.mark_room_ended_for_game(room_id=room.room_id, game_id=game_id)
        updated = self.rooms_repo.get_room(room.room_id)
        assert updated is not None
        self.assertEqual(updated.status, "ended")
        self.assertIsNone(updated.launched_game_id)


if __name__ == "__main__":
    unittest.main()
