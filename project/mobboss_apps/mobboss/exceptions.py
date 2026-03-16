"""Shared API problem-details exceptions and mapping helpers.

RFC 7807: https://datatracker.ietf.org/doc/html/rfc7807
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.http import HttpRequest, JsonResponse

PROBLEM_TYPE_BASE = "https://mobboss.dev/problems"


def problem_type(slug: str) -> str:
    return f"{PROBLEM_TYPE_BASE}/{slug}"


@dataclass(eq=False)
class ProblemDetailsException(Exception):
    status: int
    title: str
    detail: str
    type: str = field(default_factory=lambda: problem_type("about-blank"))
    code: str | None = None
    extensions: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.detail


class BadRequestProblem(ProblemDetailsException):
    def __init__(self, detail: str, code: str = "bad_request") -> None:
        super().__init__(
            status=400,
            title="Bad Request",
            detail=detail,
            type=problem_type("bad-request"),
            code=code,
        )


class UnauthorizedProblem(ProblemDetailsException):
    def __init__(self, detail: str = "Authentication required.", code: str = "unauthorized") -> None:
        super().__init__(
            status=401,
            title="Unauthorized",
            detail=detail,
            type=problem_type("unauthorized"),
            code=code,
        )


class ForbiddenProblem(ProblemDetailsException):
    def __init__(self, detail: str = "You do not have permission for this action.", code: str = "forbidden") -> None:
        super().__init__(
            status=403,
            title="Forbidden",
            detail=detail,
            type=problem_type("forbidden"),
            code=code,
        )


class NotFoundProblem(ProblemDetailsException):
    def __init__(self, detail: str = "Resource not found.", code: str = "not_found") -> None:
        super().__init__(
            status=404,
            title="Not Found",
            detail=detail,
            type=problem_type("not-found"),
            code=code,
        )


class ConflictProblem(ProblemDetailsException):
    def __init__(self, detail: str, code: str = "conflict", extensions: dict[str, Any] | None = None) -> None:
        super().__init__(
            status=409,
            title="Conflict",
            detail=detail,
            type=problem_type("conflict"),
            code=code,
            extensions=extensions,
        )


class UnprocessableEntityProblem(ProblemDetailsException):
    def __init__(self, detail: str, code: str = "invalid_request") -> None:
        super().__init__(
            status=422,
            title="Unprocessable Entity",
            detail=detail,
            type=problem_type("unprocessable-entity"),
            code=code,
        )


def _problem_payload(
    *,
    type_value: str,
    title: str,
    status: int,
    detail: str,
    instance: str | None,
    code: str | None = None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": type_value,
        "title": title,
        "status": status,
        "detail": detail,
    }
    if instance:
        payload["instance"] = instance
    if code:
        payload["code"] = code
    if extensions:
        payload.update(extensions)
    return payload


def problem_details_from_exception(exc: Exception, request: HttpRequest | None = None) -> tuple[dict[str, Any], int]:
    instance = request.get_full_path() if request is not None else None

    if isinstance(exc, ProblemDetailsException):
        payload = _problem_payload(
            type_value=exc.type,
            title=exc.title,
            status=exc.status,
            detail=exc.detail,
            instance=instance,
            code=exc.code,
            extensions=exc.extensions,
        )
        return payload, exc.status

    if isinstance(exc, PermissionError):
        payload = _problem_payload(
            type_value=problem_type("forbidden"),
            title="Forbidden",
            status=403,
            detail=str(exc),
            instance=instance,
            code="forbidden",
        )
        return payload, 403

    if isinstance(exc, KeyError):
        payload = _problem_payload(
            type_value=problem_type("bad-request"),
            title="Bad Request",
            status=400,
            detail=f"Missing required field: {str(exc)!r}",
            instance=instance,
            code="bad_request",
        )
        return payload, 400

    if isinstance(exc, ValueError):
        payload = _problem_payload(
            type_value=problem_type("unprocessable-entity"),
            title="Unprocessable Entity",
            status=422,
            detail=str(exc),
            instance=instance,
            code="invalid_request",
        )
        return payload, 422

    payload = _problem_payload(
        type_value=problem_type("internal"),
        title="Internal Server Error",
        status=500,
        detail="Unexpected error.",
        instance=instance,
        code="internal_error",
    )
    return payload, 500


def problem_details_response(exc: Exception, request: HttpRequest | None = None) -> JsonResponse:
    payload, status = problem_details_from_exception(exc, request=request)
    return JsonResponse(payload, status=status, content_type="application/problem+json")
