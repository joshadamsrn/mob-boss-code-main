from django.urls import path
from project.mobboss_apps.rooms import v1_views

urlpatterns = [
    path("", v1_views.RoomsCollectionView.as_view(), name="rooms-v1-collection"),
    path("<str:room_id>", v1_views.RoomDetailView.as_view(), name="rooms-v1-detail"),
    path("<str:room_id>/join", v1_views.JoinRoomView.as_view(), name="rooms-v1-join"),
    path("<str:room_id>/leave", v1_views.LeaveRoomView.as_view(), name="rooms-v1-leave"),
    path("<str:room_id>/readiness", v1_views.ReadinessView.as_view(), name="rooms-v1-readiness"),
    path("<str:room_id>/roles/assign", v1_views.AssignRoleView.as_view(), name="rooms-v1-assign-role"),
    path("<str:room_id>/balances", v1_views.BalanceView.as_view(), name="rooms-v1-balance"),
    path("<str:room_id>/catalog", v1_views.CatalogCollectionView.as_view(), name="rooms-v1-catalog"),
    path("<str:room_id>/catalog/<str:classification>", v1_views.CatalogItemUpsertView.as_view(), name="rooms-v1-catalog-item"),
    path("<str:room_id>/catalog/<str:classification>/image", v1_views.CatalogItemImageView.as_view(), name="rooms-v1-catalog-image"),
    path("<str:room_id>/catalog/<str:classification>/deactivate", v1_views.CatalogItemDeactivateView.as_view(), name="rooms-v1-catalog-deactivate"),
    path("<str:room_id>/launch", v1_views.LaunchGameView.as_view(), name="rooms-v1-launch"),
    path("<str:room_id>/shuffle-roles", v1_views.ShuffleRolesView.as_view(), name="rooms-v1-shuffle-roles"),
    path("<str:room_id>/delete", v1_views.DeleteRoomView.as_view(), name="rooms-v1-delete"),
]

