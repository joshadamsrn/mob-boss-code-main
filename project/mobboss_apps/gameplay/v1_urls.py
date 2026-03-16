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
]

