from django.urls import path
from project.mobboss_apps.gameplay import v1_views

urlpatterns = [
    path("", v1_views.index, name="v1-index"),
    path("games/<str:game_id>", v1_views.GameDetailView.as_view(), name="gameplay-v1-detail"),
    path("games/<str:game_id>/report-death", v1_views.ReportDeathView.as_view(), name="gameplay-v1-report-death"),
    path(
        "games/<str:game_id>/advance-accused-selection-timeout",
        v1_views.AdvanceAccusedSelectionTimeoutView.as_view(),
        name="gameplay-v1-advance-accused-selection-timeout",
    ),
    path(
        "games/<str:game_id>/submit-accused-selection",
        v1_views.SubmitAccusedSelectionView.as_view(),
        name="gameplay-v1-submit-accused-selection",
    ),
    path(
        "games/<str:game_id>/buy-from-supply",
        v1_views.BuyFromSupplyView.as_view(),
        name="gameplay-v1-buy-from-supply",
    ),
    path(
        "games/<str:game_id>/set-inventory-resale-price",
        v1_views.SetInventoryResalePriceView.as_view(),
        name="gameplay-v1-set-inventory-resale-price",
    ),
    path(
        "games/<str:game_id>/sell-inventory-item",
        v1_views.SellInventoryItemView.as_view(),
        name="gameplay-v1-sell-inventory-item",
    ),
    path(
        "games/<str:game_id>/sell-inventory-to-supply",
        v1_views.SellInventoryToSupplyView.as_view(),
        name="gameplay-v1-sell-inventory-to-supply",
    ),
    path(
        "games/<str:game_id>/offer-gift-item",
        v1_views.OfferGiftItemView.as_view(),
        name="gameplay-v1-offer-gift-item",
    ),
    path(
        "games/<str:game_id>/give-money",
        v1_views.GiveMoneyView.as_view(),
        name="gameplay-v1-give-money",
    ),
    path(
        "games/<str:game_id>/respond-money-gift-offer",
        v1_views.RespondMoneyGiftOfferView.as_view(),
        name="gameplay-v1-respond-money-gift-offer",
    ),
    path(
        "games/<str:game_id>/respond-gift-offer",
        v1_views.RespondGiftOfferView.as_view(),
        name="gameplay-v1-respond-gift-offer",
    ),
    path(
        "games/<str:game_id>/respond-sale-offer",
        v1_views.RespondSaleOfferView.as_view(),
        name="gameplay-v1-respond-sale-offer",
    ),
]
