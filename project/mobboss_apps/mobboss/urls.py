from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic.base import RedirectView

urlpatterns = [
    path(
        "favicon.ico",
        RedirectView.as_view(url=settings.STATIC_URL + "characters/mob_boss.png", permanent=False),
    ),
    path(
        "apple-touch-icon.png",
        RedirectView.as_view(url=settings.STATIC_URL + "characters/mob_boss.png", permanent=False),
    ),
    path(
        "apple-touch-icon-precomposed.png",
        RedirectView.as_view(url=settings.STATIC_URL + "characters/mob_boss.png", permanent=False),
    ),
    path("", include("project.mobboss_apps.web.urls")),
    path("auth/", include("project.mobboss_apps.iam.urls")),
    path("rooms/", include("project.mobboss_apps.rooms.urls")),
    path("games/", include("project.mobboss_apps.gameplay.urls")),
    path("gameplay/v1/", include("project.mobboss_apps.gameplay.v1_urls")),
    path("operations/", include("project.mobboss_apps.operations.urls")),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
