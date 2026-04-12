from __future__ import annotations

from project.mobboss_apps.gameplay.ports.internal import GameDetailsSnapshot


def _display_name_for_user(
    participant_name_by_id: dict[str, str],
    user_id: str | None,
    *,
    unknown: str = "Unknown Player",
) -> str | None:
    if not user_id:
        return None
    name = str(participant_name_by_id.get(user_id, "")).strip()
    return name or unknown


def build_moderator_chat_view(
    snapshot: GameDetailsSnapshot,
    *,
    viewer_user_id: str,
    is_moderator: bool,
    participant_name_by_id: dict[str, str],
) -> dict[str, object]:
    visible_threads = list(snapshot.moderator_chat_threads)
    if not is_moderator:
        visible_threads = [
            thread for thread in visible_threads if thread.player_user_id == viewer_user_id
        ]

    thread_views: list[dict[str, object]] = []
    total_unread = 0
    for thread in visible_threads:
        viewer_unread_count = (
            thread.unread_for_moderator_count
            if is_moderator
            else thread.unread_for_player_count
        )
        total_unread += viewer_unread_count
        messages = [
            {
                "message_id": message.message_id,
                "sender_user_id": message.sender_user_id,
                "sender_label": (
                    "Moderator"
                    if message.sender_user_id == snapshot.moderator_user_id
                    else _display_name_for_user(participant_name_by_id, message.sender_user_id)
                ),
                "body": message.body,
                "created_at_epoch_seconds": message.created_at_epoch_seconds,
                "is_from_viewer": message.sender_user_id == viewer_user_id,
                "is_from_moderator": message.sender_user_id == snapshot.moderator_user_id,
            }
            for message in thread.messages
        ]
        latest_message = messages[-1] if messages else None
        thread_views.append(
            {
                "player_user_id": thread.player_user_id,
                "player_username": _display_name_for_user(participant_name_by_id, thread.player_user_id),
                "player_role_name": next(
                    (
                        participant.role_name
                        for participant in snapshot.participants
                        if participant.user_id == thread.player_user_id
                    ),
                    "",
                ),
                "player_life_state": next(
                    (
                        participant.life_state
                        for participant in snapshot.participants
                        if participant.user_id == thread.player_user_id
                    ),
                    "alive",
                ),
                "viewer_unread_count": viewer_unread_count,
                "latest_message_preview": "" if latest_message is None else str(latest_message["body"])[:80],
                "latest_message_at_epoch_seconds": (
                    None if latest_message is None else latest_message["created_at_epoch_seconds"]
                ),
                "messages": messages,
            }
        )

    return {
        "viewer_can_send": snapshot.status == "in_progress",
        "viewer_unread_count": total_unread,
        "threads": thread_views,
    }
