from django.urls import path
from project.mobboss_apps.events import views

urlpatterns = [
    path("", views.index, name="index"),
]

