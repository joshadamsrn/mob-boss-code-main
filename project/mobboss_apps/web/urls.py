from django.urls import path
from project.mobboss_apps.web import views

urlpatterns = [
    path("", views.index, name="web-lobby"),
]

