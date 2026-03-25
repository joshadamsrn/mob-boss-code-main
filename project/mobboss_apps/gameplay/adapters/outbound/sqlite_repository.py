"""SQLite outbound adapter for gameplay sessions."""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from project.mobboss_apps.gameplay.adapters.outbound import sqlite_queries
from project.mobboss_apps.gameplay.ports.internal import (
    CatalogItemStateSnapshot,
    GiftOfferSnapshot,
    GameDetailsSnapshot,
    InventoryItemStateSnapshot,
    LedgerEntrySnapshot,
    LedgerStateSnapshot,
    MoneyGiftOfferSnapshot,
    NotificationEventSnapshot,
    ParticipantStateSnapshot,
    ParticipantPowerStateSnapshot,
    PlayerTransactionSnapshot,
    SaleOfferSnapshot,
    TrialStateSnapshot,
)
from project.mobboss_apps.gameplay.ports.outbound import GameplayOutboundPort


class SqliteGameplayRepository(GameplayOutboundPort):
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        sqlite_queries.ensure_schema(self._conn)

    def reserve_game_id(self, room_id: str) -> str:
        seq = sqlite_queries.reserve_game_sequence(self._conn, room_id)
        token = str(uuid4())[:8]
        return f"{room_id}-g{seq}-{token}"

    def save_game_session(self, snapshot: GameDetailsSnapshot) -> None:
        sqlite_queries.upsert_game_session(self._conn, _snapshot_to_record(snapshot))

    def get_game_session(self, game_id: str) -> GameDetailsSnapshot | None:
        record = sqlite_queries.get_game_session(self._conn, game_id)
        if record is None:
            return None
        return _record_to_snapshot(record)

    def close(self) -> None:
        self._conn.close()


def _snapshot_to_record(snapshot: GameDetailsSnapshot) -> dict[str, object]:
    payload = {
        "game_id": snapshot.game_id,
        "room_id": snapshot.room_id,
        "moderator_user_id": snapshot.moderator_user_id,
        "status": snapshot.status,
        "phase": snapshot.phase,
        "round_number": snapshot.round_number,
        "version": snapshot.version,
        "launched_at_epoch_seconds": snapshot.launched_at_epoch_seconds,
        "ended_at_epoch_seconds": snapshot.ended_at_epoch_seconds,
        "last_progressed_at_epoch_seconds": snapshot.last_progressed_at_epoch_seconds,
        "current_police_leader_user_id": snapshot.current_police_leader_user_id,
        "current_mob_leader_user_id": snapshot.current_mob_leader_user_id,
        "winning_faction": snapshot.winning_faction,
        "winning_user_id": snapshot.winning_user_id,
        "latest_public_notice": snapshot.latest_public_notice,
        "latest_private_notice_user_id": snapshot.latest_private_notice_user_id,
        "latest_private_notice_message": snapshot.latest_private_notice_message,
        "notification_feed": [
            {
                "event_id": event.event_id,
                "user_id": event.user_id,
                "message": event.message,
                "created_at_epoch_seconds": event.created_at_epoch_seconds,
            }
            for event in snapshot.notification_feed
        ],
        "total_mob_participants_at_start": snapshot.total_mob_participants_at_start,
        "police_mob_kills_count": snapshot.police_mob_kills_count,
        "protective_custody_user_id": snapshot.protective_custody_user_id,
        "protective_custody_by_user_id": snapshot.protective_custody_by_user_id,
        "protective_custody_expires_at_epoch_seconds": snapshot.protective_custody_expires_at_epoch_seconds,
        "asset_freeze_user_id": snapshot.asset_freeze_user_id,
        "asset_freeze_by_user_id": snapshot.asset_freeze_by_user_id,
        "asset_freeze_expires_at_epoch_seconds": snapshot.asset_freeze_expires_at_epoch_seconds,
        "sergeant_capture_user_id": snapshot.sergeant_capture_user_id,
        "sergeant_capture_by_user_id": snapshot.sergeant_capture_by_user_id,
        "sergeant_capture_expires_at_epoch_seconds": snapshot.sergeant_capture_expires_at_epoch_seconds,
        "felon_escape_user_id": snapshot.felon_escape_user_id,
        "felon_escape_expires_at_epoch_seconds": snapshot.felon_escape_expires_at_epoch_seconds,
        "latest_jury_log_user_ids": list(snapshot.latest_jury_log_user_ids),
        "player_transactions": [
            {
                "transaction_id": transaction.transaction_id,
                "transaction_kind": transaction.transaction_kind,
                "sender_user_id": transaction.sender_user_id,
                "recipient_user_id": transaction.recipient_user_id,
                "created_at_epoch_seconds": transaction.created_at_epoch_seconds,
                "money_amount": transaction.money_amount,
                "item_name": transaction.item_name,
            }
            for transaction in snapshot.player_transactions
        ],
        "pending_gift_offers": [
            {
                "gift_offer_id": offer.gift_offer_id,
                "giver_user_id": offer.giver_user_id,
                "receiver_user_id": offer.receiver_user_id,
                "inventory_item_id": offer.inventory_item_id,
                "item_display_name": offer.item_display_name,
                "created_at_epoch_seconds": offer.created_at_epoch_seconds,
            }
            for offer in snapshot.pending_gift_offers
        ],
        "pending_money_gift_offers": [
            {
                "money_gift_offer_id": offer.money_gift_offer_id,
                "giver_user_id": offer.giver_user_id,
                "receiver_user_id": offer.receiver_user_id,
                "amount": offer.amount,
                "created_at_epoch_seconds": offer.created_at_epoch_seconds,
            }
            for offer in snapshot.pending_money_gift_offers
        ],
        "pending_sale_offers": [
            {
                "sale_offer_id": offer.sale_offer_id,
                "seller_user_id": offer.seller_user_id,
                "buyer_user_id": offer.buyer_user_id,
                "inventory_item_id": offer.inventory_item_id,
                "item_display_name": offer.item_display_name,
                "sale_price": offer.sale_price,
                "created_at_epoch_seconds": offer.created_at_epoch_seconds,
            }
            for offer in snapshot.pending_sale_offers
        ],
        "ledger": {
            "circulating_currency_baseline": snapshot.ledger.circulating_currency_baseline,
            "checksum": snapshot.ledger.checksum,
            "entries": [
                {
                    "entry_id": entry.entry_id,
                    "entry_kind": entry.entry_kind,
                    "amount": entry.amount,
                    "from_holder_id": entry.from_holder_id,
                    "to_holder_id": entry.to_holder_id,
                    "created_at_epoch_seconds": entry.created_at_epoch_seconds,
                    "note": entry.note,
                }
                for entry in snapshot.ledger.entries
            ],
        },
        "participants": [
            {
                "user_id": participant.user_id,
                "username": participant.username,
                "faction": participant.faction,
                "role_name": participant.role_name,
                "rank": participant.rank,
                "life_state": participant.life_state,
                "money_balance": participant.money_balance,
                "murdered_by_user_id": participant.murdered_by_user_id,
                "accused_by_user_id": participant.accused_by_user_id,
                "convicted_by_user_ids": list(participant.convicted_by_user_ids),
                "power_state": {
                    "don_silence_used": participant.power_state.don_silence_used,
                    "don_silence_target_user_id": participant.power_state.don_silence_target_user_id,
                    "underboss_jury_override_used": participant.power_state.underboss_jury_override_used,
                    "kingpin_reduced_trial_keys": list(participant.power_state.kingpin_reduced_trial_keys),
                    "street_thug_steal_used": participant.power_state.street_thug_steal_used,
                    "smuggler_smuggle_used": participant.power_state.smuggler_smuggle_used,
                    "gun_runner_charisma_used": participant.power_state.gun_runner_charisma_used,
                    "gun_runner_charisma_expires_at_epoch_seconds": participant.power_state.gun_runner_charisma_expires_at_epoch_seconds,
                    "supplier_acquire_used": participant.power_state.supplier_acquire_used,
                    "supplier_acquire_target_user_id": participant.power_state.supplier_acquire_target_user_id,
                    "deputy_protective_custody_used": participant.power_state.deputy_protective_custody_used,
                    "sheriff_jury_log_views_used": participant.power_state.sheriff_jury_log_views_used,
                    "sheriff_jury_log_visible_until_epoch_seconds": participant.power_state.sheriff_jury_log_visible_until_epoch_seconds,
                    "sheriff_last_viewed_jury_user_ids": list(participant.power_state.sheriff_last_viewed_jury_user_ids),
                    "captain_asset_freeze_used": participant.power_state.captain_asset_freeze_used,
                    "lieutenant_information_briefcase_used": participant.power_state.lieutenant_information_briefcase_used,
                    "lieutenant_briefcase_visible_until_epoch_seconds": participant.power_state.lieutenant_briefcase_visible_until_epoch_seconds,
                    "lieutenant_briefcase_alive_police_count": participant.power_state.lieutenant_briefcase_alive_police_count,
                    "lieutenant_briefcase_alive_mob_count": participant.power_state.lieutenant_briefcase_alive_mob_count,
                    "lieutenant_briefcase_alive_merchant_count": participant.power_state.lieutenant_briefcase_alive_merchant_count,
                    "sergeant_capture_used": participant.power_state.sergeant_capture_used,
                    "detective_investigation_used": participant.power_state.detective_investigation_used,
                    "detective_investigation_visible_until_epoch_seconds": (
                        participant.power_state.detective_investigation_visible_until_epoch_seconds
                    ),
                    "detective_investigation_target_user_id": participant.power_state.detective_investigation_target_user_id,
                    "detective_last_viewed_transaction_total": participant.power_state.detective_last_viewed_transaction_total,
                    "detective_last_viewed_transactions": [
                        {
                            "transaction_id": transaction.transaction_id,
                            "transaction_kind": transaction.transaction_kind,
                            "sender_user_id": transaction.sender_user_id,
                            "recipient_user_id": transaction.recipient_user_id,
                            "created_at_epoch_seconds": transaction.created_at_epoch_seconds,
                            "money_amount": transaction.money_amount,
                            "item_name": transaction.item_name,
                        }
                        for transaction in participant.power_state.detective_last_viewed_transactions
                    ],
                    "inspector_record_inspection_used": participant.power_state.inspector_record_inspection_used,
                    "inspector_record_visible_until_epoch_seconds": (
                        participant.power_state.inspector_record_visible_until_epoch_seconds
                    ),
                    "inspector_record_target_user_id": participant.power_state.inspector_record_target_user_id,
                    "inspector_last_viewed_role_name": participant.power_state.inspector_last_viewed_role_name,
                    "police_officer_confiscation_used": participant.power_state.police_officer_confiscation_used,
                    "police_officer_confiscation_pending": participant.power_state.police_officer_confiscation_pending,
                    "cop_last_three_protection_used": participant.power_state.cop_last_three_protection_used,
                    "enforcer_first_kill_bonus_used": participant.power_state.enforcer_first_kill_bonus_used,
                    "made_man_skip_middle_man_used": participant.power_state.made_man_skip_middle_man_used,
                    "merchant_wholesale_order_used": participant.power_state.merchant_wholesale_order_used,
                    "gangster_tamper_used": participant.power_state.gangster_tamper_used,
                },
                "inventory": [
                    {
                        "item_id": inventory_item.item_id,
                        "classification": inventory_item.classification,
                        "display_name": inventory_item.display_name,
                        "image_path": inventory_item.image_path,
                        "acquisition_value": inventory_item.acquisition_value,
                        "resale_price": inventory_item.resale_price,
                    }
                    for inventory_item in participant.inventory
                ],
            }
            for participant in snapshot.participants
        ],
        "catalog": [
            {
                "classification": item.classification,
                "display_name": item.display_name,
                "base_price": item.base_price,
                "image_path": item.image_path,
                "is_active": item.is_active,
            }
            for item in snapshot.catalog
        ],
        "pending_trial": (
            None
            if snapshot.pending_trial is None
            else {
                "murdered_user_id": snapshot.pending_trial.murdered_user_id,
                "murderer_user_id": snapshot.pending_trial.murderer_user_id,
                "accused_user_id": snapshot.pending_trial.accused_user_id,
                "accused_selection_cursor": list(snapshot.pending_trial.accused_selection_cursor),
                "accused_selection_deadline_epoch_seconds": snapshot.pending_trial.accused_selection_deadline_epoch_seconds,
                "jury_user_ids": list(snapshot.pending_trial.jury_user_ids),
                "vote_deadline_epoch_seconds": snapshot.pending_trial.vote_deadline_epoch_seconds,
                "votes": list(snapshot.pending_trial.votes),
                "verdict": snapshot.pending_trial.verdict,
                "conviction_correct": snapshot.pending_trial.conviction_correct,
                "resolution": snapshot.pending_trial.resolution,
                "accused_by_user_id": snapshot.pending_trial.accused_by_user_id,
                "silenced_user_ids": list(snapshot.pending_trial.silenced_user_ids),
                "gangster_tamper_target_user_id": snapshot.pending_trial.gangster_tamper_target_user_id,
                "gangster_tamper_actor_user_id": snapshot.pending_trial.gangster_tamper_actor_user_id,
                "gangster_tamper_vote_deadline_epoch_seconds": snapshot.pending_trial.gangster_tamper_vote_deadline_epoch_seconds,
            }
        ),
    }
    return {
        "game_id": snapshot.game_id,
        "room_id": snapshot.room_id,
        "status": snapshot.status,
        "phase": snapshot.phase,
        "version": snapshot.version,
        "payload_json": json.dumps(payload, sort_keys=True),
    }


def _record_to_snapshot(record: dict[str, object]) -> GameDetailsSnapshot:
    payload = json.loads(str(record["payload_json"]))
    ledger_payload = payload.get("ledger") or {}

    pending_trial_payload = payload.get("pending_trial")
    pending_trial = None
    if pending_trial_payload is not None:
        pending_trial = TrialStateSnapshot(
            murdered_user_id=str(pending_trial_payload["murdered_user_id"]),
            murderer_user_id=_as_optional_str(pending_trial_payload.get("murderer_user_id")),
            accused_user_id=_as_optional_str(pending_trial_payload.get("accused_user_id")),
            accused_selection_cursor=[str(user_id) for user_id in pending_trial_payload.get("accused_selection_cursor", [])],
            accused_selection_deadline_epoch_seconds=_as_optional_int(
                pending_trial_payload.get("accused_selection_deadline_epoch_seconds")
            ),
            jury_user_ids=[str(user_id) for user_id in pending_trial_payload.get("jury_user_ids", [])],
            vote_deadline_epoch_seconds=_as_optional_int(pending_trial_payload.get("vote_deadline_epoch_seconds")),
            votes=[dict(vote) for vote in pending_trial_payload.get("votes", [])],
            verdict=_as_optional_str(pending_trial_payload.get("verdict")),
            conviction_correct=_as_optional_bool(pending_trial_payload.get("conviction_correct")),
            resolution=_as_optional_str(pending_trial_payload.get("resolution")),
            accused_by_user_id=_as_optional_str(pending_trial_payload.get("accused_by_user_id")),
            silenced_user_ids=[str(user_id) for user_id in pending_trial_payload.get("silenced_user_ids", [])],
            gangster_tamper_target_user_id=_as_optional_str(pending_trial_payload.get("gangster_tamper_target_user_id")),
            gangster_tamper_actor_user_id=_as_optional_str(pending_trial_payload.get("gangster_tamper_actor_user_id")),
            gangster_tamper_vote_deadline_epoch_seconds=_as_optional_int(
                pending_trial_payload.get("gangster_tamper_vote_deadline_epoch_seconds")
            ),
        )

    return GameDetailsSnapshot(
        game_id=str(payload["game_id"]),
        room_id=str(payload["room_id"]),
        moderator_user_id=str(payload["moderator_user_id"]),
        status=str(payload["status"]),
        phase=str(payload["phase"]),
        round_number=int(payload["round_number"]),
        version=int(payload["version"]),
        launched_at_epoch_seconds=int(payload["launched_at_epoch_seconds"]),
        ended_at_epoch_seconds=_as_optional_int(payload.get("ended_at_epoch_seconds")),
        last_progressed_at_epoch_seconds=_as_optional_int(payload.get("last_progressed_at_epoch_seconds")),
        participants=[
            ParticipantStateSnapshot(
                user_id=str(participant["user_id"]),
                username=str(participant["username"]),
                faction=str(participant["faction"]),
                role_name=str(participant["role_name"]),
                rank=int(participant["rank"]),
                life_state=str(participant["life_state"]),
                money_balance=int(participant["money_balance"]),
                murdered_by_user_id=_as_optional_str(participant.get("murdered_by_user_id")),
                accused_by_user_id=_as_optional_str(participant.get("accused_by_user_id")),
                convicted_by_user_ids=[str(user_id) for user_id in participant.get("convicted_by_user_ids", [])],
                power_state=_to_power_state_snapshot(participant.get("power_state")),
                inventory=[
                    InventoryItemStateSnapshot(
                        item_id=str(inventory_item["item_id"]),
                        classification=str(inventory_item["classification"]),
                        display_name=str(inventory_item["display_name"]),
                        image_path=str(inventory_item["image_path"]),
                        acquisition_value=int(inventory_item["acquisition_value"]),
                        resale_price=int(inventory_item["resale_price"]),
                    )
                    for inventory_item in participant.get("inventory", [])
                ],
            )
            for participant in payload.get("participants", [])
        ],
        catalog=[
            CatalogItemStateSnapshot(
                classification=str(item["classification"]),
                display_name=str(item["display_name"]),
                base_price=int(item["base_price"]),
                image_path=str(item["image_path"]),
                is_active=bool(item["is_active"]),
            )
            for item in payload.get("catalog", [])
        ],
        pending_trial=pending_trial,
        ledger=LedgerStateSnapshot(
            circulating_currency_baseline=int(ledger_payload.get("circulating_currency_baseline", 0)),
            checksum=_as_optional_str(ledger_payload.get("checksum")),
            entries=[
                LedgerEntrySnapshot(
                    entry_id=str(entry["entry_id"]),
                    entry_kind=str(entry["entry_kind"]),
                    amount=int(entry["amount"]),
                    from_holder_id=str(entry["from_holder_id"]),
                    to_holder_id=str(entry["to_holder_id"]),
                    created_at_epoch_seconds=int(entry["created_at_epoch_seconds"]),
                    note=_as_optional_str(entry.get("note")),
                )
                for entry in ledger_payload.get("entries", [])
            ],
        ),
        player_transactions=[
            PlayerTransactionSnapshot(
                transaction_id=str(transaction["transaction_id"]),
                transaction_kind=str(transaction["transaction_kind"]),
                sender_user_id=str(transaction["sender_user_id"]),
                recipient_user_id=str(transaction["recipient_user_id"]),
                created_at_epoch_seconds=int(transaction["created_at_epoch_seconds"]),
                money_amount=int(transaction.get("money_amount", 0)),
                item_name=_as_optional_str(transaction.get("item_name")),
            )
            for transaction in payload.get("player_transactions", [])
        ],
        current_police_leader_user_id=_as_optional_str(payload.get("current_police_leader_user_id")),
        current_mob_leader_user_id=_as_optional_str(payload.get("current_mob_leader_user_id")),
        winning_faction=_as_optional_str(payload.get("winning_faction")),
        winning_user_id=_as_optional_str(payload.get("winning_user_id")),
        latest_public_notice=_as_optional_str(payload.get("latest_public_notice")),
        latest_private_notice_user_id=_as_optional_str(payload.get("latest_private_notice_user_id")),
        latest_private_notice_message=_as_optional_str(payload.get("latest_private_notice_message")),
        notification_feed=[
            NotificationEventSnapshot(
                event_id=str(event["event_id"]),
                user_id=str(event["user_id"]),
                message=str(event["message"]),
                created_at_epoch_seconds=int(event["created_at_epoch_seconds"]),
            )
            for event in payload.get("notification_feed", [])
        ],
        pending_gift_offers=[
            GiftOfferSnapshot(
                gift_offer_id=str(offer["gift_offer_id"]),
                giver_user_id=str(offer["giver_user_id"]),
                receiver_user_id=str(offer["receiver_user_id"]),
                inventory_item_id=str(offer["inventory_item_id"]),
                item_display_name=str(offer["item_display_name"]),
                created_at_epoch_seconds=int(offer["created_at_epoch_seconds"]),
            )
            for offer in payload.get("pending_gift_offers", [])
        ],
        pending_money_gift_offers=[
            MoneyGiftOfferSnapshot(
                money_gift_offer_id=str(offer["money_gift_offer_id"]),
                giver_user_id=str(offer["giver_user_id"]),
                receiver_user_id=str(offer["receiver_user_id"]),
                amount=int(offer["amount"]),
                created_at_epoch_seconds=int(offer["created_at_epoch_seconds"]),
            )
            for offer in payload.get("pending_money_gift_offers", [])
        ],
        pending_sale_offers=[
            SaleOfferSnapshot(
                sale_offer_id=str(offer["sale_offer_id"]),
                seller_user_id=str(offer["seller_user_id"]),
                buyer_user_id=str(offer["buyer_user_id"]),
                inventory_item_id=str(offer["inventory_item_id"]),
                item_display_name=str(offer["item_display_name"]),
                sale_price=int(offer["sale_price"]),
                created_at_epoch_seconds=int(offer["created_at_epoch_seconds"]),
            )
            for offer in payload.get("pending_sale_offers", [])
        ],
        total_mob_participants_at_start=int(payload.get("total_mob_participants_at_start", 0)),
        police_mob_kills_count=int(payload.get("police_mob_kills_count", 0)),
        protective_custody_user_id=_as_optional_str(payload.get("protective_custody_user_id")),
        protective_custody_by_user_id=_as_optional_str(payload.get("protective_custody_by_user_id")),
        protective_custody_expires_at_epoch_seconds=_as_optional_int(
            payload.get("protective_custody_expires_at_epoch_seconds")
        ),
        asset_freeze_user_id=_as_optional_str(payload.get("asset_freeze_user_id")),
        asset_freeze_by_user_id=_as_optional_str(payload.get("asset_freeze_by_user_id")),
        asset_freeze_expires_at_epoch_seconds=_as_optional_int(payload.get("asset_freeze_expires_at_epoch_seconds")),
        sergeant_capture_user_id=_as_optional_str(payload.get("sergeant_capture_user_id")),
        sergeant_capture_by_user_id=_as_optional_str(payload.get("sergeant_capture_by_user_id")),
        sergeant_capture_expires_at_epoch_seconds=_as_optional_int(payload.get("sergeant_capture_expires_at_epoch_seconds")),
        felon_escape_user_id=_as_optional_str(payload.get("felon_escape_user_id")),
        felon_escape_expires_at_epoch_seconds=_as_optional_int(payload.get("felon_escape_expires_at_epoch_seconds")),
        latest_jury_log_user_ids=[str(user_id) for user_id in payload.get("latest_jury_log_user_ids", [])],
    )


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _to_power_state_snapshot(payload: object) -> ParticipantPowerStateSnapshot:
    if not isinstance(payload, dict):
        return ParticipantPowerStateSnapshot()
    return ParticipantPowerStateSnapshot(
        don_silence_used=bool(payload.get("don_silence_used")),
        don_silence_target_user_id=_as_optional_str(payload.get("don_silence_target_user_id")),
        underboss_jury_override_used=bool(payload.get("underboss_jury_override_used")),
        kingpin_reduced_trial_keys=[str(value) for value in payload.get("kingpin_reduced_trial_keys", [])],
        street_thug_steal_used=bool(payload.get("street_thug_steal_used")),
        smuggler_smuggle_used=bool(payload.get("smuggler_smuggle_used")),
        gun_runner_charisma_used=bool(payload.get("gun_runner_charisma_used")),
        gun_runner_charisma_expires_at_epoch_seconds=_as_optional_int(
            payload.get("gun_runner_charisma_expires_at_epoch_seconds")
        ),
        supplier_acquire_used=bool(payload.get("supplier_acquire_used")),
        supplier_acquire_target_user_id=_as_optional_str(payload.get("supplier_acquire_target_user_id")),
        deputy_protective_custody_used=bool(payload.get("deputy_protective_custody_used")),
        sheriff_jury_log_views_used=int(payload.get("sheriff_jury_log_views_used", 0)),
        sheriff_jury_log_visible_until_epoch_seconds=_as_optional_int(
            payload.get("sheriff_jury_log_visible_until_epoch_seconds")
        ),
        sheriff_last_viewed_jury_user_ids=[str(value) for value in payload.get("sheriff_last_viewed_jury_user_ids", [])],
        captain_asset_freeze_used=bool(payload.get("captain_asset_freeze_used")),
        lieutenant_information_briefcase_used=bool(payload.get("lieutenant_information_briefcase_used")),
        lieutenant_briefcase_visible_until_epoch_seconds=_as_optional_int(
            payload.get("lieutenant_briefcase_visible_until_epoch_seconds")
        ),
        lieutenant_briefcase_alive_police_count=int(payload.get("lieutenant_briefcase_alive_police_count", 0)),
        lieutenant_briefcase_alive_mob_count=int(payload.get("lieutenant_briefcase_alive_mob_count", 0)),
        lieutenant_briefcase_alive_merchant_count=int(payload.get("lieutenant_briefcase_alive_merchant_count", 0)),
        sergeant_capture_used=bool(payload.get("sergeant_capture_used")),
        detective_investigation_used=bool(payload.get("detective_investigation_used")),
        detective_investigation_visible_until_epoch_seconds=_as_optional_int(
            payload.get("detective_investigation_visible_until_epoch_seconds")
        ),
        detective_investigation_target_user_id=_as_optional_str(payload.get("detective_investigation_target_user_id")),
        detective_last_viewed_transaction_total=int(payload.get("detective_last_viewed_transaction_total", 0)),
        detective_last_viewed_transactions=[
            PlayerTransactionSnapshot(
                transaction_id=str(transaction["transaction_id"]),
                transaction_kind=str(transaction["transaction_kind"]),
                sender_user_id=str(transaction["sender_user_id"]),
                recipient_user_id=str(transaction["recipient_user_id"]),
                created_at_epoch_seconds=int(transaction["created_at_epoch_seconds"]),
                money_amount=int(transaction.get("money_amount", 0)),
                item_name=_as_optional_str(transaction.get("item_name")),
            )
            for transaction in payload.get("detective_last_viewed_transactions", [])
        ],
        inspector_record_inspection_used=bool(payload.get("inspector_record_inspection_used")),
        inspector_record_visible_until_epoch_seconds=_as_optional_int(
            payload.get("inspector_record_visible_until_epoch_seconds")
        ),
        inspector_record_target_user_id=_as_optional_str(payload.get("inspector_record_target_user_id")),
        inspector_last_viewed_role_name=_as_optional_str(payload.get("inspector_last_viewed_role_name")),
        police_officer_confiscation_used=bool(payload.get("police_officer_confiscation_used")),
        police_officer_confiscation_pending=bool(payload.get("police_officer_confiscation_pending")),
        cop_last_three_protection_used=bool(payload.get("cop_last_three_protection_used")),
        enforcer_first_kill_bonus_used=bool(payload.get("enforcer_first_kill_bonus_used")),
        made_man_skip_middle_man_used=bool(payload.get("made_man_skip_middle_man_used")),
        merchant_wholesale_order_used=bool(payload.get("merchant_wholesale_order_used")),
        gangster_tamper_used=bool(payload.get("gangster_tamper_used")),
    )
