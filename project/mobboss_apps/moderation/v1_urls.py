from django.urls import path
from project.mobboss_apps.moderation import v1_views

urlpatterns = [
    path("", v1_views.index, name="v1-index"),
]
