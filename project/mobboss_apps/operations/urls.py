from django.urls import path
from project.mobboss_apps.operations import views

urlpatterns = [
    path("", views.index, name="operations-index"),
    path("healthcheck", views.healthcheck, name="operations-healthcheck"),
    path("metrics", views.metrics, name="operations-metrics"),
]

