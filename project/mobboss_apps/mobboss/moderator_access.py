"""Helpers for granting persistent moderator access to paid users."""

from __future__ import annotations

from django.conf import settings
from django.db import DatabaseError


def _moderator_access_group_name() -> str:
    return (
        str(getattr(settings, "MODERATOR_ACCESS_GROUP_NAME", "paid_moderator") or "paid_moderator").strip()
        or "paid_moderator"
    )


def _moderator_access_code() -> str:
    return str(getattr(settings, "MODERATOR_ACCESS_CODE", "") or "")


def moderator_access_code_is_valid(code: object) -> bool:
    expected_code = _moderator_access_code()
    if not expected_code:
        return False
    return str(code or "").strip() == expected_code


def user_can_create_moderated_room(user: object) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if bool(getattr(user, "has_moderator_access", False)):
        return True

    groups = getattr(user, "groups", None)
    if groups is None:
        return False
    try:
        return groups.filter(name=_moderator_access_group_name()).exists()
    except Exception:
        return False


def grant_moderator_access(user: object) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if user_can_create_moderated_room(user):
        return True

    try:
        from django.contrib.auth.models import Group

        group, _ = Group.objects.get_or_create(name=_moderator_access_group_name())
        user.groups.add(group)
    except DatabaseError:
        return False
    return True
