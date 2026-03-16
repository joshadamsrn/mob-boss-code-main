from django.urls import path
from project.mobboss_apps.gameplay import views

urlpatterns = [
    path("", views.index, name="gameplay-index"),
    path("<str:game_id>/", views.detail, name="gameplay-detail"),
    path("<str:game_id>/report-death", views.report_death, name="gameplay-report-death"),
    path(
        "<str:game_id>/advance-accused-selection-timeout",
        views.advance_accused_selection_timeout,
        name="gameplay-advance-accused-selection-timeout",
    ),
]

