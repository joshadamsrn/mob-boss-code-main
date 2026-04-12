from django.urls import path
from project.mobboss_apps.web import views

urlpatterns = [
    path("", views.index, name="web-lobby"),
    path("how-to-play/", views.how_to_play, name="web-how-to-play"),
    path("options/", views.options, name="web-options"),
    path("options/kill-game", views.kill_game, name="web-kill-game"),
    path("options/advance-accused-timeout", views.advance_accused_timeout, name="web-advance-accused-timeout"),
    path("options/moderator-report-death", views.moderator_report_death, name="web-moderator-report-death"),
    path("options/moderator-add-funds", views.moderator_add_funds, name="web-moderator-add-funds"),
    path("options/moderator-transfer-funds", views.moderator_transfer_funds, name="web-moderator-transfer-funds"),
    path(
        "options/moderator-transfer-inventory-item",
        views.moderator_transfer_inventory_item,
        name="web-moderator-transfer-inventory-item",
    ),
]
