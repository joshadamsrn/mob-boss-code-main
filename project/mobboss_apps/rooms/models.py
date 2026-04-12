from django.conf import settings
from django.db import models


class RoomSupplyPreset(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="room_supply_presets",
    )
    name = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "rooms"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.user_id})"
