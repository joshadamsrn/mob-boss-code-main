from django.urls import path
from project.mobboss_apps.moderation import views

urlpatterns = [
    path("", views.index, name="index"),
]
