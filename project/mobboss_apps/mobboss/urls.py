from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path("", include("project.mobboss_apps.web.urls")),
    path("auth/", include("project.mobboss_apps.iam.urls")),
    path("rooms/", include("project.mobboss_apps.rooms.urls")),
    path("games/", include("project.mobboss_apps.gameplay.urls")),
    path("gameplay/v1/", include("project.mobboss_apps.gameplay.v1_urls")),
    path("operations/", include("project.mobboss_apps.operations.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

