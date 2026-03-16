from django.urls import path
from project.mobboss_apps.notebook import views

urlpatterns = [
    path("", views.index, name="index"),
]

