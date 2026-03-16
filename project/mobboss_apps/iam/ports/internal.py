"""Internal ports: DTOs and data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IamAuthPageResult:
    login_form: Any
    signup_form: Any
    redirect_to: str | None = None


@dataclass(frozen=True)
class IamLogoutResult:
    redirect_to: str
