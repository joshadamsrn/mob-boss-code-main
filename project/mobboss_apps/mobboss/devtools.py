"""Helpers for the dedicated dev-tools account."""

from __future__ import annotations

from django.conf import settings
from django.db import DatabaseError


def _dev_tools_username() -> str:
    return str(getattr(settings, "DEV_TOOLS_USERNAME", "") or "").strip()


def _dev_tools_password() -> str:
    return str(getattr(settings, "DEV_TOOLS_PASSWORD", "") or "")


def _dev_tools_group_name() -> str:
    return str(getattr(settings, "DEV_TOOLS_GROUP_NAME", "dev_tools") or "dev_tools").strip() or "dev_tools"


def dev_tools_account_configured() -> bool:
    return bool(_dev_tools_username() and _dev_tools_password())


def dev_tools_min_launch_players() -> int:
    raw_value = getattr(settings, "DEV_TOOLS_ROOM_MIN_LAUNCH_PLAYERS", 2)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = 2
    return max(1, min(value, 25))


def ensure_dev_tools_account() -> None:
    if not dev_tools_account_configured():
        return

    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group

    try:
        group, _ = Group.objects.get_or_create(name=_dev_tools_group_name())

        user_model = get_user_model()
        user, _ = user_model.objects.get_or_create(
            username=_dev_tools_username(),
            defaults={"is_active": True},
        )

        user_changed = False
        if not user.is_active:
            user.is_active = True
            user_changed = True
        if not user.check_password(_dev_tools_password()):
            user.set_password(_dev_tools_password())
            user_changed = True
        if user_changed:
            user.save()

        if not user.groups.filter(name=group.name).exists():
            user.groups.add(group)
    except DatabaseError:
        # Dev-tools bootstrap should never take down the auth page.
        return


def is_dev_tools_user(user: object) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if bool(getattr(user, "is_dev_tools_user", False)):
        return True

    groups = getattr(user, "groups", None)
    if groups is None:
        return False
    try:
        return groups.filter(name=_dev_tools_group_name()).exists()
    except Exception:
        return False


def user_dev_mode_enabled(*, user: object, room_dev_mode: bool) -> bool:
    return bool(room_dev_mode or is_dev_tools_user(user))
