from django.urls import path
from project.mobboss_apps.economy import views

urlpatterns = [
    path("", views.index, name="index"),
]

