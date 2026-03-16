"""Shared decorators for view-layer concerns."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from django.http import HttpRequest, HttpResponse

from project.mobboss_apps.mobboss.exceptions import problem_details_response


def _find_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> HttpRequest | None:
    request = kwargs.get("request")
    if isinstance(request, HttpRequest):
        return request
    for arg in args:
        if isinstance(arg, HttpRequest):
            return arg
    return None


def problem_details(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Convert unhandled exceptions into RFC 7807 Problem Details responses."""

    @wraps(view_func)
    def wrapped(*args: Any, **kwargs: Any) -> HttpResponse:
        request = _find_request(args, kwargs)
        try:
            return view_func(*args, **kwargs)
        except Exception as exc:
            return problem_details_response(exc, request=request)

    return wrapped

