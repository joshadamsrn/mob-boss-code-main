from __future__ import annotations
from dataclasses import replace
from datetime import datetime
import re
import time
from urllib.parse import quote_plus

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static

from project.mobboss_apps.gameplay.adapters.internal.page_view_mapper import (
    build_gameplay_page_view,
    _participant_role_label,
)
from project.mobboss_apps.gameplay.ports.internal import (
    ActivateDetectiveInvestigationCommand,
    ActivateInspectorRecordInspectionCommand,
    ActivateGangsterTamperCommand,
    ActivateStreetThugStealCommand,
    ActivateSmugglerSmuggleCommand,
    ActivateGunRunnerCharismaCommand,
    ActivateSupplierAcquireCommand,
    ActivateMerchantWholesaleOrderCommand,
    ActivateMadeManSkipMiddleManCommand,
    ActivatePoliceOfficerConfiscationCommand,
    ActivateSergeantCaptureCommand,
    ActivateLieutenantInformationBriefcaseCommand,
    ActivateCaptainAssetFreezeCommand,
    ActivateSheriffViewJuryLogCommand,
    ActivateDeputyProtectiveCustodyCommand,
    ActivateDonSilenceCommand,
    ActivateKingpinReduceClockCommand,
    ActivateUnderBossJuryOverrideCommand,
    BuyFromSupplyCommand,
    GiveMoneyCommand,
    AllowTrialVotingCommand,
    AdvanceAccusedSelectionTimeoutCommand,
    ReportDeathCommand,
    OfferGiftItemCommand,
    RespondGiftOfferCommand,
    RespondMoneyGiftOfferCommand,
    RespondSaleOfferCommand,
    SellInventoryItemCommand,
    SellInventoryToSupplyCommand,
    SetInventoryResalePriceCommand,
    SubmitAccusedSelectionCommand,
    SubmitTrialVoteCommand,
)
from project.mobboss_apps.gameplay.ports.internal_requests_dto import (
    ActivateDetectiveInvestigationRequestDTO,
    ActivateInspectorRecordInspectionRequestDTO,
    ActivateGangsterTamperRequestDTO,
    ActivateStreetThugStealRequestDTO,
    ActivateSmugglerSmuggleRequestDTO,
    ActivateGunRunnerCharismaRequestDTO,
    ActivateSupplierAcquireRequestDTO,
    ActivateMerchantWholesaleOrderRequestDTO,
    ActivateMadeManSkipMiddleManRequestDTO,
    ActivatePoliceOfficerConfiscationRequestDTO,
    ActivateSergeantCaptureRequestDTO,
    ActivateLieutenantInformationBriefcaseRequestDTO,
    ActivateCaptainAssetFreezeRequestDTO,
    ActivateSheriffViewJuryLogRequestDTO,
    ActivateDeputyProtectiveCustodyRequestDTO,
    ActivateDonSilenceRequestDTO,
    ActivateKingpinReduceClockRequestDTO,
    ActivateUnderBossJuryOverrideRequestDTO,
    BuyFromSupplyRequestDTO,
    GiveMoneyRequestDTO,
    AllowTrialVotingRequestDTO,
    AdvanceAccusedSelectionTimeoutRequestDTO,
    GameIdRequestDTO,
    IndexRequestDTO,
    ReportDeathRequestDTO,
    OfferGiftItemRequestDTO,
    RespondGiftOfferRequestDTO,
    RespondMoneyGiftOfferRequestDTO,
    RespondSaleOfferRequestDTO,
    SellInventoryItemRequestDTO,
    SellInventoryToSupplyRequestDTO,
    SetInventoryResalePriceRequestDTO,
    SubmitAccusedSelectionRequestDTO,
    SubmitTrialVoteRequestDTO,
)
from project.mobboss_apps.mobboss.src.starting_money import getStartingMoney
from project.mobboss_apps.mobboss.composition import get_container
from project.mobboss_apps.rooms.ports.internal import DeleteRoomCommand

MERCHANT_GOAL_ADDITIONAL_PERCENT = 0.40
NOTIFICATION_TTL_SECONDS = 120
_POLICE_LEADERSHIP_ROLES = {
    "Chief of Police",
    "Deputy",
    "Sheriff",
    "Captain",
    "Lieutenant",
    "Sergeant",
    "Detective",
    "Inspector",
    "Police Officer",
    "Cop",
}
_MOB_OPERATIVE_ROLES = {"Enforcer", "Made Man", "Gangster", "Street Thug", "Felon"}
_TRADE_ROLES = {"Arms Dealer", "Smuggler", "Gun Runner", "Supplier", "Merchant"}


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


def _with_inventory_image_fallbacks(inventory_items: list[object]) -> list[object]:
    normalized_items: list[object] = []
    for item in inventory_items:
        image_path = str(getattr(item, "image_path", "") or "").strip()
        classification = str(getattr(item, "classification", "") or "").strip()
        normalized_image_path = _normalized_inventory_item_image_path(
            classification=classification,
            image_path=image_path,
        )
        if normalized_image_path == image_path:
            normalized_items.append(item)
            continue
        normalized_items.append(replace(item, image_path=normalized_image_path))
    return normalized_items
_ROLE_ABILITY_IMAGE_FILENAMES = {
    "Chief of Police": "chief_of_police.png",
    "Mob Boss": "mob_boss.png",
    "Knife Hobo": "knife_hobo.png",
    "Don": "don.png",
    "Under Boss": "under_boss.png",
    "Kingpin": "kingpin.png",
    "Deputy": "deputy.png",
    "Sheriff": "sheriff.png",
    "Captain": "captain.png",
    "Lieutenant": "lieutenant.png",
    "Sergeant": "sergeant.png",
    "Detective": "detective.png",
    "Inspector": "inspector.png",
    "Police Officer": "police_officer.png",
    "Cop": "cop.png",
    "Enforcer": "enforcer.png",
    "Made Man": "made_man.png",
    "Gangster": "gangster.png",
    "Street Thug": "street_thug.png",
    "Felon": "felon.png",
    "Merchant": "merchant.png",
    "Arms Dealer": "arms_dealer.png",
    "Smuggler": "smuggler.png",
    "Gun Runner": "gun_runner.png",
    "Supplier": "supplier.png",
}


def _normalize_shot_count_label(display_name: str) -> str:
    return re.sub(r"\b1\s+shots\b", "1 shot", display_name, flags=re.IGNORECASE)
_ROLE_ABILITY_METADATA = {
    "Chief of Police": {
        "ability_name": "Police Authority",
        "description": "You lead the Police faction and answer first when Police must make a decision.",
        "status_text": "This authority is automatic.",
        "status_tone": "info",
        "details": [
            "You are first in the accused-selection chain while Police remain active.",
            "On a correct guilty verdict, you receive the convicted player's resources if you are still the active Police leader.",
        ],
        "implementation_state": "This role effect is automatic.",
    },
    "Mob Boss": {
        "ability_name": "Faction Leadership",
        "description": "You are the top Mob leader. A false conviction pays out to you.",
        "status_text": "",
        "status_tone": "info",
        "details": [
            "You are the highest-ranking active Mob leader.",
            "If a guilty verdict is wrong, you receive all resources taken from the jailed player.",
        ],
        "implementation_state": "False-conviction transfers resolve automatically.",
    },
    "Knife Hobo": {
        "ability_name": "Starting Knife",
        "description": "You begin the game with a knife in your inventory.",
        "status_text": "Your starting item is assigned automatically.",
        "status_tone": "info",
        "details": [
            "The knife is placed in your inventory when the session starts.",
            "This role has no manual action on the current screen.",
        ],
        "implementation_state": "This role effect is automatic.",
    },
    "Don": {
        "ability_name": "Intimidation",
        "description": "Arm one target during information; that player is silenced on the next trial. One use.",
        "status_text": "Available during the Information phase.",
        "status_tone": "secondary",
        "details": [
            "Target one living player other than yourself during the Information phase.",
            "After the next reported murder starts trial flow, your target is marked silent for that trial.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Under Boss": {
        "ability_name": "Jury Manipulation",
        "description": "Remove one juror and take the seat yourself. One use.",
        "status_text": "Available when trial conditions are met.",
        "status_tone": "secondary",
        "details": [
            "One current juror is removed and you are inserted into the jury.",
            "Any vote already cast by the removed juror is discarded.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Kingpin": {
        "ability_name": "Clock Pressure",
        "description": "Start a 15-second jury vote timer during an active trial. Two uses on separate trials.",
        "status_text": "Available during active jury voting.",
        "status_tone": "secondary",
        "details": [
            "Starts a 15-second countdown for jury votes on the current trial.",
            "You may use this on at most two separate trials.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Deputy": {
        "ability_name": "Protective Custody",
        "description": "Place one living player under police protection for 5 minutes. One use.",
        "status_text": "Available during the Information phase.",
        "status_tone": "secondary",
        "details": [
            "Target one living player other than yourself during the Information phase.",
            "That player cannot be killed for 5 minutes. An attempted murder still triggers trial flow.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Sheriff": {
        "ability_name": "View Jury Log",
        "description": "See the most recent jury lineup, not the votes. Two uses per game.",
        "status_text": "Available while the game is active.",
        "status_tone": "secondary",
        "details": [
            "Shows only juror identities from the most recent jury assignment.",
            "Vote choices are never revealed.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Captain": {
        "ability_name": "Asset Freeze",
        "description": "Freeze one living player's money actions for 10 minutes. One use.",
        "status_text": "Available while the game is active.",
        "status_tone": "secondary",
        "details": [
            "The target cannot buy, sell, send money, receive money, or exchange gifts during the freeze window.",
            "Pending transactions involving the target are canceled immediately.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Lieutenant": {
        "ability_name": "Information Briefcase",
        "description": "Reveal living faction counts for 1 minute. One use per game.",
        "status_text": "Available while the game is active.",
        "status_tone": "secondary",
        "details": [
            "Shows only the counts for living Police, Mob, and Merchant players.",
            "No names or roles are exposed.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Sergeant": {
        "ability_name": "Capture",
        "description": "Place one living player in custody for 5 minutes. One use during Information.",
        "status_text": "Available during the Information phase.",
        "status_tone": "secondary",
        "details": [
            "A captured player cannot act and cannot use role abilities while custody is active.",
            "Only the Sergeant, moderator, and captured player see the custody status.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Detective": {
        "ability_name": "Investigation",
        "description": "Privately view a player's last three player-to-player transactions for 60 seconds. One use per game.",
        "status_text": "Available while the game is active.",
        "status_tone": "secondary",
        "details": [
            "Target any participant, living, dead, or jailed.",
            "The report shows only player-to-player transactions: time, sender, recipient, money, item, and transaction type.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Inspector": {
        "ability_name": "Record Inspection",
        "description": "Privately reveal the role of one dead or jailed player for 60 seconds. One use per game.",
        "status_text": "Available while the game is active.",
        "status_tone": "secondary",
        "details": [
            "Target one dead or jailed participant other than yourself.",
            "Only the role name is shown, and only to you.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Police Officer": {
        "ability_name": "Confiscation",
        "description": "Arm the next guilty verdict so the jailed player's resources are seized and divided by Police. One use per game.",
        "status_text": "Available during Information, Accused Selection, or active Trial Voting.",
        "status_tone": "secondary",
        "details": [
            "The Police Officer receives a confiscation share, and the remaining police share is distributed to other living Police players.",
            "The effect must be armed before the verdict and is canceled if the accused escapes or the officer is no longer active.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Cop": {
        "ability_name": "Last 3 Protection",
        "description": "You are automatically protected when 3 or fewer non-jailed players remain.",
        "status_text": "Status: Inactive",
        "status_tone": "secondary",
        "details": [
            "When the living non-jailed player count drops to 3 or fewer, this protection triggers once per game.",
            "If you do not already have a bulletproof vest, the system places one in your inventory.",
        ],
        "implementation_state": "This role effect is automatic.",
    },
    "Enforcer": {
        "ability_name": "First Kill Bonus",
        "description": "Your first successful kill pays a 50% cash bonus.",
        "status_text": "Status: Active",
        "status_tone": "secondary",
        "details": [
            "This triggers only on your first successful reported murder where you are the killer.",
            "The bonus is based only on the victim's transferred money and is generated by the system.",
        ],
        "implementation_state": "This role effect is automatic.",
    },
    "Made Man": {
        "ability_name": "Skip Middle Man",
        "description": "Buy one active item directly from Central Supply at listed price.",
        "status_text": "Available while the game is active.",
        "status_tone": "secondary",
        "details": [
            "This bypasses the normal merchant-only supply restriction for one purchase.",
            "The purchase still uses your money and still respects supply, custody, freeze, and life-state restrictions.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Gangster": {
        "ability_name": "Tamper",
        "description": "Suppress one juror's counted vote and replace it with your own for one trial.",
        "status_text": "Available during trial voting before all required votes are recorded.",
        "status_tone": "secondary",
        "details": [
            "Target one current juror and suppress that juror's counted vote for the current trial.",
            "You receive a separate replacement vote with its own timer. If you are already on the jury, you may vote twice.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Street Thug": {
        "ability_name": "Steal",
        "description": "Take $100 from one living player if they have it. One use while the game is active.",
        "status_text": "Available while the game is active.",
        "status_tone": "secondary",
        "details": [
            "Target one living player other than yourself and take exactly $100 if the target has at least that much.",
            "If the target has less than $100, the action is still consumed and no money moves.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Felon": {
        "ability_name": "Mob Succession",
        "description": "A Mob rank role with standard Mob play and possible automatic promotion.",
        "status_text": "Passive role. No action is available here.",
        "status_tone": "secondary",
        "details": [
            "This role follows the standard Mob trial, murder, inventory, and economy rules.",
            "You may become the active Mob leader automatically if higher-ranked Mob roles are removed.",
        ],
        "implementation_state": "This role effect is passive.",
    },
    "Merchant": {
        "ability_name": "Wholesale Order",
        "description": "Buy one active Central Supply item at a 30% discount. One use per game.",
        "status_text": "Available during the Information phase.",
        "status_tone": "secondary",
        "details": [
            "Only the base Merchant role has this ability. Other merchant roles have separate abilities.",
            "The purchase still removes the shared stock item and records the discounted payment in the ledger.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Arms Dealer": {
        "ability_name": "Starting Gun Cache",
        "description": "You start the game holding one Tier 1 gun from Central Supply.",
        "status_text": "Starting loadout is resolved automatically at game launch.",
        "status_tone": "info",
        "details": [
            "One Tier 1 gun is removed from Central Supply and placed in your inventory when the session starts.",
            "After that, you follow the standard merchant economy, resale, sale-offer, gifting, and money-goal systems.",
        ],
        "implementation_state": "Automatic start-of-game loadout is live. No manual activation button is needed.",
    },
    "Smuggler": {
        "ability_name": "Smuggle",
        "description": "Take one random eligible item from a living player during Information. One use per game.",
        "status_text": "Available only during the Information phase.",
        "status_tone": "secondary",
        "details": [
            "Target one living player other than yourself who is not in custody. One random eligible item is taken if available.",
            "If the target has no eligible items, the action is still consumed and only private notices are sent.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Gun Runner": {
        "ability_name": "Charisma",
        "description": "Open a 3-minute window where accepted sales pay you a 30% system bonus.",
        "status_text": "Available only during the Information phase.",
        "status_tone": "secondary",
        "details": [
            "The bonus applies when a player-to-player sale is accepted during the active window, based on the accepted sale price.",
            "The extra money is generated by the system, rounded to the normal nearest-$10 rule. Only you and the moderator are notified.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
    "Supplier": {
        "ability_name": "Acquire",
        "description": "Mark one player during Information. If they are merchant-faction, you take 50% of the base price from their next successful player sale.",
        "status_text": "Available only during the Information phase.",
        "status_tone": "secondary",
        "details": [
            "Choose one living player other than yourself. If they are not Merchant, Arms Dealer, Smuggler, or Gun Runner, the action is consumed immediately.",
            "If the target is valid, the next successful player-to-player sale by that target redirects 50% of the base accepted sale price to you, rounded to the normal nearest-$10 rule.",
        ],
        "implementation_state": "Act here when the window opens.",
    },
}


def _current_user_id(request: HttpRequest) -> str:
    return str(request.user.id or request.user.username)

def _parse_bool_flag(raw_value: object) -> bool:
    value = str(raw_value if raw_value is not None else "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _round_money_to_nearest_ten(value: int) -> int:
    return int(((value + 5) // 10) * 10)


def _merchant_wholesale_price(base_price: int) -> int:
    return _round_money_to_nearest_ten((base_price * 70) // 100)


def _game_detail_url(game_id: str, as_user_id: str = "", simulate_actions: bool = False) -> str:
    query_parts: list[str] = []
    if as_user_id:
        query_parts.append(f"as_user_id={quote_plus(as_user_id)}")
    if simulate_actions:
        query_parts.append("simulate_actions=1")
    if query_parts:
        return f"/games/{game_id}/?{'&'.join(query_parts)}"
    return f"/games/{game_id}/"


def _redirect_to_game_detail_with_context(request: HttpRequest, game_id: str) -> HttpResponse:
    as_user_id = str(request.POST.get("as_user_id", request.GET.get("as_user_id", ""))).strip()
    simulate_actions = _parse_bool_flag(request.POST.get("simulate_actions", request.GET.get("simulate_actions", "")))
    return redirect(_game_detail_url(game_id=game_id, as_user_id=as_user_id, simulate_actions=simulate_actions))


def _resolve_action_user_id(request: HttpRequest, *, session, dev_mode_enabled: bool) -> str:
    actor_user_id = _current_user_id(request)
    if session.moderator_user_id != actor_user_id or not dev_mode_enabled:
        return actor_user_id

    requested_user_id = str(request.POST.get("as_user_id", request.GET.get("as_user_id", ""))).strip()
    if not requested_user_id:
        return actor_user_id

    allowed_user_ids = {participant.user_id for participant in session.participants}
    if requested_user_id in allowed_user_ids:
        return requested_user_id
    return actor_user_id



def _set_active_game_session(request: HttpRequest, *, game_id: str, room_id: str) -> None:
    session_store = getattr(request, "session", None)
    if session_store is None:
        return
    session_store["active_game_id"] = game_id
    session_store["active_room_id"] = room_id


def _clear_active_game_session(request: HttpRequest) -> None:
    session_store = getattr(request, "session", None)
    if session_store is None:
        return
    session_store.pop("active_game_id", None)
    session_store.pop("active_room_id", None)


def _get_active_game_id(request: HttpRequest) -> str:
    session_store = getattr(request, "session", None)
    if session_store is None:
        return ""
    return str(session_store.get("active_game_id", "")).strip()


def _game_plan_steps() -> list[dict[str, str]]:
    return [
        {
            "phase": "information",
            "label": "Information",
            "description": "Gather information, assess risk, and decide your next move.",
        },
        {
            "phase": "accused_selection",
            "label": "Accused Selection",
            "description": "Police choose who gets put on trial.",
        },
        {
            "phase": "trial_voting",
            "label": "Trial Voting",
            "description": "The jury decides guilty or not guilty.",
        },
        {
            "phase": "boundary_resolution",
            "label": "Boundary Resolution",
            "description": "Results are applied and win conditions are checked.",
        },
        {
            "phase": "ended",
            "label": "Ended",
            "description": "The game is over.",
        },
    ]


def _viewer_notifications(session, viewer_user_id: str, *, now_epoch_seconds: int) -> list[object]:
    min_created_at_epoch_seconds = now_epoch_seconds - NOTIFICATION_TTL_SECONDS
    return sorted(
        [
            event
            for event in session.notification_feed
            if event.user_id == viewer_user_id and event.created_at_epoch_seconds >= min_created_at_epoch_seconds
        ],
        key=lambda event: event.created_at_epoch_seconds,
        reverse=True,
    )[:8]


def _viewer_notification_history(session, viewer_user_id: str) -> list[object]:
    return sorted(
        [
            event
            for event in session.notification_feed
            if event.user_id == viewer_user_id
        ],
        key=lambda event: event.created_at_epoch_seconds,
        reverse=True,
    )


def _display_name_for_user(participant_name_by_id: dict[str, str], user_id: str | None, *, unknown: str = "Unknown Player") -> str:
    if not user_id:
        return unknown
    name = str(participant_name_by_id.get(user_id, "")).strip()
    return name or unknown


def _gift_offer_view_rows(offers, *, participant_name_by_id: dict[str, str]) -> list[dict[str, object]]:
    return [
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
        for offer in offers
    ]


def _money_gift_offer_view_rows(offers, *, participant_name_by_id: dict[str, str]) -> list[dict[str, object]]:
    return [
        {
            "money_gift_offer_id": offer.money_gift_offer_id,
            "giver_user_id": offer.giver_user_id,
            "giver_username": _display_name_for_user(participant_name_by_id, offer.giver_user_id),
            "receiver_user_id": offer.receiver_user_id,
            "receiver_username": _display_name_for_user(participant_name_by_id, offer.receiver_user_id),
            "amount": offer.amount,
            "created_at_epoch_seconds": offer.created_at_epoch_seconds,
        }
        for offer in offers
    ]


def _sale_offer_view_rows(offers, *, participant_name_by_id: dict[str, str]) -> list[dict[str, object]]:
    return [
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
        for offer in offers
    ]


def _is_leadership_transition_notification(message: str) -> bool:
    normalized = str(message).strip()
    return normalized in {
        "You are now the Acting Chief of Police.",
        "You are now the Acting Mob Boss.",
    }


def _current_trial_key(session) -> str:
    pending_trial = session.pending_trial
    if pending_trial is None:
        return ""
    return f"{session.round_number}:{pending_trial.murdered_user_id}:{pending_trial.accused_user_id or 'pending'}"


def _role_ability_image_url(role_name: str) -> str:
    filename = _ROLE_ABILITY_IMAGE_FILENAMES.get(role_name)
    if not filename:
        return ""
    return static(f"characters/{filename}")


def _build_superpower_panel(
    session,
    *,
    current_user_id: str,
    current_participant,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object]:
    if current_participant is None or current_participant.life_state != "alive" or session.status != "in_progress":
        return {"show": False}

    role_name = current_participant.role_name
    pending_trial = session.pending_trial
    base_panel = {
        "show": True,
        "role_name": role_name,
        "image_url": _role_ability_image_url(role_name),
        "kind": "info",
        "title": "Role Ability",
        **_role_ability_metadata(role_name),
    }
    if role_name == "Don":
        target_rows = []
        if session.phase == "information":
            target_rows = [
                participant
                for participant in session.participants
                if participant.user_id != current_user_id and participant.life_state == "alive"
            ]
        armed_target = next(
            (
                participant
                for participant in session.participants
                if participant.user_id == current_participant.power_state.don_silence_target_user_id
            ),
            None,
        )
        return {
            **base_panel,
            "kind": "don",
            "used": current_participant.power_state.don_silence_used,
            "can_activate": (
                session.phase == "information"
                and bool(target_rows)
                and not current_participant.power_state.don_silence_used
            ),
            "target_rows": sorted(target_rows, key=lambda participant: participant.username.lower()),
            "armed_target_username": armed_target.username if armed_target is not None else "",
            "status_text": (
                f"Armed on {armed_target.username}."
                if current_participant.power_state.don_silence_target_user_id and armed_target is not None
                else (
                    "Armed for the next trial."
                    if current_participant.power_state.don_silence_target_user_id
                    else (
                        "Used."
                        if current_participant.power_state.don_silence_used
                        else "Ready during Information phase."
                    )
                )
            ),
            "status_tone": "dark"
            if current_participant.power_state.don_silence_used and not current_participant.power_state.don_silence_target_user_id
            else ("info" if current_participant.power_state.don_silence_target_user_id else "secondary"),
            "implementation_state": "Use this panel when the ability is available.",
        }

    if role_name == "Under Boss":
        juror_rows = []
        if session.phase == "trial_voting" and pending_trial is not None:
            juror_rows = [
                participant
                for participant in session.participants
                if participant.user_id in pending_trial.jury_user_ids and participant.user_id != current_user_id
            ]
        return {
            **base_panel,
            "kind": "underboss",
            "used": current_participant.power_state.underboss_jury_override_used,
            "can_activate": bool(juror_rows) and not current_participant.power_state.underboss_jury_override_used,
            "target_rows": sorted(juror_rows, key=lambda participant: participant.username.lower()),
            "status_text": (
                "Used."
                if current_participant.power_state.underboss_jury_override_used
                else "Ready during an active trial with a jury."
            ),
            "status_tone": "dark" if current_participant.power_state.underboss_jury_override_used else "secondary",
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Kingpin":
        reduced_trial_keys = list(current_participant.power_state.kingpin_reduced_trial_keys)
        current_trial_key = _current_trial_key(session)
        is_voting_active = session.phase == "trial_voting" and pending_trial is not None and pending_trial.vote_deadline_epoch_seconds is not None
        can_activate = (
            is_voting_active
            and len(reduced_trial_keys) < 2
            and current_trial_key not in reduced_trial_keys
        )
        return {
            **base_panel,
            "kind": "kingpin",
            "used_count": len(reduced_trial_keys),
            "remaining_uses": max(0, 2 - len(reduced_trial_keys)),
            "can_activate": can_activate,
            "status_text": f"{max(0, 2 - len(reduced_trial_keys))} uses remaining.",
            "status_tone": "secondary",
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Merchant":
        target_rows = []
        if session.phase == "information":
            target_rows = [
                {
                    "classification": item.classification,
                    "display_name": _normalize_shot_count_label(item.display_name),
                    "base_price": item.base_price,
                    "discounted_price": _merchant_wholesale_price(item.base_price),
                }
                for item in session.catalog
                if item.is_active
            ]
        return {
            **base_panel,
            "kind": "merchant",
            "used": current_participant.power_state.merchant_wholesale_order_used,
            "can_activate": (
                session.phase == "information"
                and bool(target_rows)
                and not current_participant.power_state.merchant_wholesale_order_used
            ),
            "target_rows": sorted(target_rows, key=lambda item: str(item["display_name"]).lower()),
            "status_text": (
                "Used."
                if current_participant.power_state.merchant_wholesale_order_used
                else "Ready during information phase."
            ),
            "status_tone": "dark" if current_participant.power_state.merchant_wholesale_order_used else "secondary",
            "implementation_state": "Activated power is fully usable from this card.",
        }

    if role_name == "Deputy":
        active_custody = _active_protective_custody_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        target_rows = []
        if session.phase == "information" and active_custody is None:
            target_rows = [
                participant
                for participant in session.participants
                if participant.user_id != current_user_id and participant.life_state == "alive"
            ]
        return {
            **base_panel,
            "kind": "deputy",
            "used": current_participant.power_state.deputy_protective_custody_used,
            "can_activate": (
                session.phase == "information"
                and active_custody is None
                and bool(target_rows)
                and not current_participant.power_state.deputy_protective_custody_used
            ),
            "target_rows": sorted(target_rows, key=lambda participant: participant.username.lower()),
            "active_custody": active_custody,
            "status_text": (
                "Used."
                if current_participant.power_state.deputy_protective_custody_used
                else (
                    "Active target in custody."
                    if active_custody is not None
                    else "Ready during information phase."
                )
            ),
            "status_tone": (
                "dark"
                if current_participant.power_state.deputy_protective_custody_used
                else ("info" if active_custody is not None else "secondary")
            ),
            "implementation_state": "Activated power is fully usable from this card.",
        }

    if role_name == "Captain":
        active_freeze = _active_asset_freeze_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        target_rows = []
        if session.status == "in_progress" and active_freeze is None:
            target_rows = [
                participant
                for participant in session.participants
                if participant.user_id != current_user_id and participant.life_state == "alive"
            ]
        return {
            **base_panel,
            "kind": "captain",
            "used": current_participant.power_state.captain_asset_freeze_used,
            "can_activate": (
                session.status == "in_progress"
                and active_freeze is None
                and bool(target_rows)
                and not current_participant.power_state.captain_asset_freeze_used
            ),
            "target_rows": sorted(target_rows, key=lambda participant: participant.username.lower()),
            "active_freeze": active_freeze,
            "status_text": (
                "Used."
                if current_participant.power_state.captain_asset_freeze_used
                else (
                    "Asset freeze is active."
                    if active_freeze is not None
                    else "Ready while game is in progress."
                )
            ),
            "status_tone": (
                "dark"
                if current_participant.power_state.captain_asset_freeze_used
                else ("info" if active_freeze is not None else "secondary")
            ),
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Lieutenant":
        reveal_state = _active_lieutenant_briefcase_state(
            current_participant,
            now_epoch_seconds=now_epoch_seconds,
        )
        return {
            **base_panel,
            "kind": "lieutenant",
            "used": current_participant.power_state.lieutenant_information_briefcase_used,
            "can_activate": (
                session.status == "in_progress"
                and not current_participant.power_state.lieutenant_information_briefcase_used
            ),
            "reveal_state": reveal_state,
            "status_text": (
                "Used."
                if current_participant.power_state.lieutenant_information_briefcase_used
                else "Ready while game is in progress."
            ),
            "status_tone": (
                "dark" if current_participant.power_state.lieutenant_information_briefcase_used else "secondary"
            ),
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Sergeant":
        active_capture = _active_sergeant_capture_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        target_rows = []
        if session.phase == "information" and session.status == "in_progress" and active_capture is None:
            target_rows = [
                participant
                for participant in session.participants
                if participant.user_id != current_user_id and participant.life_state == "alive"
            ]
        return {
            **base_panel,
            "kind": "sergeant",
            "used": current_participant.power_state.sergeant_capture_used,
            "can_activate": (
                session.status == "in_progress"
                and session.phase == "information"
                and active_capture is None
                and bool(target_rows)
                and not current_participant.power_state.sergeant_capture_used
            ),
            "target_rows": sorted(target_rows, key=lambda participant: participant.username.lower()),
            "active_capture": active_capture,
            "status_text": (
                "Used."
                if current_participant.power_state.sergeant_capture_used
                else ("Capture is active." if active_capture is not None else "Ready during information phase.")
            ),
            "status_tone": (
                "dark"
                if current_participant.power_state.sergeant_capture_used
                else ("info" if active_capture is not None else "secondary")
            ),
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Detective":
        active_capture = _active_sergeant_capture_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        reveal_state = _active_detective_investigation_state(
            current_participant,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        is_captured = (
            active_capture is not None and active_capture["target_user_id"] == current_participant.user_id
        )
        target_rows = sorted(session.participants, key=lambda participant: participant.username.lower())
        return {
            **base_panel,
            "kind": "detective",
            "used": current_participant.power_state.detective_investigation_used,
            "can_activate": (
                session.status == "in_progress"
                and bool(target_rows)
                and not is_captured
                and not current_participant.power_state.detective_investigation_used
            ),
            "target_rows": target_rows,
            "reveal_state": reveal_state,
            "status_text": (
                "Used."
                if current_participant.power_state.detective_investigation_used
                else ("Unavailable while in custody." if is_captured else "Ready while game is in progress.")
            ),
            "status_tone": (
                "dark"
                if current_participant.power_state.detective_investigation_used
                else ("warning" if is_captured else "secondary")
            ),
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Inspector":
        active_capture = _active_sergeant_capture_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        reveal_state = _active_inspector_record_inspection_state(
            current_participant,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        is_captured = active_capture is not None and active_capture["target_user_id"] == current_participant.user_id
        target_rows = sorted(
            [
                participant
                for participant in session.participants
                if participant.user_id != current_user_id and participant.life_state in {"dead", "jailed"}
            ],
            key=lambda participant: participant.username.lower(),
        )
        return {
            **base_panel,
            "kind": "inspector",
            "used": current_participant.power_state.inspector_record_inspection_used,
            "can_activate": (
                session.status == "in_progress"
                and bool(target_rows)
                and not is_captured
                and not current_participant.power_state.inspector_record_inspection_used
            ),
            "target_rows": target_rows,
            "reveal_state": reveal_state,
            "status_text": (
                "Used."
                if current_participant.power_state.inspector_record_inspection_used
                else (
                    "Unavailable while in custody."
                    if is_captured
                    else ("No jail or morgue records available yet." if not target_rows else "Ready while game is in progress.")
                )
            ),
            "status_tone": (
                "dark"
                if current_participant.power_state.inspector_record_inspection_used
                else ("warning" if is_captured else "secondary")
            ),
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Police Officer":
        active_capture = _active_sergeant_capture_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        is_captured = active_capture is not None and active_capture["target_user_id"] == current_participant.user_id
        can_activate = (
            not current_participant.power_state.police_officer_confiscation_used
            and not current_participant.power_state.police_officer_confiscation_pending
            and not is_captured
            and _can_activate_police_officer_confiscation_view(session)
        )
        return {
            **base_panel,
            "kind": "police_officer",
            "used": current_participant.power_state.police_officer_confiscation_used,
            "pending": current_participant.power_state.police_officer_confiscation_pending,
            "can_activate": can_activate,
            "status_text": (
                "Used."
                if current_participant.power_state.police_officer_confiscation_used
                else (
                    "Confiscation is armed for the next guilty verdict."
                    if current_participant.power_state.police_officer_confiscation_pending
                    else (
                        "Unavailable while in custody."
                        if is_captured
                        else "Ready during information, accused selection, or active trial voting."
                    )
                )
            ),
            "status_tone": (
                "dark"
                if current_participant.power_state.police_officer_confiscation_used
                else ("info" if current_participant.power_state.police_officer_confiscation_pending else ("warning" if is_captured else "secondary"))
            ),
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Cop":
        has_bulletproof_vest = any(item.classification == "bulletproof_vest" for item in current_participant.inventory)
        is_active = current_participant.power_state.cop_last_three_protection_used and has_bulletproof_vest
        return {
            **base_panel,
            "kind": "cop",
            "active": is_active,
            "status_text": f"Status: {'Active' if is_active else 'Inactive'}",
            "status_tone": "info" if is_active else "secondary",
            "implementation_state": "This protection runs automatically - no button needed.",
        }

    if role_name == "Enforcer":
        return {
            **base_panel,
            "kind": "enforcer",
            "status_text": (
                "Status: Used"
                if current_participant.power_state.enforcer_first_kill_bonus_used
                else "Status: Active"
            ),
            "status_tone": "dark" if current_participant.power_state.enforcer_first_kill_bonus_used else "secondary",
            "implementation_state": "This bonus runs automatically - no button needed.",
        }

    if role_name == "Gangster":
        juror_rows = []
        if session.phase == "trial_voting" and pending_trial is not None:
            juror_rows = [
                participant
                for participant in session.participants
                if participant.user_id in pending_trial.jury_user_ids
                and not (participant.user_id == current_user_id and current_user_id in pending_trial.jury_user_ids)
            ]
        effective_vote_count = len(_counted_trial_votes_view(session))
        can_activate = (
            session.phase == "trial_voting"
            and pending_trial is not None
            and not current_participant.power_state.gangster_tamper_used
            and pending_trial.gangster_tamper_target_user_id is None
            and effective_vote_count < len(pending_trial.jury_user_ids)
            and bool(juror_rows)
        )
        target_username = _display_name_for_user(
            participant_name_by_id,
            pending_trial.gangster_tamper_target_user_id if pending_trial is not None else None,
            unknown="",
        )
        return {
            **base_panel,
            "kind": "gangster",
            "used": current_participant.power_state.gangster_tamper_used,
            "can_activate": can_activate,
            "target_rows": sorted(juror_rows, key=lambda participant: participant.username.lower()),
            "active_target_username": target_username,
            "status_text": (
                "Status: Used"
                if current_participant.power_state.gangster_tamper_used
                else (
                    f"Tamper active against {target_username}."
                    if pending_trial is not None and pending_trial.gangster_tamper_target_user_id is not None
                    else "Status: Active"
                )
            ),
            "status_tone": (
                "dark"
                if current_participant.power_state.gangster_tamper_used
                else ("info" if pending_trial is not None and pending_trial.gangster_tamper_target_user_id is not None else "secondary")
            ),
            "implementation_state": "Activated power is fully usable from this card.",
        }

    if role_name == "Street Thug":
        active_capture = _active_sergeant_capture_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        is_captured = active_capture is not None and active_capture["target_user_id"] == current_participant.user_id
        captured_target_user_id = active_capture["target_user_id"] if active_capture is not None else None
        target_rows = sorted(
            [
                participant
                for participant in session.participants
                if participant.user_id != current_user_id
                and participant.life_state == "alive"
                and participant.user_id != captured_target_user_id
            ],
            key=lambda participant: participant.username.lower(),
        )
        return {
            **base_panel,
            "kind": "street_thug",
            "used": current_participant.power_state.street_thug_steal_used,
            "can_activate": (
                session.status == "in_progress"
                and bool(target_rows)
                and not is_captured
                and not current_participant.power_state.street_thug_steal_used
            ),
            "target_rows": target_rows,
            "status_text": (
                "Used."
                if current_participant.power_state.street_thug_steal_used
                else ("Unavailable while in custody." if is_captured else "Ready while game is in progress.")
            ),
            "status_tone": (
                "dark"
                if current_participant.power_state.street_thug_steal_used
                else ("warning" if is_captured else "secondary")
            ),
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Smuggler":
        active_capture = _active_sergeant_capture_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        is_captured = active_capture is not None and active_capture["target_user_id"] == current_participant.user_id
        captured_target_user_id = active_capture["target_user_id"] if active_capture is not None else None
        target_rows = sorted(
            [
                participant
                for participant in session.participants
                if participant.user_id != current_user_id
                and participant.life_state == "alive"
                and participant.user_id != captured_target_user_id
            ],
            key=lambda participant: participant.username.lower(),
        )
        return {
            **base_panel,
            "kind": "smuggler",
            "used": current_participant.power_state.smuggler_smuggle_used,
            "can_activate": (
                session.phase == "information"
                and bool(target_rows)
                and not is_captured
                and not current_participant.power_state.smuggler_smuggle_used
            ),
            "target_rows": target_rows,
            "status_text": (
                "Used."
                if current_participant.power_state.smuggler_smuggle_used
                else ("Unavailable while in custody." if is_captured else "Ready during information phase.")
            ),
            "status_tone": (
                "dark"
                if current_participant.power_state.smuggler_smuggle_used
                else ("warning" if is_captured else "secondary")
            ),
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Gun Runner":
        active_capture = _active_sergeant_capture_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        is_captured = active_capture is not None and active_capture["target_user_id"] == current_participant.user_id
        charisma_state = _active_gun_runner_charisma_state(
            current_participant,
            now_epoch_seconds=now_epoch_seconds,
        )
        active_freeze = _active_asset_freeze_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        is_frozen = active_freeze is not None and active_freeze["target_user_id"] == current_participant.user_id
        return {
            **base_panel,
            "kind": "gun_runner",
            "used": current_participant.power_state.gun_runner_charisma_used,
            "can_activate": (
                session.phase == "information"
                and not is_captured
                and not current_participant.power_state.gun_runner_charisma_used
            ),
            "charisma_state": charisma_state,
            "status_text": (
                "Status: Used"
                if current_participant.power_state.gun_runner_charisma_used and charisma_state is None
                else (
                    "Charisma is active."
                    if charisma_state is not None
                    else ("Unavailable while in custody." if is_captured else ("Accounts are frozen, but Charisma can still be activated." if is_frozen else "Ready during information phase."))
                )
            ),
            "status_tone": (
                "dark"
                if current_participant.power_state.gun_runner_charisma_used and charisma_state is None
                else ("info" if charisma_state is not None else ("warning" if is_captured or is_frozen else "secondary"))
            ),
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Supplier":
        active_capture = _active_sergeant_capture_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        is_captured = active_capture is not None and active_capture["target_user_id"] == current_participant.user_id
        target_rows = sorted(
            [
                participant
                for participant in session.participants
                if participant.user_id != current_user_id and participant.life_state == "alive"
            ],
            key=lambda participant: participant.username.lower(),
        )
        acquire_target = None
        if current_participant.power_state.supplier_acquire_target_user_id:
            acquire_target = next(
                (
                    participant
                    for participant in session.participants
                    if participant.user_id == current_participant.power_state.supplier_acquire_target_user_id
                ),
                None,
            )
        acquire_state = (
            {
                "target_user_id": current_participant.power_state.supplier_acquire_target_user_id,
                "target_username": (
                    acquire_target.username
                    if acquire_target is not None
                    else _display_name_for_user(
                        participant_name_by_id,
                        current_participant.power_state.supplier_acquire_target_user_id,
                    )
                ),
            }
            if current_participant.power_state.supplier_acquire_target_user_id
            else None
        )
        return {
            **base_panel,
            "kind": "supplier",
            "used": current_participant.power_state.supplier_acquire_used,
            "can_activate": (
                session.phase == "information"
                and bool(target_rows)
                and not is_captured
                and not current_participant.power_state.supplier_acquire_used
            ),
            "target_rows": target_rows,
            "acquire_state": acquire_state,
            "status_text": (
                "Acquire is armed."
                if acquire_state is not None
                else (
                    "Used."
                    if current_participant.power_state.supplier_acquire_used
                    else ("Unavailable while in custody." if is_captured else "Ready during information phase.")
                )
            ),
            "status_tone": (
                "info"
                if acquire_state is not None
                else (
                    "dark"
                    if current_participant.power_state.supplier_acquire_used
                    else ("warning" if is_captured else "secondary")
                )
            ),
            "implementation_state": "Activated power is fully usable from this card.",
        }

    if role_name == "Made Man":
        target_rows = sorted(
            [
                {
                    "classification": item.classification,
                    "display_name": _normalize_shot_count_label(item.display_name),
                    "base_price": item.base_price,
                }
                for item in session.catalog
                if item.is_active
            ],
            key=lambda item: str(item["display_name"]).lower(),
        )
        active_capture = _active_sergeant_capture_state(
            session,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        is_captured = active_capture is not None and active_capture["target_user_id"] == current_participant.user_id
        can_activate = (
            session.status == "in_progress"
            and current_participant.power_state.made_man_skip_middle_man_used is False
            and current_participant.life_state == "alive"
            and not is_captured
            and bool(target_rows)
        )
        return {
            **base_panel,
            "kind": "made_man",
            "used": current_participant.power_state.made_man_skip_middle_man_used,
            "can_activate": can_activate,
            "target_rows": target_rows,
            "status_text": (
                "Status: Used"
                if current_participant.power_state.made_man_skip_middle_man_used
                else ("Unavailable while in custody." if is_captured else ("No items remain in central supply." if not target_rows else "Status: Active"))
            ),
            "status_tone": (
                "dark"
                if current_participant.power_state.made_man_skip_middle_man_used
                else ("warning" if is_captured else "secondary")
            ),
            "implementation_state": "Use this card when your role power is available.",
        }

    if role_name == "Sheriff":
        reveal_state = _active_sheriff_jury_log_reveal_state(
            current_participant,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        used_count = current_participant.power_state.sheriff_jury_log_views_used
        has_history = bool(session.latest_jury_log_user_ids)
        return {
            **base_panel,
            "kind": "sheriff",
            "used_count": used_count,
            "remaining_uses": max(0, 2 - used_count),
            "can_activate": used_count < 2 and session.status == "in_progress",
            "has_history": has_history,
            "reveal_state": reveal_state,
            "status_text": (
                "No jury history yet."
                if not has_history and used_count < 2
                else f"{max(0, 2 - used_count)} uses remaining."
            ),
            "status_tone": "secondary",
            "implementation_state": "Use this card when your role power is available.",
        }

    return base_panel


def _role_ability_metadata(role_name: str) -> dict[str, str]:
    if role_name in _ROLE_ABILITY_METADATA:
        return dict(_ROLE_ABILITY_METADATA[role_name])
    return {
        "ability_name": "Role Ability",
        "description": "This role has no button power yet.",
        "status_text": "No active power to trigger right now.",
        "status_tone": "secondary",
        "details": [
            "You still play using normal faction, trial, and inventory rules.",
            "A custom role action has not been added yet.",
        ],
        "implementation_state": "This role card is informational for now.",
    }


def _active_protective_custody_state(
    session,
    *,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object] | None:
    target_user_id = session.protective_custody_user_id
    expires_at = session.protective_custody_expires_at_epoch_seconds
    activated_by_user_id = session.protective_custody_by_user_id
    if not target_user_id or expires_at is None or now_epoch_seconds >= expires_at:
        return None
    target = next((participant for participant in session.participants if participant.user_id == target_user_id), None)
    if target is None or target.life_state != "alive":
        return None
    return {
        "target_user_id": target_user_id,
        "target_username": _display_name_for_user(participant_name_by_id, target_user_id),
        "activated_by_user_id": activated_by_user_id,
        "expires_at_epoch_seconds": expires_at,
    }


def _active_sheriff_jury_log_reveal_state(
    current_participant,
    *,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object] | None:
    visible_until = current_participant.power_state.sheriff_jury_log_visible_until_epoch_seconds
    if visible_until is None or now_epoch_seconds >= visible_until:
        return None
    jury_user_ids = list(current_participant.power_state.sheriff_last_viewed_jury_user_ids)
    if not jury_user_ids:
        return None
    return {
        "jury_user_ids": jury_user_ids,
        "jury_usernames": [_display_name_for_user(participant_name_by_id, user_id) for user_id in jury_user_ids],
        "visible_until_epoch_seconds": visible_until,
    }


def _active_gun_runner_charisma_state(
    current_participant,
    *,
    now_epoch_seconds: int,
) -> dict[str, object] | None:
    visible_until = current_participant.power_state.gun_runner_charisma_expires_at_epoch_seconds
    if visible_until is None or now_epoch_seconds >= visible_until:
        return None
    return {"visible_until_epoch_seconds": visible_until}


def _active_detective_investigation_state(
    current_participant,
    *,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object] | None:
    visible_until = current_participant.power_state.detective_investigation_visible_until_epoch_seconds
    if visible_until is None or now_epoch_seconds >= visible_until:
        return None
    target_user_id = current_participant.power_state.detective_investigation_target_user_id
    if not target_user_id:
        return None
    target_username = _display_name_for_user(participant_name_by_id, target_user_id)
    total_transactions = current_participant.power_state.detective_last_viewed_transaction_total
    sorted_transactions = sorted(
        current_participant.power_state.detective_last_viewed_transactions,
        key=lambda transaction: transaction.created_at_epoch_seconds,
    )
    transaction_rows = [
        {
            "transaction_id": transaction.transaction_id,
            "summary_text": _detective_transaction_summary_text(
                transaction,
                participant_name_by_id=participant_name_by_id,
            ),
        }
        for transaction in sorted_transactions
    ]
    return {
        "target_user_id": target_user_id,
        "target_username": target_username,
        "visible_until_epoch_seconds": visible_until,
        "transaction_rows": transaction_rows,
        "total_transactions": total_transactions,
    }


def _active_inspector_record_inspection_state(
    current_participant,
    *,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object] | None:
    visible_until = current_participant.power_state.inspector_record_visible_until_epoch_seconds
    if visible_until is None or now_epoch_seconds >= visible_until:
        return None
    target_user_id = current_participant.power_state.inspector_record_target_user_id
    role_name = current_participant.power_state.inspector_last_viewed_role_name
    if not target_user_id or not role_name:
        return None
    return {
        "target_user_id": target_user_id,
        "target_username": _display_name_for_user(participant_name_by_id, target_user_id),
        "role_name": role_name,
        "visible_until_epoch_seconds": visible_until,
    }


def _detective_transaction_type_label(transaction_kind: str) -> str:
    if transaction_kind == "sale":
        return "Sale"
    if transaction_kind == "money_gift":
        return "Money Gift"
    if transaction_kind == "item_gift":
        return "Item Gift"
    if transaction_kind == "item_theft":
        return "Stolen Item"
    return "Transaction"


def _detective_transaction_summary_text(
    transaction,
    *,
    participant_name_by_id: dict[str, str],
) -> str:
    sender_username = _display_name_for_user(participant_name_by_id, transaction.sender_user_id)
    recipient_username = _display_name_for_user(participant_name_by_id, transaction.recipient_user_id)
    time_text = _format_local_time(transaction.created_at_epoch_seconds)
    item_or_money = transaction.item_name or (f"${transaction.money_amount}" if transaction.money_amount else "item")
    if transaction.transaction_kind == "sale":
        return f"{recipient_username} purchased {item_or_money} from {sender_username} at {time_text}"
    if transaction.transaction_kind == "money_gift":
        return f"{recipient_username} was gifted ${transaction.money_amount} from {sender_username} at {time_text}"
    if transaction.transaction_kind == "item_gift":
        return f"{recipient_username} was gifted {item_or_money} from {sender_username} at {time_text}"
    if transaction.transaction_kind == "item_theft":
        return f"{recipient_username} stole {item_or_money} from {sender_username} at {time_text}"
    return f"{recipient_username} received {item_or_money} from {sender_username} at {time_text}"


def _format_local_timestamp(epoch_seconds: int) -> str:
    local_dt = datetime.fromtimestamp(epoch_seconds)
    return local_dt.strftime("%Y-%m-%d %I:%M %p").replace(" 0", " ")


def _format_local_time(epoch_seconds: int) -> str:
    local_dt = datetime.fromtimestamp(epoch_seconds)
    return local_dt.strftime("%I:%M %p").lstrip("0")


def _can_activate_police_officer_confiscation_view(session) -> bool:
    if session.status != "in_progress":
        return False
    if session.phase == "information":
        return True
    if session.phase == "accused_selection":
        return session.pending_trial is not None
    if session.phase == "trial_voting" and session.pending_trial is not None:
        return len(_counted_trial_votes_view(session)) < len(session.pending_trial.jury_user_ids)
    return False


def _counted_trial_votes_view(session) -> list[dict[str, str]]:
    pending_trial = session.pending_trial
    if pending_trial is None:
        return []
    actor_user_id = pending_trial.gangster_tamper_actor_user_id
    target_user_id = pending_trial.gangster_tamper_target_user_id
    captured_user_id = session.sergeant_capture_user_id if session.sergeant_capture_expires_at_epoch_seconds else None
    tamper_active = False
    if actor_user_id and target_user_id:
        actor = next((participant for participant in session.participants if participant.user_id == actor_user_id), None)
        tamper_active = actor is not None and actor.life_state == "alive" and captured_user_id != actor_user_id
    counted = []
    for vote in pending_trial.votes:
        vote_slot = str(vote.get("vote_slot", "jury"))
        user_id = str(vote.get("user_id", ""))
        if vote_slot == "tamper":
            if tamper_active and user_id == actor_user_id:
                counted.append(dict(vote))
            continue
        if tamper_active and user_id == target_user_id:
            continue
        counted.append(dict(vote))
    return counted


def _active_asset_freeze_state(
    session,
    *,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object] | None:
    target_user_id = session.asset_freeze_user_id
    expires_at = session.asset_freeze_expires_at_epoch_seconds
    activated_by_user_id = session.asset_freeze_by_user_id
    if not target_user_id or expires_at is None or now_epoch_seconds >= expires_at:
        return None
    target = next((participant for participant in session.participants if participant.user_id == target_user_id), None)
    if target is None or target.life_state != "alive":
        return None
    return {
        "target_user_id": target_user_id,
        "target_username": _display_name_for_user(participant_name_by_id, target_user_id),
        "activated_by_user_id": activated_by_user_id,
        "expires_at_epoch_seconds": expires_at,
    }


def _active_sergeant_capture_state(
    session,
    *,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object] | None:
    target_user_id = session.sergeant_capture_user_id
    expires_at = session.sergeant_capture_expires_at_epoch_seconds
    activated_by_user_id = session.sergeant_capture_by_user_id
    if not target_user_id or expires_at is None or now_epoch_seconds >= expires_at:
        return None
    target = next((participant for participant in session.participants if participant.user_id == target_user_id), None)
    if target is None or target.life_state != "alive":
        return None
    return {
        "target_user_id": target_user_id,
        "target_username": _display_name_for_user(participant_name_by_id, target_user_id),
        "activated_by_user_id": activated_by_user_id,
        "expires_at_epoch_seconds": expires_at,
    }


def _active_felon_escape_state(
    session,
    *,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object] | None:
    felon_user_id = session.felon_escape_user_id
    expires_at = session.felon_escape_expires_at_epoch_seconds
    if not felon_user_id or expires_at is None or now_epoch_seconds >= expires_at:
        return None
    felon = next((participant for participant in session.participants if participant.user_id == felon_user_id), None)
    if felon is None or felon.life_state != "jailed" or felon.role_name != "Felon":
        return None
    return {
        "target_user_id": felon_user_id,
        "target_username": _display_name_for_user(participant_name_by_id, felon_user_id),
        "expires_at_epoch_seconds": expires_at,
    }


def _active_lieutenant_briefcase_state(
    current_participant,
    *,
    now_epoch_seconds: int,
) -> dict[str, object] | None:
    visible_until = current_participant.power_state.lieutenant_briefcase_visible_until_epoch_seconds
    if visible_until is None or now_epoch_seconds >= visible_until:
        return None
    return {
        "alive_police_count": current_participant.power_state.lieutenant_briefcase_alive_police_count,
        "alive_mob_count": current_participant.power_state.lieutenant_briefcase_alive_mob_count,
        "alive_merchant_count": current_participant.power_state.lieutenant_briefcase_alive_merchant_count,
        "visible_until_epoch_seconds": visible_until,
    }


def _build_protective_custody_panel(
    session,
    *,
    current_user_id: str,
    actor_is_moderator: bool,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object]:
    active_custody = _active_protective_custody_state(
        session,
        participant_name_by_id=participant_name_by_id,
        now_epoch_seconds=now_epoch_seconds,
    )
    if active_custody is None:
        return {"show": False}
    allowed_viewers = {
        active_custody["target_user_id"],
        active_custody["activated_by_user_id"],
    }
    if not actor_is_moderator and current_user_id not in allowed_viewers:
        return {"show": False}
    return {
        "show": True,
        "target_username": active_custody["target_username"],
        "expires_at_epoch_seconds": active_custody["expires_at_epoch_seconds"],
        "viewer_is_moderator": actor_is_moderator,
    }


def _build_asset_freeze_panel(
    session,
    *,
    current_user_id: str,
    actor_is_moderator: bool,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object]:
    active_freeze = _active_asset_freeze_state(
        session,
        participant_name_by_id=participant_name_by_id,
        now_epoch_seconds=now_epoch_seconds,
    )
    if active_freeze is None:
        return {"show": False}
    allowed_viewers = {
        active_freeze["target_user_id"],
        active_freeze["activated_by_user_id"],
    }
    if not actor_is_moderator and current_user_id not in allowed_viewers:
        return {"show": False}
    return {
        "show": True,
        "target_username": active_freeze["target_username"],
        "expires_at_epoch_seconds": active_freeze["expires_at_epoch_seconds"],
        "viewer_is_moderator": actor_is_moderator,
    }


def _build_sergeant_capture_panel(
    session,
    *,
    current_user_id: str,
    actor_is_moderator: bool,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object]:
    active_capture = _active_sergeant_capture_state(
        session,
        participant_name_by_id=participant_name_by_id,
        now_epoch_seconds=now_epoch_seconds,
    )
    if active_capture is None:
        return {"show": False}
    allowed_viewers = {
        active_capture["target_user_id"],
        active_capture["activated_by_user_id"],
    }
    if not actor_is_moderator and current_user_id not in allowed_viewers:
        return {"show": False}
    return {
        "show": True,
        "target_username": active_capture["target_username"],
        "expires_at_epoch_seconds": active_capture["expires_at_epoch_seconds"],
        "viewer_is_moderator": actor_is_moderator,
    }


def _build_felon_escape_panel(
    session,
    *,
    current_user_id: str,
    actor_is_moderator: bool,
    participant_name_by_id: dict[str, str],
    now_epoch_seconds: int,
) -> dict[str, object]:
    active_escape = _active_felon_escape_state(
        session,
        participant_name_by_id=participant_name_by_id,
        now_epoch_seconds=now_epoch_seconds,
    )
    if active_escape is None:
        return {"show": False}
    if not actor_is_moderator and current_user_id != active_escape["target_user_id"]:
        return {"show": False}
    return {
        "show": True,
        "target_username": active_escape["target_username"],
        "target_user_id": active_escape["target_user_id"],
        "expires_at_epoch_seconds": active_escape["expires_at_epoch_seconds"],
        "viewer_is_target": current_user_id == active_escape["target_user_id"],
        "viewer_is_moderator": actor_is_moderator,
    }


def _participant_has_ghost_view(session: GameDetailsSnapshot, participant: ParticipantStateSnapshot) -> bool:
    if (
        session.status == "in_progress"
        and participant.role_name == "Felon"
        and participant.life_state == "jailed"
        and session.felon_escape_user_id == participant.user_id
        and session.felon_escape_expires_at_epoch_seconds is not None
    ):
        return False
    return participant.life_state in {"dead", "jailed"}


@login_required(login_url="/auth/")
def index(request: HttpRequest) -> HttpResponse:
    IndexRequestDTO.from_payload({"method": request.method})
    return redirect("web-lobby")


@login_required(login_url="/auth/")
def detail(request: HttpRequest, game_id: str) -> HttpResponse:
    try:
        dto = GameIdRequestDTO.from_payload({"method": request.method, "game_id": game_id})
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(dto.game_id)
        actor_user_id = _current_user_id(request)
        actor_is_moderator = session.moderator_user_id == actor_user_id
        dev_mode_enabled = container.room_dev_mode

        requested_view_as_user_id = str(request.GET.get("as_user_id", "")).strip()
        requested_simulate_actions = _parse_bool_flag(request.GET.get("simulate_actions", ""))
        allowed_view_as_user_ids = {participant.user_id for participant in session.participants}

        current_user_id = actor_user_id
        if actor_is_moderator and dev_mode_enabled and requested_view_as_user_id in allowed_view_as_user_ids:
            current_user_id = requested_view_as_user_id
        is_view_as_mode = current_user_id != actor_user_id
        simulate_actions_enabled = actor_is_moderator and dev_mode_enabled and is_view_as_mode and requested_simulate_actions

        page = build_gameplay_page_view(session, current_user_id)
        _set_active_game_session(request, game_id=session.game_id, room_id=session.room_id)
        can_submit_accused_selection = (
            page.phase == "accused_selection"
            and page.status == "in_progress"
            and session.pending_trial is not None
            and bool(session.pending_trial.accused_selection_cursor)
            and session.pending_trial.accused_selection_cursor[0] == current_user_id
        )
        accused_candidate_rows = [participant for participant in page.participant_rows if participant.life_state == "alive"]
        participant_name_by_id = {participant.user_id: participant.username for participant in session.participants}
        now_epoch_seconds = int(time.time())
        viewer_notifications = _viewer_notifications(session, current_user_id, now_epoch_seconds=now_epoch_seconds)
        viewer_notification_history = _viewer_notification_history(session, current_user_id)
        jury_user_ids = list(session.pending_trial.jury_user_ids) if session.pending_trial is not None else []
        current_user_has_voted = (
            session.pending_trial is not None
            and any(
                vote.get("user_id") == current_user_id and str(vote.get("vote_slot", "jury")) == "jury"
                for vote in session.pending_trial.votes
            )
        )
        current_user_has_tamper_vote = (
            session.pending_trial is not None
            and any(
                vote.get("user_id") == current_user_id and str(vote.get("vote_slot", "jury")) == "tamper"
                for vote in session.pending_trial.votes
            )
        )
        current_user_is_silenced = (
            session.pending_trial is not None
            and current_user_id in session.pending_trial.silenced_user_ids
        )
        is_jury_voting_active = (
            session.pending_trial is not None and session.pending_trial.vote_deadline_epoch_seconds is not None
        )
        tamper_target_user_id = session.pending_trial.gangster_tamper_target_user_id if session.pending_trial is not None else None
        tamper_actor_user_id = session.pending_trial.gangster_tamper_actor_user_id if session.pending_trial is not None else None
        current_user_is_juror = current_user_id in jury_user_ids
        jury_prompt = {
            "show": (
                page.phase == "trial_voting"
                and session.pending_trial is not None
                and (current_user_is_juror or tamper_actor_user_id == current_user_id)
            ),
            "is_juror": current_user_is_juror,
            "accused_user_id": session.pending_trial.accused_user_id if session.pending_trial is not None else None,
            "accused_username": _display_name_for_user(
                participant_name_by_id,
                session.pending_trial.accused_user_id if session.pending_trial is not None else None,
                unknown="Unknown",
            ),
            "has_voted": current_user_has_voted,
            "can_vote": is_jury_voting_active and current_user_is_juror and not current_user_has_voted,
            "is_silenced": current_user_is_silenced,
            "silence_notice": "You seem to be afraid to testify at court. You must remain silent during this trial.",
            "show_tamper_vote": page.phase == "trial_voting" and tamper_actor_user_id == current_user_id,
            "tamper_has_voted": current_user_has_tamper_vote,
            "tamper_can_vote": (
                session.pending_trial is not None
                and tamper_actor_user_id == current_user_id
                and tamper_target_user_id is not None
                and not current_user_has_tamper_vote
            ),
            "tamper_vote_deadline_epoch_seconds": (
                session.pending_trial.gangster_tamper_vote_deadline_epoch_seconds if session.pending_trial is not None else None
            ),
            "tamper_target_username": _display_name_for_user(participant_name_by_id, tamper_target_user_id, unknown="Unknown"),
            "waiting_for_moderator": (current_user_is_juror and not is_jury_voting_active),
            "vote_deadline_epoch_seconds": (
                session.pending_trial.vote_deadline_epoch_seconds if session.pending_trial is not None else None
            ),
            "vote_timer_active": (
                session.pending_trial is not None
                and session.pending_trial.vote_deadline_epoch_seconds is not None
                and session.pending_trial.vote_deadline_epoch_seconds > 0
            ),
        }
        defer_accused_overlay_for_leadership_notice = (
            can_submit_accused_selection
            and any(_is_leadership_transition_notification(event.message) for event in viewer_notifications)
        )
        moderator_trial_control = {
            "show": (
                (page.is_moderator or page.is_ghost_view)
                and page.phase == "trial_voting"
                and session.pending_trial is not None
            ),
            "viewer_can_start_voting": actor_is_moderator,
            "is_voting_active": is_jury_voting_active,
            "accused_username": _display_name_for_user(
                participant_name_by_id,
                session.pending_trial.accused_user_id if session.pending_trial is not None else None,
                unknown="Unknown",
            ),
            "juror_usernames": [_display_name_for_user(participant_name_by_id, user_id) for user_id in jury_user_ids],
            "tampered_juror_username": (
                _display_name_for_user(participant_name_by_id, tamper_target_user_id, unknown="")
                if tamper_target_user_id
                else ""
            ),
        }
        pending_trial_murdered_username = ""
        pending_trial_current_responder_username = ""
        if session.pending_trial is not None:
            pending_trial_murdered_username = _display_name_for_user(
                participant_name_by_id,
                session.pending_trial.murdered_user_id,
            )
        if page.pending_trial is not None:
            pending_trial_current_responder_username = _display_name_for_user(
                participant_name_by_id,
                page.pending_trial.current_responder_user_id,
                unknown="",
            )
        current_participant = next((participant for participant in session.participants if participant.user_id == current_user_id), None)
        can_view_accused_selection = (
            page.phase == "accused_selection"
            and page.status == "in_progress"
            and current_participant is not None
            and current_participant.faction == "Police"
            and not page.is_ghost_view
        )
        ghost_view_enabled = bool(page.is_ghost_view)
        is_current_user_merchant = (
            current_participant is not None
            and current_participant.faction == "Merchant"
            and current_participant.life_state == "alive"
            and not ghost_view_enabled
        )
        merchant_supply_items = sorted(
            [
                {
                    "classification": item.classification,
                    "display_name": _normalize_shot_count_label(item.display_name),
                    "base_price": item.base_price,
                }
                for item in session.catalog
                if item.is_active
            ],
            key=lambda item: str(item["display_name"]).lower(),
        )
        merchant_inventory_items = [] if current_participant is None else _with_inventory_image_fallbacks(list(current_participant.inventory))
        merchant_sale_targets = sorted(
            [
                participant
                for participant in session.participants
                if participant.user_id != current_user_id and participant.life_state == "alive"
            ],
            key=lambda participant: participant.username.lower(),
        )
        show_player_inventory = (
            current_participant is not None
            and not page.is_moderator
            and not page.is_ghost_view
        )
        show_player_wallet = show_player_inventory and not is_current_user_merchant
        use_player_phone_layout = bool(show_player_inventory)
        player_money_balance = 0 if current_participant is None else current_participant.money_balance
        merchant_money_balance = 0 if current_participant is None else current_participant.money_balance
        merchant_money_goal = None
        if is_current_user_merchant and current_participant is not None:
            player_count = max(7, min(len(session.participants), 25))
            goal_bonus = int(session.ledger.circulating_currency_baseline * MERCHANT_GOAL_ADDITIONAL_PERCENT)
            merchant_money_goal = getStartingMoney(player_count, current_participant.role_name) + goal_bonus
        player_inventory_items = [] if current_participant is None else _with_inventory_image_fallbacks(list(current_participant.inventory))
        player_role_name = "" if current_participant is None else current_participant.role_name
        player_role_label = ""
        if current_participant is not None:
            player_role_label = _participant_role_label(session, current_participant.user_id, reveal_role=True)
        player_role_image_url = _role_ability_image_url(player_role_name) if player_role_name else ""
        can_self_report_murder = (
            not page.is_moderator
            and current_participant is not None
            and current_participant.life_state == "alive"
            and page.status == "in_progress"
            and session.pending_trial is None
        )
        self_report_murderer_rows = sorted(
            [
                participant
                for participant in session.participants
                if current_participant is not None
                and participant.user_id != current_participant.user_id
                and participant.life_state == "alive"
            ],
            key=lambda participant: participant.username.lower(),
        )
        player_gift_targets = sorted(
            [
                participant
                for participant in session.participants
                if participant.user_id != current_user_id and participant.life_state == "alive"
            ],
            key=lambda participant: participant.username.lower(),
        )
        incoming_gift_offers = _gift_offer_view_rows(
            [offer for offer in session.pending_gift_offers if offer.receiver_user_id == current_user_id],
            participant_name_by_id=participant_name_by_id,
        )
        outgoing_gift_offers = _gift_offer_view_rows(
            [offer for offer in session.pending_gift_offers if offer.giver_user_id == current_user_id],
            participant_name_by_id=participant_name_by_id,
        )
        incoming_money_gift_offers = _money_gift_offer_view_rows(
            [offer for offer in session.pending_money_gift_offers if offer.receiver_user_id == current_user_id],
            participant_name_by_id=participant_name_by_id,
        )
        outgoing_money_gift_offers = _money_gift_offer_view_rows(
            [offer for offer in session.pending_money_gift_offers if offer.giver_user_id == current_user_id],
            participant_name_by_id=participant_name_by_id,
        )
        incoming_sale_offers = _sale_offer_view_rows(
            [offer for offer in session.pending_sale_offers if offer.buyer_user_id == current_user_id],
            participant_name_by_id=participant_name_by_id,
        )
        outgoing_sale_offers = _sale_offer_view_rows(
            [offer for offer in session.pending_sale_offers if offer.seller_user_id == current_user_id],
            participant_name_by_id=participant_name_by_id,
        )
        trial_result_notice = session.latest_public_notice or ""
        private_trial_notice = ""
        if session.latest_private_notice_user_id == current_user_id and session.latest_private_notice_message:
            private_trial_notice = session.latest_private_notice_message
        game_result_notice = ""
        if session.status == "ended" and session.winning_faction:
            if session.winning_faction == "Merchant" and session.winning_user_id:
                winner_name = _display_name_for_user(participant_name_by_id, session.winning_user_id)
                game_result_notice = f"Winner: {winner_name} (Merchant)."
            else:
                game_result_notice = f"Winner: {session.winning_faction}."
        police_mob_kills_allowed = session.total_mob_participants_at_start // 2
        police_brutality_exceeded = session.police_mob_kills_count > police_mob_kills_allowed
        superpower_panel = _build_superpower_panel(
            session,
            current_user_id=current_user_id,
            current_participant=current_participant,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        protective_custody_panel = _build_protective_custody_panel(
            session,
            current_user_id=current_user_id,
            actor_is_moderator=actor_is_moderator,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        asset_freeze_panel = _build_asset_freeze_panel(
            session,
            current_user_id=current_user_id,
            actor_is_moderator=actor_is_moderator,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        sergeant_capture_panel = _build_sergeant_capture_panel(
            session,
            current_user_id=current_user_id,
            actor_is_moderator=actor_is_moderator,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        felon_escape_panel = _build_felon_escape_panel(
            session,
            current_user_id=current_user_id,
            actor_is_moderator=actor_is_moderator,
            participant_name_by_id=participant_name_by_id,
            now_epoch_seconds=now_epoch_seconds,
        )
        moderator_latest_jury_usernames = []
        if page.is_moderator and session.latest_jury_log_user_ids:
            moderator_latest_jury_usernames = [
                _display_name_for_user(participant_name_by_id, user_id) for user_id in session.latest_jury_log_user_ids
            ]
        mob_secret_word_panel = {
            "show": False,
            "secret_word": "",
            "viewer_label": "",
        }
        rooms_inbound = getattr(container, "rooms_inbound_port", None)
        if rooms_inbound is not None:
            try:
                room_details = rooms_inbound.get_room_details(session.room_id)
                secret_mob_word = str(room_details.secret_mob_word or "").strip()
                viewer_is_mob_player = (
                    current_participant is not None
                    and current_participant.faction == "Mob"
                )
                viewer_is_moderator_screen = bool(page.is_moderator)
                if secret_mob_word and (viewer_is_moderator_screen or viewer_is_mob_player):
                    mob_secret_word_panel = {
                        "show": True,
                        "secret_word": secret_mob_word,
                        "viewer_label": "Moderator"
                        if viewer_is_moderator_screen
                        else "Mob Faction",
                    }
            except Exception:
                mob_secret_word_panel = {
                    "show": False,
                    "secret_word": "",
                    "viewer_label": "",
                }

        view_tabs: list[dict[str, str | bool]] = []
        if actor_is_moderator and dev_mode_enabled:
            view_tabs.append({
                "label": "Moderator",
                "href": _game_detail_url(game_id=session.game_id),
                "is_active": not is_view_as_mode,
            })
            for participant in session.participants:
                label = participant.role_name
                if str(participant.user_id).startswith("dev-seat-"):
                    label = f"{label} [Dev]"
                view_tabs.append(
                    {
                        "label": label,
                        "href": _game_detail_url(
                            game_id=session.game_id,
                            as_user_id=participant.user_id,
                            simulate_actions=simulate_actions_enabled,
                        ),
                        "is_active": participant.user_id == current_user_id,
                        "is_ghost_view_player": _participant_has_ghost_view(session, participant),
                    }
                )
        viewed_role_name = ""
        viewed_role_image_url = ""
        if actor_is_moderator and not is_view_as_mode:
            viewed_role_name = "Moderator"
        elif is_view_as_mode and current_participant is not None:
            viewed_role_name = current_participant.role_name
        if viewed_role_name and viewed_role_name != "Moderator":
            viewed_role_image_url = _role_ability_image_url(viewed_role_name)

        return render(
            request,
            "gameplay/detail.html",
            {
                "page": page,
                "actor_is_moderator": actor_is_moderator,
                "ghost_view_enabled": ghost_view_enabled,
                "dev_mode_enabled": dev_mode_enabled,
                "current_user_id": current_user_id,
                "is_view_as_mode": is_view_as_mode,
                "simulate_actions_enabled": simulate_actions_enabled,
                "view_tabs": view_tabs,
                "viewed_role_name": viewed_role_name,
                "viewed_role_image_url": viewed_role_image_url,
                "can_submit_accused_selection": can_submit_accused_selection,
                "defer_accused_overlay_for_leadership_notice": defer_accused_overlay_for_leadership_notice,
                "accused_candidate_rows": accused_candidate_rows,
                "jury_prompt": jury_prompt,
                "moderator_trial_control": moderator_trial_control,
                "pending_trial_murdered_username": pending_trial_murdered_username,
                "pending_trial_current_responder_username": pending_trial_current_responder_username,
                "trial_result_notice": trial_result_notice,
                "private_trial_notice": private_trial_notice,
                "viewer_notifications": viewer_notifications,
                "viewer_notification_history": viewer_notification_history,
                "game_result_notice": game_result_notice,
                "police_mob_kills_count": session.police_mob_kills_count,
                "police_mob_kills_allowed": police_mob_kills_allowed,
                "police_brutality_exceeded": police_brutality_exceeded,
                "is_current_user_merchant": is_current_user_merchant,
                "merchant_supply_items": merchant_supply_items,
                "merchant_inventory_items": merchant_inventory_items,
                "merchant_sale_targets": merchant_sale_targets,
                "merchant_money_balance": merchant_money_balance,
                "merchant_money_goal": merchant_money_goal,
                "show_player_wallet": show_player_wallet,
                "show_player_inventory": show_player_inventory,
                "use_player_phone_layout": use_player_phone_layout,
                "player_money_balance": player_money_balance,
                "player_inventory_items": player_inventory_items,
                "player_role_name": player_role_name,
                "player_role_label": player_role_label,
                "player_role_image_url": player_role_image_url,
                "can_self_report_murder": can_self_report_murder,
                "self_report_murderer_rows": self_report_murderer_rows,
                "player_gift_targets": player_gift_targets,
                "incoming_gift_offers": incoming_gift_offers,
                "outgoing_gift_offers": outgoing_gift_offers,
                "incoming_money_gift_offers": incoming_money_gift_offers,
                "outgoing_money_gift_offers": outgoing_money_gift_offers,
                "incoming_sale_offers": incoming_sale_offers,
                "outgoing_sale_offers": outgoing_sale_offers,
                "superpower_panel": superpower_panel,
                "protective_custody_panel": protective_custody_panel,
                "asset_freeze_panel": asset_freeze_panel,
                "sergeant_capture_panel": sergeant_capture_panel,
                "felon_escape_panel": felon_escape_panel,
                "moderator_latest_jury_usernames": moderator_latest_jury_usernames,
                "mob_secret_word_panel": mob_secret_word_panel,
                "game_plan_steps": _game_plan_steps(),
                "game_state_poll_interval_seconds": container.room_state_poll_interval_seconds,
                "can_view_accused_selection": can_view_accused_selection,
            },
        )
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect("web-lobby")


@login_required(login_url="/auth/")
def game_info(request: HttpRequest) -> HttpResponse:
    game_id = _get_active_game_id(request)
    if not game_id:
        messages.info(request, "No active game is selected yet.")
        return redirect("web-lobby")

    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _current_user_id(request)
        is_participant = any(participant.user_id == actor_user_id for participant in session.participants)
        is_moderator = session.moderator_user_id == actor_user_id
        if not is_participant and not is_moderator:
            messages.error(request, "You do not have access to this game.")
            _clear_active_game_session(request)
            return redirect("web-lobby")

        _set_active_game_session(request, game_id=session.game_id, room_id=session.room_id)
        page = build_gameplay_page_view(session, actor_user_id)
        return render(
            request,
            "gameplay/game_info.html",
            {
                "page": page,
            },
        )
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect("web-lobby")


@login_required(login_url="/auth/")
def exit_game(request: HttpRequest, game_id: str) -> HttpResponse:
    actor_user_id = _current_user_id(request)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        if session.status == "ended" and session.moderator_user_id == actor_user_id:
            rooms_inbound = getattr(container, "rooms_inbound_port", None)
            if rooms_inbound is not None:
                rooms_inbound.delete_room(
                    DeleteRoomCommand(
                        room_id=session.room_id,
                        requested_by_user_id=actor_user_id,
                    )
                )
        _clear_active_game_session(request)
    except Exception:
        _clear_active_game_session(request)
    return redirect("web-lobby")


@login_required(login_url="/auth/")
def report_death(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        dto = ReportDeathRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "murdered_user_id": request.POST.get("murdered_user_id", ""),
                "reported_by_user_id": _current_user_id(request),
                "expected_version": request.POST.get("expected_version", ""),
                "murderer_user_id": request.POST.get("murderer_user_id", ""),
                "attack_classification": request.POST.get("attack_classification", ""),
            }
        )
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        gameplay_inbound.report_death(
            ReportDeathCommand(
                game_id=dto.game_id,
                murdered_user_id=dto.murdered_user_id,
                reported_by_user_id=dto.reported_by_user_id,
                expected_version=dto.expected_version,
                murderer_user_id=dto.murderer_user_id,
                attack_classification=dto.attack_classification,
            )
        )
        messages.success(request, "Death reported.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def advance_accused_selection_timeout(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        dto = AdvanceAccusedSelectionTimeoutRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "requested_by_user_id": _current_user_id(request),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        gameplay_inbound.advance_accused_selection_timeout(
            AdvanceAccusedSelectionTimeoutCommand(
                game_id=dto.game_id,
                requested_by_user_id=dto.requested_by_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Accused-selection timeout advanced.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)




@login_required(login_url="/auth/")
def submit_accused_selection(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        selected_by_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = SubmitAccusedSelectionRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "selected_by_user_id": selected_by_user_id,
                "accused_user_id": request.POST.get("accused_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.submit_accused_selection(
            SubmitAccusedSelectionCommand(
                game_id=dto.game_id,
                selected_by_user_id=dto.selected_by_user_id,
                accused_user_id=dto.accused_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Accused player selected.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def submit_trial_vote(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        voter_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = SubmitTrialVoteRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "voter_user_id": voter_user_id,
                "vote": request.POST.get("vote", ""),
                "expected_version": request.POST.get("expected_version", ""),
                "vote_slot": request.POST.get("vote_slot", "jury"),
            }
        )
        gameplay_inbound.submit_trial_vote(
            SubmitTrialVoteCommand(
                game_id=dto.game_id,
                voter_user_id=dto.voter_user_id,
                vote=dto.vote,
                expected_version=dto.expected_version,
                vote_slot=dto.vote_slot,
            )
        )
        messages.success(request, "Trial vote submitted.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_don_silence(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        session = container.gameplay_inbound_port.get_game_details(game_id)
        resolved_actor_user_id = _resolve_action_user_id(
            request,
            session=session,
            dev_mode_enabled=container.room_dev_mode,
        )
        dto = ActivateDonSilenceRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": resolved_actor_user_id,
                "target_user_id": request.POST.get("target_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        container.gameplay_inbound_port.activate_don_silence(
            ActivateDonSilenceCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                target_user_id=dto.target_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Intimidation armed.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_underboss_jury_override(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        session = container.gameplay_inbound_port.get_game_details(game_id)
        resolved_actor_user_id = _resolve_action_user_id(
            request,
            session=session,
            dev_mode_enabled=container.room_dev_mode,
        )
        dto = ActivateUnderBossJuryOverrideRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": resolved_actor_user_id,
                "removed_juror_user_id": request.POST.get("removed_juror_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        container.gameplay_inbound_port.activate_underboss_jury_override(
            ActivateUnderBossJuryOverrideCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                removed_juror_user_id=dto.removed_juror_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Jury manipulated.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_kingpin_reduce_clock(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        session = container.gameplay_inbound_port.get_game_details(game_id)
        resolved_actor_user_id = _resolve_action_user_id(
            request,
            session=session,
            dev_mode_enabled=container.room_dev_mode,
        )
        dto = ActivateKingpinReduceClockRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": resolved_actor_user_id,
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        container.gameplay_inbound_port.activate_kingpin_reduce_clock(
            ActivateKingpinReduceClockCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "15-second jury timer started.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_gangster_tamper(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        session = container.gameplay_inbound_port.get_game_details(game_id)
        resolved_actor_user_id = _resolve_action_user_id(
            request,
            session=session,
            dev_mode_enabled=container.room_dev_mode,
        )
        dto = ActivateGangsterTamperRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": resolved_actor_user_id,
                "target_user_id": request.POST.get("target_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound = container.gameplay_inbound_port
        gameplay_inbound.activate_gangster_tamper(
            ActivateGangsterTamperCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                target_user_id=dto.target_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Tamper activated.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_street_thug_steal(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateStreetThugStealRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "target_user_id": request.POST.get("target_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_street_thug_steal(
            ActivateStreetThugStealCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                target_user_id=dto.target_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Steal resolved.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_deputy_protective_custody(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateDeputyProtectiveCustodyRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "target_user_id": request.POST.get("target_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_deputy_protective_custody(
            ActivateDeputyProtectiveCustodyCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                target_user_id=dto.target_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Protective custody activated.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_sheriff_view_jury_log(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateSheriffViewJuryLogRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        container.gameplay_inbound_port.activate_sheriff_view_jury_log(
            ActivateSheriffViewJuryLogCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Jury log viewed.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_captain_asset_freeze(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateCaptainAssetFreezeRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "target_user_id": request.POST.get("target_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_captain_asset_freeze(
            ActivateCaptainAssetFreezeCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                target_user_id=dto.target_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Asset freeze activated.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_lieutenant_information_briefcase(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateLieutenantInformationBriefcaseRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_lieutenant_information_briefcase(
            ActivateLieutenantInformationBriefcaseCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Information briefcase opened.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_sergeant_capture(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateSergeantCaptureRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "target_user_id": request.POST.get("target_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_sergeant_capture(
            ActivateSergeantCaptureCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                target_user_id=dto.target_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Capture activated.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_detective_investigation(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateDetectiveInvestigationRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "target_user_id": request.POST.get("target_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_detective_investigation(
            ActivateDetectiveInvestigationCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                target_user_id=dto.target_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Investigation started.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_smuggler_smuggle(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateSmugglerSmuggleRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "target_user_id": request.POST.get("target_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_smuggler_smuggle(
            ActivateSmugglerSmuggleCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                target_user_id=dto.target_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Smuggle resolved.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_gun_runner_charisma(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateGunRunnerCharismaRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_gun_runner_charisma(
            ActivateGunRunnerCharismaCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Charisma activated.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_supplier_acquire(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateSupplierAcquireRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "target_user_id": request.POST.get("target_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_supplier_acquire(
            ActivateSupplierAcquireCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                target_user_id=dto.target_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Acquire resolved.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_inspector_record_inspection(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateInspectorRecordInspectionRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "target_user_id": request.POST.get("target_user_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_inspector_record_inspection(
            ActivateInspectorRecordInspectionCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                target_user_id=dto.target_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Record inspection started.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_police_officer_confiscation(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivatePoliceOfficerConfiscationRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_police_officer_confiscation(
            ActivatePoliceOfficerConfiscationCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Confiscation armed.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_made_man_skip_middle_man(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateMadeManSkipMiddleManRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "classification": request.POST.get("classification", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_made_man_skip_middle_man(
            ActivateMadeManSkipMiddleManCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                classification=dto.classification,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Skip Middle Man completed.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def activate_merchant_wholesale_order(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        actor_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = ActivateMerchantWholesaleOrderRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "actor_user_id": actor_user_id,
                "classification": request.POST.get("classification", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.activate_merchant_wholesale_order(
            ActivateMerchantWholesaleOrderCommand(
                game_id=dto.game_id,
                actor_user_id=dto.actor_user_id,
                classification=dto.classification,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Wholesale Order completed.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def start_trial_voting(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        dto = AllowTrialVotingRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "requested_by_user_id": _current_user_id(request),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        gameplay_inbound.allow_trial_voting(
            AllowTrialVotingCommand(
                game_id=dto.game_id,
                requested_by_user_id=dto.requested_by_user_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Jury voting is now active.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def buy_from_supply(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        buyer_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = BuyFromSupplyRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "buyer_user_id": buyer_user_id,
                "classification": request.POST.get("classification", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.buy_from_supply(
            BuyFromSupplyCommand(
                game_id=dto.game_id,
                buyer_user_id=dto.buyer_user_id,
                classification=dto.classification,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Item purchased from central supply.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def set_inventory_resale_price(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        seller_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = SetInventoryResalePriceRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "seller_user_id": seller_user_id,
                "inventory_item_id": request.POST.get("inventory_item_id", ""),
                "resale_price": request.POST.get("resale_price", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.set_inventory_resale_price(
            SetInventoryResalePriceCommand(
                game_id=dto.game_id,
                seller_user_id=dto.seller_user_id,
                inventory_item_id=dto.inventory_item_id,
                resale_price=dto.resale_price,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Resale price updated.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def sell_inventory_item(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        seller_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = SellInventoryItemRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "seller_user_id": seller_user_id,
                "buyer_user_id": request.POST.get("buyer_user_id", ""),
                "inventory_item_id": request.POST.get("inventory_item_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.sell_inventory_item(
            SellInventoryItemCommand(
                game_id=dto.game_id,
                seller_user_id=dto.seller_user_id,
                buyer_user_id=dto.buyer_user_id,
                inventory_item_id=dto.inventory_item_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Sale offer sent to player.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def sell_inventory_to_supply(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        seller_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = SellInventoryToSupplyRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "seller_user_id": seller_user_id,
                "inventory_item_id": request.POST.get("inventory_item_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.sell_inventory_to_supply(
            SellInventoryToSupplyCommand(
                game_id=dto.game_id,
                seller_user_id=dto.seller_user_id,
                inventory_item_id=dto.inventory_item_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Item sold to central supply.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def offer_gift_item(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        giver_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = OfferGiftItemRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "giver_user_id": giver_user_id,
                "receiver_user_id": request.POST.get("receiver_user_id", ""),
                "inventory_item_id": request.POST.get("inventory_item_id", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.offer_gift_item(
            OfferGiftItemCommand(
                game_id=dto.game_id,
                giver_user_id=dto.giver_user_id,
                receiver_user_id=dto.receiver_user_id,
                inventory_item_id=dto.inventory_item_id,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Gift offer sent.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def give_money(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        giver_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = GiveMoneyRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "giver_user_id": giver_user_id,
                "receiver_user_id": request.POST.get("receiver_user_id", ""),
                "amount": request.POST.get("amount", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.give_money(
            GiveMoneyCommand(
                game_id=dto.game_id,
                giver_user_id=dto.giver_user_id,
                receiver_user_id=dto.receiver_user_id,
                amount=dto.amount,
                expected_version=dto.expected_version,
            )
        )
        messages.success(request, "Money gift offer sent.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def respond_money_gift_offer(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        receiver_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = RespondMoneyGiftOfferRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "receiver_user_id": receiver_user_id,
                "money_gift_offer_id": request.POST.get("money_gift_offer_id", ""),
                "accept": request.POST.get("accept", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.respond_money_gift_offer(
            RespondMoneyGiftOfferCommand(
                game_id=dto.game_id,
                receiver_user_id=dto.receiver_user_id,
                money_gift_offer_id=dto.money_gift_offer_id,
                accept=dto.accept,
                expected_version=dto.expected_version,
            )
        )
        if dto.accept:
            messages.success(request, "Money gift accepted.")
        else:
            messages.info(request, "Money gift declined.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def respond_sale_offer(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        buyer_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = RespondSaleOfferRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "buyer_user_id": buyer_user_id,
                "sale_offer_id": request.POST.get("sale_offer_id", ""),
                "accept": request.POST.get("accept", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.respond_sale_offer(
            RespondSaleOfferCommand(
                game_id=dto.game_id,
                buyer_user_id=dto.buyer_user_id,
                sale_offer_id=dto.sale_offer_id,
                accept=dto.accept,
                expected_version=dto.expected_version,
            )
        )
        if dto.accept:
            messages.success(request, "Purchase accepted.")
        else:
            messages.info(request, "Purchase declined.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)


@login_required(login_url="/auth/")
def respond_gift_offer(request: HttpRequest, game_id: str) -> HttpResponse:
    if request.method != "POST":
        return _redirect_to_game_detail_with_context(request, game_id=game_id)
    try:
        container = get_container()
        gameplay_inbound = container.gameplay_inbound_port
        session = gameplay_inbound.get_game_details(game_id)
        receiver_user_id = _resolve_action_user_id(request, session=session, dev_mode_enabled=container.room_dev_mode)
        dto = RespondGiftOfferRequestDTO.from_payload(
            {
                "method": request.method,
                "game_id": game_id,
                "receiver_user_id": receiver_user_id,
                "gift_offer_id": request.POST.get("gift_offer_id", ""),
                "accept": request.POST.get("accept", ""),
                "expected_version": request.POST.get("expected_version", ""),
            }
        )
        gameplay_inbound.respond_gift_offer(
            RespondGiftOfferCommand(
                game_id=dto.game_id,
                receiver_user_id=dto.receiver_user_id,
                gift_offer_id=dto.gift_offer_id,
                accept=dto.accept,
                expected_version=dto.expected_version,
            )
        )
        if dto.accept:
            messages.success(request, "Gift accepted.")
        else:
            messages.info(request, "Gift declined.")
    except Exception as exc:
        messages.error(request, str(exc))
    return _redirect_to_game_detail_with_context(request, game_id=game_id)
