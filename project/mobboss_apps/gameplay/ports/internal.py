"""Internal ports: gameplay DTOs and data contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FactionName = Literal["Police", "Mob", "Merchant"]
LifeState = Literal["alive", "dead", "jailed"]
GamePhase = Literal["information", "accused_selection", "trial_voting", "boundary_resolution", "ended"]
GameStatus = Literal["in_progress", "paused", "ended"]
TrialVerdict = Literal["guilty", "innocent"]
LedgerEntryKind = Literal[
    "central_supply_purchase",
    "central_supply_buyback",
    "participant_sale",
    "supplier_acquire_cut",
    "money_gift",
    "moderator_adjustment",
    "street_thug_steal",
    "gun_runner_charisma_bonus",
    "murder_transfer",
    "conviction_transfer",
    "felon_escape_reset",
    "efj_bribe_transfer",
    "enforcer_bonus",
]
PlayerTransactionKind = Literal["sale", "money_gift", "item_gift", "item_theft"]

RoleName = Literal[
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
    "Mob Boss",
    "Don",
    "Under Boss",
    "Kingpin",
    "Enforcer",
    "Made Man",
    "Gangster",
    "Street Thug",
    "Felon",
    "Knife Hobo",
    "Arms Dealer",
    "Smuggler",
    "Merchant",
    "Gun Runner",
    "Supplier",
]


@dataclass(frozen=True)
class StartSessionParticipantInput:
    user_id: str
    username: str
    faction: FactionName
    role_name: RoleName
    rank: int
    starting_balance: int


@dataclass(frozen=True)
class StartSessionCatalogItemInput:
    classification: str
    display_name: str
    base_price: int
    image_path: str
    is_active: bool


@dataclass(frozen=True)
class StartSessionFromRoomCommand:
    room_id: str
    moderator_user_id: str
    launched_at_epoch_seconds: int
    participants: list[StartSessionParticipantInput]
    catalog: list[StartSessionCatalogItemInput]


@dataclass(frozen=True)
class ReportDeathCommand:
    game_id: str
    murdered_user_id: str
    reported_by_user_id: str
    attack_classification: str
    expected_version: int
    murderer_user_id: str | None = None


@dataclass(frozen=True)
class AdvanceAccusedSelectionTimeoutCommand:
    game_id: str
    requested_by_user_id: str
    expected_version: int




@dataclass(frozen=True)
class SubmitAccusedSelectionCommand:
    game_id: str
    selected_by_user_id: str
    accused_user_id: str
    expected_version: int


@dataclass(frozen=True)
class AllowTrialVotingCommand:
    game_id: str
    requested_by_user_id: str
    expected_version: int


@dataclass(frozen=True)
class SubmitTrialVoteCommand:
    game_id: str
    voter_user_id: str
    vote: TrialVerdict
    expected_version: int
    vote_slot: str = "jury"


@dataclass(frozen=True)
class ActivateDonSilenceCommand:
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateUnderBossJuryOverrideCommand:
    game_id: str
    actor_user_id: str
    removed_juror_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateKingpinReduceClockCommand:
    game_id: str
    actor_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateGangsterTamperCommand:
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateStreetThugStealCommand:
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateSmugglerSmuggleCommand:
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateGunRunnerCharismaCommand:
    game_id: str
    actor_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateSupplierAcquireCommand:
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateDeputyProtectiveCustodyCommand:
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateSheriffViewJuryLogCommand:
    game_id: str
    actor_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateCaptainAssetFreezeCommand:
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateLieutenantInformationBriefcaseCommand:
    game_id: str
    actor_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateSergeantCaptureCommand:
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateDetectiveInvestigationCommand:
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateInspectorRecordInspectionCommand:
    game_id: str
    actor_user_id: str
    target_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivatePoliceOfficerConfiscationCommand:
    game_id: str
    actor_user_id: str
    expected_version: int


@dataclass(frozen=True)
class ActivateMadeManSkipMiddleManCommand:
    game_id: str
    actor_user_id: str
    classification: str
    expected_version: int


@dataclass(frozen=True)
class ActivateMerchantWholesaleOrderCommand:
    game_id: str
    actor_user_id: str
    classification: str
    expected_version: int


@dataclass(frozen=True)
class BuyFromSupplyCommand:
    game_id: str
    buyer_user_id: str
    classification: str
    expected_version: int


@dataclass(frozen=True)
class SetInventoryResalePriceCommand:
    game_id: str
    seller_user_id: str
    inventory_item_id: str
    resale_price: int
    expected_version: int


@dataclass(frozen=True)
class SellInventoryItemCommand:
    game_id: str
    seller_user_id: str
    buyer_user_id: str
    inventory_item_id: str
    expected_version: int


@dataclass(frozen=True)
class SellInventoryToSupplyCommand:
    game_id: str
    seller_user_id: str
    inventory_item_id: str
    expected_version: int


@dataclass(frozen=True)
class RespondSaleOfferCommand:
    game_id: str
    buyer_user_id: str
    sale_offer_id: str
    accept: bool
    expected_version: int


@dataclass(frozen=True)
class KillGameCommand:
    game_id: str
    requested_by_user_id: str


@dataclass(frozen=True)
class OfferGiftItemCommand:
    game_id: str
    giver_user_id: str
    receiver_user_id: str
    inventory_item_id: str
    expected_version: int


@dataclass(frozen=True)
class RespondGiftOfferCommand:
    game_id: str
    receiver_user_id: str
    gift_offer_id: str
    accept: bool
    expected_version: int


@dataclass(frozen=True)
class GiveMoneyCommand:
    game_id: str
    giver_user_id: str
    receiver_user_id: str
    amount: int
    expected_version: int


@dataclass(frozen=True)
class ModeratorAddFundsCommand:
    game_id: str
    requested_by_user_id: str
    recipient_user_id: str
    amount: int
    expected_version: int


@dataclass(frozen=True)
class ModeratorTransferFundsCommand:
    game_id: str
    requested_by_user_id: str
    from_user_id: str
    to_user_id: str
    amount: int
    expected_version: int


@dataclass(frozen=True)
class ModeratorTransferInventoryItemCommand:
    game_id: str
    requested_by_user_id: str
    from_user_id: str
    to_user_id: str
    inventory_item_id: str
    expected_version: int


@dataclass(frozen=True)
class RespondMoneyGiftOfferCommand:
    game_id: str
    receiver_user_id: str
    money_gift_offer_id: str
    accept: bool
    expected_version: int


@dataclass(frozen=True)
class SendModeratorChatMessageCommand:
    game_id: str
    sender_user_id: str
    thread_user_id: str
    message_text: str
    expected_version: int


@dataclass(frozen=True)
class MarkModeratorChatReadCommand:
    game_id: str
    viewer_user_id: str
    thread_user_id: str
    expected_version: int


@dataclass(frozen=True)
class InventoryItemStateSnapshot:
    item_id: str
    classification: str
    display_name: str
    image_path: str
    acquisition_value: int
    resale_price: int


@dataclass(frozen=True)
class GiftOfferSnapshot:
    gift_offer_id: str
    giver_user_id: str
    receiver_user_id: str
    inventory_item_id: str
    item_display_name: str
    created_at_epoch_seconds: int


@dataclass(frozen=True)
class SaleOfferSnapshot:
    sale_offer_id: str
    seller_user_id: str
    buyer_user_id: str
    inventory_item_id: str
    item_display_name: str
    sale_price: int
    created_at_epoch_seconds: int


@dataclass(frozen=True)
class MoneyGiftOfferSnapshot:
    money_gift_offer_id: str
    giver_user_id: str
    receiver_user_id: str
    amount: int
    created_at_epoch_seconds: int


@dataclass(frozen=True)
class TrialStateSnapshot:
    murdered_user_id: str
    murderer_user_id: str | None
    accused_user_id: str | None
    accused_selection_cursor: list[str]
    accused_selection_deadline_epoch_seconds: int | None
    jury_user_ids: list[str]
    vote_deadline_epoch_seconds: int | None
    votes: list[dict[str, str]]
    verdict: TrialVerdict | None
    conviction_correct: bool | None
    resolution: str | None
    accused_by_user_id: str | None = None
    silenced_user_ids: list[str] = field(default_factory=list)
    gangster_tamper_target_user_id: str | None = None
    gangster_tamper_actor_user_id: str | None = None
    gangster_tamper_vote_deadline_epoch_seconds: int | None = None


@dataclass(frozen=True)
class ParticipantPowerStateSnapshot:
    don_silence_used: bool = False
    don_silence_target_user_id: str | None = None
    underboss_jury_override_used: bool = False
    kingpin_reduced_trial_keys: list[str] = field(default_factory=list)
    street_thug_steal_used: bool = False
    smuggler_smuggle_used: bool = False
    gun_runner_charisma_used: bool = False
    gun_runner_charisma_expires_at_epoch_seconds: int | None = None
    supplier_acquire_used: bool = False
    supplier_acquire_target_user_id: str | None = None
    deputy_protective_custody_used: bool = False
    sheriff_jury_log_views_used: int = 0
    sheriff_jury_log_visible_until_epoch_seconds: int | None = None
    sheriff_last_viewed_jury_user_ids: list[str] = field(default_factory=list)
    captain_asset_freeze_used: bool = False
    lieutenant_information_briefcase_used: bool = False
    lieutenant_briefcase_visible_until_epoch_seconds: int | None = None
    lieutenant_briefcase_alive_police_count: int = 0
    lieutenant_briefcase_alive_mob_count: int = 0
    lieutenant_briefcase_alive_merchant_count: int = 0
    sergeant_capture_used: bool = False
    detective_investigation_used: bool = False
    detective_investigation_visible_until_epoch_seconds: int | None = None
    detective_investigation_target_user_id: str | None = None
    detective_last_viewed_transaction_total: int = 0
    detective_last_viewed_transactions: list["PlayerTransactionSnapshot"] = field(default_factory=list)
    inspector_record_inspection_used: bool = False
    inspector_record_visible_until_epoch_seconds: int | None = None
    inspector_record_target_user_id: str | None = None
    inspector_last_viewed_role_name: str | None = None
    police_officer_confiscation_used: bool = False
    police_officer_confiscation_pending: bool = False
    cop_last_three_protection_used: bool = False
    enforcer_first_kill_bonus_used: bool = False
    made_man_skip_middle_man_used: bool = False
    merchant_wholesale_order_used: bool = False
    gangster_tamper_used: bool = False


@dataclass(frozen=True)
class NotificationEventSnapshot:
    event_id: str
    user_id: str
    message: str
    created_at_epoch_seconds: int


@dataclass(frozen=True)
class LedgerEntrySnapshot:
    entry_id: str
    entry_kind: LedgerEntryKind
    amount: int
    from_holder_id: str
    to_holder_id: str
    created_at_epoch_seconds: int
    note: str | None = None


@dataclass(frozen=True)
class LedgerStateSnapshot:
    circulating_currency_baseline: int
    checksum: str | None = None
    entries: list[LedgerEntrySnapshot] = field(default_factory=list)


@dataclass(frozen=True)
class PlayerTransactionSnapshot:
    transaction_id: str
    transaction_kind: PlayerTransactionKind
    sender_user_id: str
    recipient_user_id: str
    created_at_epoch_seconds: int
    money_amount: int = 0
    item_name: str | None = None


@dataclass(frozen=True)
class ParticipantStateSnapshot:
    user_id: str
    username: str
    faction: FactionName
    role_name: RoleName
    rank: int
    life_state: LifeState
    money_balance: int
    inventory: list[InventoryItemStateSnapshot] = field(default_factory=list)
    murdered_by_user_id: str | None = None
    accused_by_user_id: str | None = None
    convicted_by_user_ids: list[str] = field(default_factory=list)
    power_state: ParticipantPowerStateSnapshot = field(default_factory=ParticipantPowerStateSnapshot)


@dataclass(frozen=True)
class CatalogItemStateSnapshot:
    classification: str
    display_name: str
    base_price: int
    image_path: str
    is_active: bool


@dataclass(frozen=True)
class ModeratorChatMessageSnapshot:
    message_id: str
    sender_user_id: str
    body: str
    created_at_epoch_seconds: int


@dataclass(frozen=True)
class ModeratorChatThreadSnapshot:
    player_user_id: str
    unread_for_player_count: int = 0
    unread_for_moderator_count: int = 0
    messages: list[ModeratorChatMessageSnapshot] = field(default_factory=list)


@dataclass(frozen=True)
class GameDetailsSnapshot:
    game_id: str
    room_id: str
    moderator_user_id: str
    status: GameStatus
    phase: GamePhase
    round_number: int
    version: int
    launched_at_epoch_seconds: int
    ended_at_epoch_seconds: int | None
    participants: list[ParticipantStateSnapshot]
    catalog: list[CatalogItemStateSnapshot]
    pending_trial: TrialStateSnapshot | None
    last_progressed_at_epoch_seconds: int | None = None
    ledger: LedgerStateSnapshot = field(default_factory=lambda: LedgerStateSnapshot(circulating_currency_baseline=0))
    current_police_leader_user_id: str | None = None
    current_mob_leader_user_id: str | None = None
    winning_faction: FactionName | None = None
    winning_user_id: str | None = None
    latest_public_notice: str | None = None
    latest_private_notice_user_id: str | None = None
    latest_private_notice_message: str | None = None
    notification_feed: list[NotificationEventSnapshot] = field(default_factory=list)
    pending_gift_offers: list[GiftOfferSnapshot] = field(default_factory=list)
    pending_money_gift_offers: list[MoneyGiftOfferSnapshot] = field(default_factory=list)
    pending_sale_offers: list[SaleOfferSnapshot] = field(default_factory=list)
    total_mob_participants_at_start: int = 0
    police_mob_kills_count: int = 0
    protective_custody_user_id: str | None = None
    protective_custody_by_user_id: str | None = None
    protective_custody_expires_at_epoch_seconds: int | None = None
    asset_freeze_user_id: str | None = None
    asset_freeze_by_user_id: str | None = None
    asset_freeze_expires_at_epoch_seconds: int | None = None
    moderator_chat_version: int = 0
    moderator_chat_threads: list[ModeratorChatThreadSnapshot] = field(default_factory=list)
    sergeant_capture_user_id: str | None = None
    sergeant_capture_by_user_id: str | None = None
    sergeant_capture_expires_at_epoch_seconds: int | None = None
    felon_escape_user_id: str | None = None
    felon_escape_expires_at_epoch_seconds: int | None = None
    latest_jury_log_user_ids: list[str] = field(default_factory=list)
    player_transactions: list[PlayerTransactionSnapshot] = field(default_factory=list)


# Backward-compatible alias used by older call sites.
GameSessionSnapshot = GameDetailsSnapshot
