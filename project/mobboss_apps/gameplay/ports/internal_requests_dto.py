"""Request DTOs used by gameplay inbound adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class IndexRequestDTO:
    method: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "IndexRequestDTO":
        return cls(method=_parse_method(payload.get("method"), key="method"))


@dataclass(frozen=True)
class StatusIndexRequestDTO:
    method: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "StatusIndexRequestDTO":
        return cls(method=_parse_method(payload.get("method"), key="method"))


@dataclass(frozen=True)
class GameIdRequestDTO:
    method: str
    game_id: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "GameIdRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
        )


@dataclass(frozen=True)
class ReportDeathRequestDTO:
    method: str
    game_id: str
    murdered_user_id: str
    reported_by_user_id: str
    attack_classification: str
    expected_version: int
    murderer_user_id: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReportDeathRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            murdered_user_id=_require_non_empty(payload, "murdered_user_id"),
            reported_by_user_id=_require_non_empty(payload, "reported_by_user_id"),
            attack_classification=_parse_required_attack_classification(payload, "attack_classification"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
            murderer_user_id=_parse_optional_non_empty(payload, "murderer_user_id"),
        )


@dataclass(frozen=True)
class AdvanceAccusedSelectionTimeoutRequestDTO:
    method: str
    game_id: str
    requested_by_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AdvanceAccusedSelectionTimeoutRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            requested_by_user_id=_require_non_empty(payload, "requested_by_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class SubmitAccusedSelectionRequestDTO:
    method: str
    game_id: str
    selected_by_user_id: str
    accused_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SubmitAccusedSelectionRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            selected_by_user_id=_require_non_empty(payload, "selected_by_user_id"),
            accused_user_id=_require_non_empty(payload, "accused_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


def _require_non_empty(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"Field '{key}' must be non-empty.")
    return value


def _parse_int(raw: Any, *, key: str) -> int:
    if raw is None:
        raise ValueError(f"Field '{key}' must be an integer.")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field '{key}' must be an integer.") from exc


def _parse_method(raw: Any, *, key: str) -> str:
    value = str(raw if raw is not None else "").strip().upper()
    if value not in _ALLOWED_HTTP_METHODS:
        raise ValueError(f"Field '{key}' has unsupported HTTP method: {value!r}")
    return value


def _parse_optional_non_empty(payload: dict[str, Any], key: str) -> str | None:
    if key not in payload or payload.get(key) is None:
        return None
    value = str(payload.get(key, "")).strip()
    return value if value else None


def _parse_required_attack_classification(payload: dict[str, Any], key: str) -> str:
    value = _require_non_empty(payload, key)
    normalized = value.lower()
    if normalized not in {"knife", "gun_tier_1", "gun_tier_2", "gun_tier_3"}:
        raise ValueError(
            "Field 'attack_classification' must be one of: knife, gun_tier_1, gun_tier_2, gun_tier_3."
        )
    return normalized


@dataclass(frozen=True)
class AllowTrialVotingRequestDTO:
    method: str
    game_id: str
    requested_by_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AllowTrialVotingRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            requested_by_user_id=_require_non_empty(payload, "requested_by_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class SubmitTrialVoteRequestDTO:
    method: str
    game_id: str
    voter_user_id: str
    vote: str
    expected_version: int
    vote_slot: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SubmitTrialVoteRequestDTO":
        vote = _require_non_empty(payload, "vote").lower()
        if vote not in {"guilty", "innocent"}:
            raise ValueError("Field 'vote' must be either 'guilty' or 'innocent'.")
        vote_slot = str(payload.get("vote_slot", "jury")).strip().lower() or "jury"
        if vote_slot not in {"jury", "tamper"}:
            raise ValueError("Field 'vote_slot' must be either 'jury' or 'tamper'.")
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            voter_user_id=_require_non_empty(payload, "voter_user_id"),
            vote=vote,
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
            vote_slot=vote_slot,
        )


@dataclass(frozen=True)
class ActivateDonSilenceRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateDonSilenceRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateUnderBossJuryOverrideRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    removed_juror_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateUnderBossJuryOverrideRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            removed_juror_user_id=_require_non_empty(payload, "removed_juror_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateKingpinReduceClockRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateKingpinReduceClockRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateGangsterTamperRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateGangsterTamperRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateStreetThugStealRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateStreetThugStealRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateSmugglerSmuggleRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateSmugglerSmuggleRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateGunRunnerCharismaRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateGunRunnerCharismaRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateSupplierAcquireRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateSupplierAcquireRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateMerchantWholesaleOrderRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    classification: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateMerchantWholesaleOrderRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            classification=_require_non_empty(payload, "classification"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateDeputyProtectiveCustodyRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateDeputyProtectiveCustodyRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateSheriffViewJuryLogRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateSheriffViewJuryLogRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateCaptainAssetFreezeRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateCaptainAssetFreezeRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateLieutenantInformationBriefcaseRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateLieutenantInformationBriefcaseRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateSergeantCaptureRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateSergeantCaptureRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateDetectiveInvestigationRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateDetectiveInvestigationRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateInspectorRecordInspectionRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateInspectorRecordInspectionRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            target_user_id=_require_non_empty(payload, "target_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivatePoliceOfficerConfiscationRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivatePoliceOfficerConfiscationRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class ActivateMadeManSkipMiddleManRequestDTO:
    method: str
    game_id: str
    actor_user_id: str
    classification: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActivateMadeManSkipMiddleManRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            actor_user_id=_require_non_empty(payload, "actor_user_id"),
            classification=_require_non_empty(payload, "classification"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class BuyFromSupplyRequestDTO:
    method: str
    game_id: str
    buyer_user_id: str
    classification: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "BuyFromSupplyRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            buyer_user_id=_require_non_empty(payload, "buyer_user_id"),
            classification=_require_non_empty(payload, "classification"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class SetInventoryResalePriceRequestDTO:
    method: str
    game_id: str
    seller_user_id: str
    inventory_item_id: str
    resale_price: int
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SetInventoryResalePriceRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            seller_user_id=_require_non_empty(payload, "seller_user_id"),
            inventory_item_id=_require_non_empty(payload, "inventory_item_id"),
            resale_price=_parse_int(payload.get("resale_price"), key="resale_price"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class SellInventoryItemRequestDTO:
    method: str
    game_id: str
    seller_user_id: str
    buyer_user_id: str
    inventory_item_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SellInventoryItemRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            seller_user_id=_require_non_empty(payload, "seller_user_id"),
            buyer_user_id=_require_non_empty(payload, "buyer_user_id"),
            inventory_item_id=_require_non_empty(payload, "inventory_item_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class SellInventoryToSupplyRequestDTO:
    method: str
    game_id: str
    seller_user_id: str
    inventory_item_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SellInventoryToSupplyRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            seller_user_id=_require_non_empty(payload, "seller_user_id"),
            inventory_item_id=_require_non_empty(payload, "inventory_item_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class RespondSaleOfferRequestDTO:
    method: str
    game_id: str
    buyer_user_id: str
    sale_offer_id: str
    accept: bool
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RespondSaleOfferRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            buyer_user_id=_require_non_empty(payload, "buyer_user_id"),
            sale_offer_id=_require_non_empty(payload, "sale_offer_id"),
            accept=_parse_bool(payload.get("accept"), key="accept"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class OfferGiftItemRequestDTO:
    method: str
    game_id: str
    giver_user_id: str
    receiver_user_id: str
    inventory_item_id: str
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OfferGiftItemRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            giver_user_id=_require_non_empty(payload, "giver_user_id"),
            receiver_user_id=_require_non_empty(payload, "receiver_user_id"),
            inventory_item_id=_require_non_empty(payload, "inventory_item_id"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class RespondGiftOfferRequestDTO:
    method: str
    game_id: str
    receiver_user_id: str
    gift_offer_id: str
    accept: bool
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RespondGiftOfferRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            receiver_user_id=_require_non_empty(payload, "receiver_user_id"),
            gift_offer_id=_require_non_empty(payload, "gift_offer_id"),
            accept=_parse_bool(payload.get("accept"), key="accept"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class GiveMoneyRequestDTO:
    method: str
    game_id: str
    giver_user_id: str
    receiver_user_id: str
    amount: int
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "GiveMoneyRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            giver_user_id=_require_non_empty(payload, "giver_user_id"),
            receiver_user_id=_require_non_empty(payload, "receiver_user_id"),
            amount=_parse_int(payload.get("amount"), key="amount"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


@dataclass(frozen=True)
class RespondMoneyGiftOfferRequestDTO:
    method: str
    game_id: str
    receiver_user_id: str
    money_gift_offer_id: str
    accept: bool
    expected_version: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RespondMoneyGiftOfferRequestDTO":
        return cls(
            method=_parse_method(payload.get("method"), key="method"),
            game_id=_require_non_empty(payload, "game_id"),
            receiver_user_id=_require_non_empty(payload, "receiver_user_id"),
            money_gift_offer_id=_require_non_empty(payload, "money_gift_offer_id"),
            accept=_parse_bool(payload.get("accept"), key="accept"),
            expected_version=_parse_int(payload.get("expected_version"), key="expected_version"),
        )


def _parse_bool(raw: Any, *, key: str) -> bool:
    if isinstance(raw, bool):
        return raw
    value = str(raw if raw is not None else "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Field '{key}' must be a boolean.")
