from django.urls import path
from project.mobboss_apps.iam import views

urlpatterns = [
    path("", views.index, name="iam-auth"),
    path("logout/", views.logout_view, name="iam-logout"),
]

