"""Inbound ports: gameplay use-case contracts."""

from __future__ import annotations

from typing import Protocol

from .internal import (
    ActivateDetectiveInvestigationCommand,
    ActivateInspectorRecordInspectionCommand,
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
    ActivateGangsterTamperCommand,
    ActivateDonSilenceCommand,
    ActivateKingpinReduceClockCommand,
    ActivateUnderBossJuryOverrideCommand,
    GiveMoneyCommand,
    KillGameCommand,
    MarkModeratorChatReadCommand,
    ModeratorAddFundsCommand,
    ModeratorTransferFundsCommand,
    ModeratorTransferInventoryItemCommand,
    OfferGiftItemCommand,
    RespondMoneyGiftOfferCommand,
    RespondGiftOfferCommand,
    RespondSaleOfferCommand,
    SendModeratorChatMessageCommand,
    SellInventoryItemCommand,
    SellInventoryToSupplyCommand,
    BuyFromSupplyCommand,
    AllowTrialVotingCommand,
    AdvanceAccusedSelectionTimeoutCommand,
    GameDetailsSnapshot,
    ReportDeathCommand,
    SetInventoryResalePriceCommand,
    StartSessionFromRoomCommand,
    SubmitAccusedSelectionCommand,
    SubmitTrialVoteCommand,
)


class GameplayInboundPort(Protocol):
    def start_session_from_room(self, command: StartSessionFromRoomCommand) -> GameDetailsSnapshot:
        ...

    def get_game_details(self, game_id: str) -> GameDetailsSnapshot:
        ...

    def report_death(self, command: ReportDeathCommand) -> GameDetailsSnapshot:
        ...

    def advance_accused_selection_timeout(self, command: AdvanceAccusedSelectionTimeoutCommand) -> GameDetailsSnapshot:
        ...

    def submit_accused_selection(self, command: SubmitAccusedSelectionCommand) -> GameDetailsSnapshot:
        ...

    def allow_trial_voting(self, command: AllowTrialVotingCommand) -> GameDetailsSnapshot:
        ...

    def submit_trial_vote(self, command: SubmitTrialVoteCommand) -> GameDetailsSnapshot:
        ...

    def activate_don_silence(self, command: ActivateDonSilenceCommand) -> GameDetailsSnapshot:
        ...

    def activate_underboss_jury_override(self, command: ActivateUnderBossJuryOverrideCommand) -> GameDetailsSnapshot:
        ...

    def activate_kingpin_reduce_clock(self, command: ActivateKingpinReduceClockCommand) -> GameDetailsSnapshot:
        ...

    def activate_gangster_tamper(self, command: ActivateGangsterTamperCommand) -> GameDetailsSnapshot:
        ...

    def activate_street_thug_steal(self, command: ActivateStreetThugStealCommand) -> GameDetailsSnapshot:
        ...

    def activate_smuggler_smuggle(self, command: ActivateSmugglerSmuggleCommand) -> GameDetailsSnapshot:
        ...

    def activate_gun_runner_charisma(self, command: ActivateGunRunnerCharismaCommand) -> GameDetailsSnapshot:
        ...

    def activate_supplier_acquire(self, command: ActivateSupplierAcquireCommand) -> GameDetailsSnapshot:
        ...

    def activate_merchant_wholesale_order(
        self, command: ActivateMerchantWholesaleOrderCommand
    ) -> GameDetailsSnapshot:
        ...

    def activate_deputy_protective_custody(self, command: ActivateDeputyProtectiveCustodyCommand) -> GameDetailsSnapshot:
        ...

    def activate_sheriff_view_jury_log(self, command: ActivateSheriffViewJuryLogCommand) -> GameDetailsSnapshot:
        ...

    def activate_captain_asset_freeze(self, command: ActivateCaptainAssetFreezeCommand) -> GameDetailsSnapshot:
        ...

    def activate_lieutenant_information_briefcase(
        self, command: ActivateLieutenantInformationBriefcaseCommand
    ) -> GameDetailsSnapshot:
        ...

    def activate_sergeant_capture(self, command: ActivateSergeantCaptureCommand) -> GameDetailsSnapshot:
        ...

    def activate_detective_investigation(
        self, command: ActivateDetectiveInvestigationCommand
    ) -> GameDetailsSnapshot:
        ...

    def activate_inspector_record_inspection(
        self, command: ActivateInspectorRecordInspectionCommand
    ) -> GameDetailsSnapshot:
        ...

    def activate_police_officer_confiscation(
        self, command: ActivatePoliceOfficerConfiscationCommand
    ) -> GameDetailsSnapshot:
        ...

    def activate_made_man_skip_middle_man(
        self, command: ActivateMadeManSkipMiddleManCommand
    ) -> GameDetailsSnapshot:
        ...

    def buy_from_supply(self, command: BuyFromSupplyCommand) -> GameDetailsSnapshot:
        ...

    def set_inventory_resale_price(self, command: SetInventoryResalePriceCommand) -> GameDetailsSnapshot:
        ...

    def sell_inventory_item(self, command: SellInventoryItemCommand) -> GameDetailsSnapshot:
        ...

    def sell_inventory_to_supply(self, command: SellInventoryToSupplyCommand) -> GameDetailsSnapshot:
        ...

    def kill_game(self, command: KillGameCommand) -> GameDetailsSnapshot:
        ...

    def offer_gift_item(self, command: OfferGiftItemCommand) -> GameDetailsSnapshot:
        ...

    def respond_gift_offer(self, command: RespondGiftOfferCommand) -> GameDetailsSnapshot:
        ...

    def respond_sale_offer(self, command: RespondSaleOfferCommand) -> GameDetailsSnapshot:
        ...

    def give_money(self, command: GiveMoneyCommand) -> GameDetailsSnapshot:
        ...

    def moderator_add_funds(self, command: ModeratorAddFundsCommand) -> GameDetailsSnapshot:
        ...

    def moderator_transfer_funds(self, command: ModeratorTransferFundsCommand) -> GameDetailsSnapshot:
        ...

    def moderator_transfer_inventory_item(
        self, command: ModeratorTransferInventoryItemCommand
    ) -> GameDetailsSnapshot:
        ...

    def respond_money_gift_offer(self, command: RespondMoneyGiftOfferCommand) -> GameDetailsSnapshot:
        ...

    def send_moderator_chat_message(self, command: SendModeratorChatMessageCommand) -> GameDetailsSnapshot:
        ...

    def mark_moderator_chat_read(self, command: MarkModeratorChatReadCommand) -> GameDetailsSnapshot:
        ...
