from __future__ import annotations

import json
import time
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from project.mobboss_apps.gameplay.ports.internal import (
    BuyFromSupplyCommand,
    GiveMoneyCommand,
    AllowTrialVotingCommand,
    AdvanceAccusedSelectionTimeoutCommand,
    MarkModeratorChatReadCommand,
    ModeratorAddFundsCommand,
    ModeratorTransferFundsCommand,
    ModeratorTransferInventoryItemCommand,
    ReportDeathCommand,
    OfferGiftItemCommand,
    RespondGiftOfferCommand,
    RespondMoneyGiftOfferCommand,
    RespondSaleOfferCommand,
    SendModeratorChatMessageCommand,
    SellInventoryItemCommand,
    SellInventoryToSupplyCommand,
    SetInventoryResalePriceCommand,
    SubmitAccusedSelectionCommand,
    SubmitTrialVoteCommand,
)
from project.mobboss_apps.gameplay.chat_projection import build_moderator_chat_view
from project.mobboss_apps.gameplay.ports.internal_requests_dto import (
    BuyFromSupplyRequestDTO,
    GiveMoneyRequestDTO,
    AllowTrialVotingRequestDTO,
    AdvanceAccusedSelectionTimeoutRequestDTO,
    GameIdRequestDTO,
    MarkModeratorChatReadRequestDTO,
    ModeratorAddFundsRequestDTO,
    ModeratorTransferFundsRequestDTO,
    ModeratorTransferInventoryItemRequestDTO,
    ReportDeathRequestDTO,
    OfferGiftItemRequestDTO,
    RespondGiftOfferRequestDTO,
    RespondMoneyGiftOfferRequestDTO,
    RespondSaleOfferRequestDTO,
    SendModeratorChatMessageRequestDTO,
    SellInventoryItemRequestDTO,
    SellInventoryToSupplyRequestDTO,
    SetInventoryResalePriceRequestDTO,
    StatusIndexRequestDTO,
    SubmitAccusedSelectionRequestDTO,
    SubmitTrialVoteRequestDTO,
)
from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.mobboss.devtools import user_dev_mode_enabled
from project.mobboss_apps.mobboss.decorators import problem_details
from project.mobboss_apps.mobboss.exceptions import UnauthorizedProblem
from project.mobboss_apps.mobboss.src.starting_money import getStartingMoney

MERCHANT_GOAL_ADDITIONAL_PERCENT = 0.40
NOTIFICATION_TTL_SECONDS = 120


def _default_inventory_item_image_path(classification: str) -> str:
    if classification == "gun_tier_1":
        return "/static/items/defaults/default_gun_tier_1.jpg"
    if classification == "gun_tier_2":
        return "/static/items/defaults/default_gun_tier_2.jpg"
    if classification == "gun_tier_3":
        return "/static/items/defaults/default_gun_tier_3.jpg"
    if classification == "knife":
        return "/static/items/defaults/default_knife.jpg"
    if classification == "bulletproof_vest":
        return "/static/items/defaults/default_bulletproof_vest.png"
    if classification == "escape_from_jail":
        return "/static/items/defaults/default_escape_from_jail.jpg"
    return ""


def _normalized_inventory_item_image_path(*, classification: str, image_path: str) -> str:
    normalized_image_path = image_path.strip()
    fallback_path = _default_inventory_item_image_path(classification)
    if not fallback_path:
        return normalized_image_path
    if not normalized_image_path:
        return fallback_path
    legacy_default_prefix = f"/static/items/defaults/default_{classification}."
    if normalized_image_path.startswith(legacy_default_prefix):
        return fallback_path
    return normalized_image_path


def _display_name_for_user(participant_name_by_id: dict[str, str], user_id: str | None, *, unknown: str = "Unknown Player") -> str | None:
    if not user_id:
        return None
    name = str(participant_name_by_id.get(user_id, "")).strip()
    return name or unknown


def _parse_bool_flag(value: object) -> bool:
    return str(value if value is not None else "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_v1_action_user_id(
    request: HttpRequest,
    *,
    snapshot,
    container,
    actor_user_id: str,
    payload: dict[str, Any],
) -> str:
    if snapshot.moderator_user_id != actor_user_id:
        return actor_user_id
    if not user_dev_mode_enabled(user=request.user, room_dev_mode=getattr(container, "room_dev_mode", False)):
        return actor_user_id
    if not _parse_bool_flag(payload.get("simulate_actions", request.GET.get("simulate_actions", ""))):
        return actor_user_id

    requested_user_id = str(payload.get("as_user_id", request.GET.get("as_user_id", ""))).strip()
    if not requested_user_id:
        return actor_user_id
    allowed_user_ids = {participant.user_id for participant in snapshot.participants}
    if requested_user_id in allowed_user_ids:
        return requested_user_id
    return actor_user_id


@problem_details
def index(request: HttpRequest) -> JsonResponse:
    StatusIndexRequestDTO.from_payload({"method": request.method})
    _container = get_container()
    return JsonResponse({"status": "ok"})


def _to_participant_dict(
    participant,
    *,
    include_role_details: bool,
    status_label: str,
    snapshot,
    participant_name_by_id: dict[str, str],
    player_count: int,
) -> dict:
    data = {
        "user_id": participant.user_id,
        "username": participant.username,
        "life_state": participant.life_state,
        "status_label": status_label,
    }
    if include_role_details:
        goal_bonus = int(snapshot.ledger.circulating_currency_baseline * MERCHANT_GOAL_ADDITIONAL_PERCENT)
        data["faction"] = participant.faction
        data["role_name"] = participant.role_name
        data["rank"] = participant.rank
        data["money_balance"] = participant.money_balance
        data["is_juror"] = _is_trial_juror(snapshot, participant.user_id)
        data["murdered_by_username"] = _display_name_for_user(participant_name_by_id, participant.murdered_by_user_id)
        data["accused_by_username"] = _display_name_for_user(participant_name_by_id, participant.accused_by_user_id)
        data["convicted_by_usernames"] = [
            _display_name_for_user(participant_name_by_id, user_id) for user_id in participant.convicted_by_user_ids
        ]
        if participant.faction == "Merchant":
            data["money_goal"] = getStartingMoney(player_count, participant.role_name) + goal_bonus
        data["inventory"] = [
            {
                "item_id": inventory_item.item_id,
                "classification": inventory_item.classification,
                "display_name": inventory_item.display_name,
                "image_path": _normalized_inventory_item_image_path(
                    classification=inventory_item.classification,
                    image_path=inventory_item.image_path,
                ),
                "acquisition_value": inventory_item.acquisition_value,
                "resale_price": inventory_item.resale_price,
            }
            for inventory_item in participant.inventory
        ]
    return data


def _to_game_view_dict(snapshot, *, viewer_user_id: str, is_moderator: bool) -> dict:
    # Invariant: role leakage is prevented at projection time. Non-moderator viewers
    # only receive role/faction/rank fields for self until the game has ended.
    now_epoch_seconds = int(time.time())
    min_created_at_epoch_seconds = now_epoch_seconds - NOTIFICATION_TTL_SECONDS
    participants: list[dict] = []
    participant_name_by_id = {participant.user_id: participant.username for participant in snapshot.participants}
    player_count = max(7, min(len(snapshot.participants), 25))
    reveal_all_roles = snapshot.status == "ended"
    ghost_view_enabled = _viewer_has_ghost_view(snapshot, viewer_user_id)
    can_view_police_mob_kill_tracker = is_moderator or ghost_view_enabled
    pending_trial = snapshot.pending_trial
    jury_vote_open = (
        pending_trial is not None
        and snapshot.phase == "trial_voting"
        and pending_trial.vote_deadline_epoch_seconds is not None
    )
    viewer_has_jury_vote = (
        pending_trial is not None
        and any(
            vote.get("user_id") == viewer_user_id and str(vote.get("vote_slot", "jury")) == "jury"
            for vote in pending_trial.votes
        )
    )
    viewer_has_tamper_vote = (
        pending_trial is not None
        and any(
            vote.get("user_id") == viewer_user_id and str(vote.get("vote_slot", "jury")) == "tamper"
            for vote in pending_trial.votes
        )
    )
    viewer_is_silenced = pending_trial is not None and viewer_user_id in pending_trial.silenced_user_ids
    for participant in snapshot.participants:
        include_role_details = is_moderator or ghost_view_enabled or reveal_all_roles or participant.user_id == viewer_user_id
        participants.append(
            _to_participant_dict(
                participant,
                include_role_details=include_role_details,
                status_label=_participant_status_label(snapshot, participant.user_id),
                snapshot=snapshot,
                participant_name_by_id=participant_name_by_id,
                player_count=player_count,
            )
        )

    payload = {
        "game_id": snapshot.game_id,
        "room_id": snapshot.room_id,
        "status": snapshot.status,
        "phase": snapshot.phase,
        "round_number": snapshot.round_number,
        "version": snapshot.version,
        "chat_version": snapshot.moderator_chat_version,
        "launched_at_epoch_seconds": snapshot.launched_at_epoch_seconds,
        "ended_at_epoch_seconds": snapshot.ended_at_epoch_seconds,
        "winning_faction": snapshot.winning_faction,
        "winning_user_id": snapshot.winning_user_id,
        "winning_username": _display_name_for_user(participant_name_by_id, snapshot.winning_user_id),
        "current_police_leader_user_id": snapshot.current_police_leader_user_id,
        "current_mob_leader_user_id": snapshot.current_mob_leader_user_id,
        "latest_public_notice": snapshot.latest_public_notice,
        "latest_private_notice": (
            snapshot.latest_private_notice_message
            if snapshot.latest_private_notice_user_id == viewer_user_id
            else None
        ),
        "viewer_notifications": [
            {
                "event_id": event.event_id,
                "message": event.message,
                "created_at_epoch_seconds": event.created_at_epoch_seconds,
            }
            for event in snapshot.notification_feed
            if event.user_id == viewer_user_id and event.created_at_epoch_seconds >= min_created_at_epoch_seconds
        ],
        "pending_gift_offers": [
            {
                "gift_offer_id": offer.gift_offer_id,
                "giver_user_id": offer.giver_user_id,
                "giver_username": _display_name_for_user(participant_name_by_id, offer.giver_user_id),
                "receiver_user_id": offer.receiver_user_id,
                "receiver_username": _display_name_for_user(participant_name_by_id, offer.receiver_user_id),
                "inventory_item_id": offer.inventory_item_id,
                "item_display_name": offer.item_display_name,
                "created_at_epoch_seconds": offer.created_at_epoch_seconds,
            }
            for offer in snapshot.pending_gift_offers
            if is_moderator or viewer_user_id in {offer.giver_user_id, offer.receiver_user_id}
        ],
        "pending_money_gift_offers": [
            {
                "money_gift_offer_id": offer.money_gift_offer_id,
                "giver_user_id": offer.giver_user_id,
                "giver_username": _display_name_for_user(participant_name_by_id, offer.giver_user_id),
                "receiver_user_id": offer.receiver_user_id,
                "receiver_username": _display_name_for_user(participant_name_by_id, offer.receiver_user_id),
                "amount": offer.amount,
                "created_at_epoch_seconds": offer.created_at_epoch_seconds,
            }
            for offer in snapshot.pending_money_gift_offers
            if is_moderator or viewer_user_id in {offer.giver_user_id, offer.receiver_user_id}
        ],
        "pending_sale_offers": [
            {
                "sale_offer_id": offer.sale_offer_id,
                "seller_user_id": offer.seller_user_id,
                "seller_username": _display_name_for_user(participant_name_by_id, offer.seller_user_id),
                "buyer_user_id": offer.buyer_user_id,
                "buyer_username": _display_name_for_user(participant_name_by_id, offer.buyer_user_id),
                "inventory_item_id": offer.inventory_item_id,
                "item_display_name": offer.item_display_name,
                "sale_price": offer.sale_price,
                "created_at_epoch_seconds": offer.created_at_epoch_seconds,
            }
            for offer in snapshot.pending_sale_offers
            if is_moderator or viewer_user_id in {offer.seller_user_id, offer.buyer_user_id}
        ],
        "participants": participants,
        "moderator_chat": build_moderator_chat_view(
            snapshot,
            viewer_user_id=viewer_user_id,
            is_moderator=is_moderator,
            participant_name_by_id=participant_name_by_id,
        ),
        "police_mob_kills_count": (
            snapshot.police_mob_kills_count if can_view_police_mob_kill_tracker else None
        ),
        "police_mob_kills_allowed": (
            snapshot.total_mob_participants_at_start // 2 if can_view_police_mob_kill_tracker else None
        ),
        "police_brutality_exceeded": (
            snapshot.police_mob_kills_count > (snapshot.total_mob_participants_at_start // 2)
            if can_view_police_mob_kill_tracker
            else None
        ),
        "protective_custody": _active_protective_custody_view(
            snapshot,
            viewer_user_id=viewer_user_id,
            is_moderator=is_moderator,
            participant_name_by_id=participant_name_by_id,
        ),
        "asset_freeze": _active_asset_freeze_view(
            snapshot,
            viewer_user_id=viewer_user_id,
            is_moderator=is_moderator,
            participant_name_by_id=participant_name_by_id,
        ),
        "sergeant_capture": _active_sergeant_capture_view(
            snapshot,
            viewer_user_id=viewer_user_id,
            is_moderator=is_moderator,
            participant_name_by_id=participant_name_by_id,
        ),
        "can_submit_accused_selection": (
            snapshot.status == "in_progress"
            and snapshot.phase == "accused_selection"
            and pending_trial is not None
            and bool(pending_trial.accused_selection_cursor)
            and pending_trial.accused_selection_cursor[0] == viewer_user_id
        ),
        "can_submit_jury_vote": (
            pending_trial is not None
            and snapshot.status == "in_progress"
            and snapshot.phase == "trial_voting"
            and viewer_user_id in pending_trial.jury_user_ids
            and jury_vote_open
            and not viewer_has_jury_vote
        ),
        "can_submit_tamper_vote": (
            pending_trial is not None
            and snapshot.status == "in_progress"
            and snapshot.phase == "trial_voting"
            and pending_trial.gangster_tamper_actor_user_id == viewer_user_id
            and pending_trial.gangster_tamper_target_user_id is not None
            and not viewer_has_tamper_vote
        ),
    }
    if is_moderator and pending_trial is not None:
        payload["pending_trial"] = {
            "murdered_user_id": pending_trial.murdered_user_id,
            "murderer_user_id": pending_trial.murderer_user_id,
            "accused_user_id": pending_trial.accused_user_id,
            "accused_selection_cursor": list(pending_trial.accused_selection_cursor),
            "accused_selection_deadline_epoch_seconds": pending_trial.accused_selection_deadline_epoch_seconds,
            "jury_user_ids": list(pending_trial.jury_user_ids),
            "vote_deadline_epoch_seconds": pending_trial.vote_deadline_epoch_seconds,
            "votes": list(pending_trial.votes),
            "verdict": pending_trial.verdict,
            "conviction_correct": pending_trial.conviction_correct,
            "resolution": pending_trial.resolution,
        }
    return payload


def _viewer_has_ghost_view(snapshot, viewer_user_id: str) -> bool:
    participant = next((candidate for candidate in snapshot.participants if candidate.user_id == viewer_user_id), None)
    if participant is None:
        return False
    if (
        snapshot.status == "in_progress"
        and participant.role_name == "Felon"
        and participant.life_state == "jailed"
        and snapshot.felon_escape_user_id == participant.user_id
        and snapshot.felon_escape_expires_at_epoch_seconds is not None
    ):
        return False
    return participant.life_state in {"dead", "jailed"}


def _participant_status_label(snapshot, user_id: str) -> str:
    participant = next(candidate for candidate in snapshot.participants if candidate.user_id == user_id)
    if (
        participant.life_state == "alive"
        and snapshot.phase == "trial_voting"
        and snapshot.pending_trial is not None
        and user_id in snapshot.pending_trial.silenced_user_ids
    ):
        return "silenced"
    if (
        participant.life_state == "alive"
        and snapshot.phase == "trial_voting"
        and snapshot.pending_trial is not None
        and snapshot.pending_trial.accused_user_id == participant.user_id
    ):
        return "on_trial"
    return participant.life_state


def _active_protective_custody_view(
    snapshot,
    *,
    viewer_user_id: str,
    is_moderator: bool,
    participant_name_by_id: dict[str, str],
) -> dict[str, object] | None:
    target_user_id = snapshot.protective_custody_user_id
    activated_by_user_id = snapshot.protective_custody_by_user_id
    expires_at_epoch_seconds = snapshot.protective_custody_expires_at_epoch_seconds
    if not target_user_id or expires_at_epoch_seconds is None:
        return None
    if int(time.time()) >= int(expires_at_epoch_seconds):
        return None
    target = next((participant for participant in snapshot.participants if participant.user_id == target_user_id), None)
    if target is None or target.life_state != "alive":
        return None
    if not is_moderator and viewer_user_id not in {target_user_id, activated_by_user_id}:
        return None
    return {
        "target_user_id": target_user_id,
        "target_username": _display_name_for_user(participant_name_by_id, target_user_id),
        "expires_at_epoch_seconds": int(expires_at_epoch_seconds),
    }


def _active_asset_freeze_view(
    snapshot,
    *,
    viewer_user_id: str,
    is_moderator: bool,
    participant_name_by_id: dict[str, str],
) -> dict[str, object] | None:
    target_user_id = snapshot.asset_freeze_user_id
    activated_by_user_id = snapshot.asset_freeze_by_user_id
    expires_at_epoch_seconds = snapshot.asset_freeze_expires_at_epoch_seconds
    if not target_user_id or expires_at_epoch_seconds is None:
        return None
    if int(time.time()) >= int(expires_at_epoch_seconds):
        return None
    target = next((participant for participant in snapshot.participants if participant.user_id == target_user_id), None)
    if target is None or target.life_state != "alive":
        return None
    if not is_moderator and viewer_user_id not in {target_user_id, activated_by_user_id}:
        return None
    return {
        "target_user_id": target_user_id,
        "target_username": _display_name_for_user(participant_name_by_id, target_user_id),
        "expires_at_epoch_seconds": int(expires_at_epoch_seconds),
    }


def _active_sergeant_capture_view(
    snapshot,
    *,
    viewer_user_id: str,
    is_moderator: bool,
    participant_name_by_id: dict[str, str],
) -> dict[str, object] | None:
    target_user_id = snapshot.sergeant_capture_user_id
    activated_by_user_id = snapshot.sergeant_capture_by_user_id
    expires_at_epoch_seconds = snapshot.sergeant_capture_expires_at_epoch_seconds
    if not target_user_id or expires_at_epoch_seconds is None:
        return None
    if int(time.time()) >= int(expires_at_epoch_seconds):
        return None
    target = next((participant for participant in snapshot.participants if participant.user_id == target_user_id), None)
    if target is None or target.life_state != "alive":
        return None
    if not is_moderator and viewer_user_id not in {target_user_id, activated_by_user_id}:
        return None
    return {
        "target_user_id": target_user_id,
        "target_username": _display_name_for_user(participant_name_by_id, target_user_id),
        "expires_at_epoch_seconds": int(expires_at_epoch_seconds),
    }


def _is_trial_juror(snapshot, user_id: str) -> bool:
    if snapshot.phase != "trial_voting" or snapshot.pending_trial is None:
        return False
    return user_id in snapshot.pending_trial.jury_user_ids


@method_decorator(problem_details, name="dispatch")
class BaseJsonView(View):
    @staticmethod
    def _ok(data: Any, status: int = 200) -> JsonResponse:
        return JsonResponse({"data": data, "error": None}, status=status)

    @staticmethod
    def _require_authenticated_user_id(request: HttpRequest) -> str:
        if not request.user.is_authenticated:
            raise UnauthorizedProblem()
        return str(request.user.id or request.user.username)

    @staticmethod
    def _load_json_body(request: HttpRequest) -> dict:
        if not request.body:
            return {}
        try:
            return json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON payload.") from exc


class GameDetailView(BaseJsonView):
    def get(self, request: HttpRequest, game_id: str) -> JsonResponse:
        viewer_user_id = self._require_authenticated_user_id(request)
        dto = GameIdRequestDTO.from_payload({"method": request.method, "game_id": game_id})
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        snapshot = gameplay_inbound.get_game_details(dto.game_id)

        is_moderator = snapshot.moderator_user_id == viewer_user_id
        requested_view_as_user_id = str(request.GET.get("as_user_id", "")).strip()
        view_as_user_id = viewer_user_id
        if is_moderator and user_dev_mode_enabled(user=request.user, room_dev_mode=getattr(container, "room_dev_mode", False)):
            allowed_view_ids = {participant.user_id for participant in snapshot.participants}
            if requested_view_as_user_id in allowed_view_ids:
                view_as_user_id = requested_view_as_user_id

        is_participant = any(participant.user_id == view_as_user_id for participant in snapshot.participants)
        if not is_moderator and not is_participant:
            raise PermissionError("Only moderator or joined participants can view this game.")

        viewer_is_moderator = snapshot.moderator_user_id == view_as_user_id
        return self._ok(_to_game_view_dict(snapshot, viewer_user_id=view_as_user_id, is_moderator=viewer_is_moderator))


class SendModeratorChatMessageView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        actor_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        snapshot = gameplay_inbound.get_game_details(game_id)
        sender_user_id = _resolve_v1_action_user_id(
            request,
            snapshot=snapshot,
            container=container,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        payload["sender_user_id"] = sender_user_id
        dto = SendModeratorChatMessageRequestDTO.from_payload(payload)
        is_moderator = sender_user_id == snapshot.moderator_user_id
        is_thread_player = any(
            participant.user_id == sender_user_id == dto.thread_user_id
            for participant in snapshot.participants
        )
        if not is_moderator and not is_thread_player:
            raise PermissionError("Players can only message the moderator in their own thread.")

        updated = gameplay_inbound.send_moderator_chat_message(
            SendModeratorChatMessageCommand(
                game_id=dto.game_id,
                sender_user_id=dto.sender_user_id,
                thread_user_id=dto.thread_user_id,
                message_text=dto.message_text,
                expected_version=dto.expected_version,
            )
        )
        return self._ok(
            _to_game_view_dict(updated, viewer_user_id=sender_user_id, is_moderator=is_moderator)
        )


class MarkModeratorChatReadView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        actor_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        snapshot = gameplay_inbound.get_game_details(game_id)
        viewer_user_id = _resolve_v1_action_user_id(
            request,
            snapshot=snapshot,
            container=container,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        payload["viewer_user_id"] = viewer_user_id
        dto = MarkModeratorChatReadRequestDTO.from_payload(payload)
        is_moderator = viewer_user_id == snapshot.moderator_user_id
        is_thread_player = any(
            participant.user_id == viewer_user_id == dto.thread_user_id
            for participant in snapshot.participants
        )
        if not is_moderator and not is_thread_player:
            raise PermissionError("Players can only access their own moderator chat thread.")

        updated = gameplay_inbound.mark_moderator_chat_read(
            MarkModeratorChatReadCommand(
                game_id=dto.game_id,
                viewer_user_id=dto.viewer_user_id,
                thread_user_id=dto.thread_user_id,
                expected_version=dto.expected_version,
            )
        )
        return self._ok(
            _to_game_view_dict(updated, viewer_user_id=viewer_user_id, is_moderator=is_moderator)
        )


class ReportDeathView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        reporter_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["reported_by_user_id"] = reporter_user_id
        dto = ReportDeathRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        snapshot = gameplay_inbound.get_game_details(dto.game_id)
        can_report = reporter_user_id == snapshot.moderator_user_id or reporter_user_id == dto.murdered_user_id
        if not can_report:
            raise PermissionError("Only moderator or the murdered player can report this death.")

        updated = gameplay_inbound.report_death(
            ReportDeathCommand(
                game_id=dto.game_id,
                murdered_user_id=dto.murdered_user_id,
                reported_by_user_id=dto.reported_by_user_id,
                expected_version=dto.expected_version,
                murderer_user_id=dto.murderer_user_id,
                attack_classification=dto.attack_classification,
            )
        )
        is_moderator = updated.moderator_user_id == reporter_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=reporter_user_id, is_moderator=is_moderator))


class AdvanceAccusedSelectionTimeoutView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        requester_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["requested_by_user_id"] = requester_user_id
        dto = AdvanceAccusedSelectionTimeoutRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.advance_accused_selection_timeout(
            AdvanceAccusedSelectionTimeoutCommand(
                game_id=dto.game_id,
                requested_by_user_id=dto.requested_by_user_id,
                expected_version=dto.expected_version,
            )
        )
        return self._ok(_to_game_view_dict(updated, viewer_user_id=requester_user_id, is_moderator=True))




class SubmitAccusedSelectionView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        selector_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["selected_by_user_id"] = selector_user_id
        dto = SubmitAccusedSelectionRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=dto.game_id,
                selected_by_user_id=dto.selected_by_user_id,
                accused_user_id=dto.accused_user_id,
                expected_version=dto.expected_version,
            )
        )
        is_moderator = updated.moderator_user_id == selector_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=selector_user_id, is_moderator=is_moderator))


class SubmitTrialVoteView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        voter_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["voter_user_id"] = voter_user_id
        dto = SubmitTrialVoteRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=dto.game_id,
                voter_user_id=dto.voter_user_id,
                vote=dto.vote,
                expected_version=dto.expected_version,
            )
        )
        is_moderator = updated.moderator_user_id == voter_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=voter_user_id, is_moderator=is_moderator))


class StartTrialVotingView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        requester_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["requested_by_user_id"] = requester_user_id
        dto = AllowTrialVotingRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=dto.game_id,
                requested_by_user_id=dto.requested_by_user_id,
                expected_version=dto.expected_version,
            )
        )
        return self._ok(_to_game_view_dict(updated, viewer_user_id=requester_user_id, is_moderator=True))


class BuyFromSupplyView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        buyer_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["buyer_user_id"] = buyer_user_id
        dto = BuyFromSupplyRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=dto.game_id,
                buyer_user_id=dto.buyer_user_id,
                classification=dto.classification,
                expected_version=dto.expected_version,
            )
        )
        is_moderator = updated.moderator_user_id == buyer_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=buyer_user_id, is_moderator=is_moderator))


class SetInventoryResalePriceView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        seller_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["seller_user_id"] = seller_user_id
        dto = SetInventoryResalePriceRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.set_inventory_resale_price(
            SetInventoryResalePriceCommand(
                game_id=dto.game_id,
                seller_user_id=dto.seller_user_id,
                inventory_item_id=dto.inventory_item_id,
                resale_price=dto.resale_price,
                expected_version=dto.expected_version,
            )
        )
        is_moderator = updated.moderator_user_id == seller_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=seller_user_id, is_moderator=is_moderator))


class SellInventoryItemView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        seller_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["seller_user_id"] = seller_user_id
        dto = SellInventoryItemRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.sell_inventory_item(
            SellInventoryItemCommand(
                game_id=dto.game_id,
                seller_user_id=dto.seller_user_id,
                buyer_user_id=dto.buyer_user_id,
                inventory_item_id=dto.inventory_item_id,
                expected_version=dto.expected_version,
            )
        )
        is_moderator = updated.moderator_user_id == seller_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=seller_user_id, is_moderator=is_moderator))


class SellInventoryToSupplyView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        seller_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["seller_user_id"] = seller_user_id
        dto = SellInventoryToSupplyRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.sell_inventory_to_supply(
            SellInventoryToSupplyCommand(
                game_id=dto.game_id,
                seller_user_id=dto.seller_user_id,
                inventory_item_id=dto.inventory_item_id,
                expected_version=dto.expected_version,
            )
        )
        is_moderator = updated.moderator_user_id == seller_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=seller_user_id, is_moderator=is_moderator))


class OfferGiftItemView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        giver_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["giver_user_id"] = giver_user_id
        dto = OfferGiftItemRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.offer_gift_item(
            OfferGiftItemCommand(
                game_id=dto.game_id,
                giver_user_id=dto.giver_user_id,
                receiver_user_id=dto.receiver_user_id,
                inventory_item_id=dto.inventory_item_id,
                expected_version=dto.expected_version,
            )
        )
        is_moderator = updated.moderator_user_id == giver_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=giver_user_id, is_moderator=is_moderator))


class GiveMoneyView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        giver_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["giver_user_id"] = giver_user_id
        dto = GiveMoneyRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.give_money(
            GiveMoneyCommand(
                game_id=dto.game_id,
                giver_user_id=dto.giver_user_id,
                receiver_user_id=dto.receiver_user_id,
                amount=dto.amount,
                expected_version=dto.expected_version,
            )
        )
        is_moderator = updated.moderator_user_id == giver_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=giver_user_id, is_moderator=is_moderator))


class ModeratorAddFundsView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        requester_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["requested_by_user_id"] = requester_user_id
        dto = ModeratorAddFundsRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.moderator_add_funds(
            ModeratorAddFundsCommand(
                game_id=dto.game_id,
                requested_by_user_id=dto.requested_by_user_id,
                recipient_user_id=dto.recipient_user_id,
                amount=dto.amount,
                expected_version=dto.expected_version,
            )
        )
        return self._ok(_to_game_view_dict(updated, viewer_user_id=requester_user_id, is_moderator=True))


class ModeratorTransferFundsView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        requester_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["requested_by_user_id"] = requester_user_id
        dto = ModeratorTransferFundsRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.moderator_transfer_funds(
            ModeratorTransferFundsCommand(
                game_id=dto.game_id,
                requested_by_user_id=dto.requested_by_user_id,
                from_user_id=dto.from_user_id,
                to_user_id=dto.to_user_id,
                amount=dto.amount,
                expected_version=dto.expected_version,
            )
        )
        return self._ok(_to_game_view_dict(updated, viewer_user_id=requester_user_id, is_moderator=True))


class ModeratorTransferInventoryItemView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        requester_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["requested_by_user_id"] = requester_user_id
        dto = ModeratorTransferInventoryItemRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.moderator_transfer_inventory_item(
            ModeratorTransferInventoryItemCommand(
                game_id=dto.game_id,
                requested_by_user_id=dto.requested_by_user_id,
                from_user_id=dto.from_user_id,
                to_user_id=dto.to_user_id,
                inventory_item_id=dto.inventory_item_id,
                expected_version=dto.expected_version,
            )
        )
        return self._ok(_to_game_view_dict(updated, viewer_user_id=requester_user_id, is_moderator=True))


class RespondMoneyGiftOfferView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        receiver_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["receiver_user_id"] = receiver_user_id
        dto = RespondMoneyGiftOfferRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.respond_money_gift_offer(
            RespondMoneyGiftOfferCommand(
                game_id=dto.game_id,
                receiver_user_id=dto.receiver_user_id,
                money_gift_offer_id=dto.money_gift_offer_id,
                accept=dto.accept,
                expected_version=dto.expected_version,
            )
        )
        is_moderator = updated.moderator_user_id == receiver_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=receiver_user_id, is_moderator=is_moderator))


class RespondGiftOfferView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        receiver_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["receiver_user_id"] = receiver_user_id
        dto = RespondGiftOfferRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.respond_gift_offer(
            RespondGiftOfferCommand(
                game_id=dto.game_id,
                receiver_user_id=dto.receiver_user_id,
                gift_offer_id=dto.gift_offer_id,
                accept=dto.accept,
                expected_version=dto.expected_version,
            )
        )
        is_moderator = updated.moderator_user_id == receiver_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=receiver_user_id, is_moderator=is_moderator))


class RespondSaleOfferView(BaseJsonView):
    def post(self, request: HttpRequest, game_id: str) -> JsonResponse:
        buyer_user_id = self._require_authenticated_user_id(request)
        payload = self._load_json_body(request)
        payload["method"] = request.method
        payload["game_id"] = game_id
        payload["buyer_user_id"] = buyer_user_id
        dto = RespondSaleOfferRequestDTO.from_payload(payload)

        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        updated = gameplay_inbound.respond_sale_offer(
            RespondSaleOfferCommand(
                game_id=dto.game_id,
                buyer_user_id=dto.buyer_user_id,
                sale_offer_id=dto.sale_offer_id,
                accept=dto.accept,
                expected_version=dto.expected_version,
            )
        )
        is_moderator = updated.moderator_user_id == buyer_user_id
        return self._ok(_to_game_view_dict(updated, viewer_user_id=buyer_user_id, is_moderator=is_moderator))
