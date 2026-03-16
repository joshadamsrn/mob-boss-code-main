from django.urls import include, path
from project.mobboss_apps.rooms import views

urlpatterns = [
    path("", views.index, name="rooms-index"),
    path("create", views.create_room, name="rooms-create"),
    path("<str:room_id>/", views.detail, name="rooms-detail"),
    path("<str:room_id>/join", views.join_room, name="rooms-join"),
    path("<str:room_id>/leave", views.leave_room, name="rooms-leave"),
    path("<str:room_id>/dev/add-seat", views.add_dev_seat, name="rooms-dev-add-seat"),
    path("<str:room_id>/dev/remove-seat", views.remove_dev_seat, name="rooms-dev-remove-seat"),
    path("<str:room_id>/ready", views.set_ready, name="rooms-ready"),
    path("<str:room_id>/assign-role", views.assign_role, name="rooms-assign-role"),
    path("<str:room_id>/set-balance", views.set_balance, name="rooms-set-balance"),
    path("<str:room_id>/upsert-item", views.upsert_item, name="rooms-upsert-item"),
    path("<str:room_id>/deactivate-item/<str:classification>", views.deactivate_item, name="rooms-deactivate-item"),
    path("<str:room_id>/launch", views.launch_game, name="rooms-launch"),
    path("<str:room_id>/shuffle-roles", views.shuffle_roles, name="rooms-shuffle-roles"),
    path("<str:room_id>/delete", views.delete_room, name="rooms-delete"),
    path("v1/", include("project.mobboss_apps.rooms.v1_urls")),
]

