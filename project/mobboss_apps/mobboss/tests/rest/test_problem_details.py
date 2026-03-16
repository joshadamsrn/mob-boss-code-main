import json
import sys
import unittest
from pathlib import Path

from django.conf import settings
from django.http import HttpRequest


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project.mobboss_apps.mobboss.decorators import problem_details  # noqa: E402
from project.mobboss_apps.mobboss.exceptions import (  # noqa: E402
    ConflictProblem,
    UnprocessableEntityProblem,
    problem_details_from_exception,
)

if not settings.configured:
    settings.configure(DEFAULT_CHARSET="utf-8")


class ProblemDetailsTests(unittest.TestCase):
    def test_problem_details_from_value_error(self) -> None:
        request = HttpRequest()
        request.path = "/rooms/v1/"

        payload, status = problem_details_from_exception(ValueError("Invalid payload"), request=request)

        self.assertEqual(status, 422)
        self.assertEqual(payload["title"], "Unprocessable Entity")
        self.assertEqual(payload["detail"], "Invalid payload")
        self.assertEqual(payload["code"], "invalid_request")
        self.assertEqual(payload["instance"], "/rooms/v1/")

    def test_problem_details_from_custom_problem_exception(self) -> None:
        request = HttpRequest()
        request.path = "/rooms/v1/"

        payload, status = problem_details_from_exception(
            UnprocessableEntityProblem("Room configuration is invalid."),
            request=request,
        )

        self.assertEqual(status, 422)
        self.assertEqual(payload["status"], 422)
        self.assertEqual(payload["detail"], "Room configuration is invalid.")
        self.assertEqual(payload["code"], "invalid_request")

    def test_problem_details_includes_custom_extensions(self) -> None:
        request = HttpRequest()
        request.path = "/gameplay/v1/games/g-1/report-death"

        payload, status = problem_details_from_exception(
            ConflictProblem(
                "stale version",
                code="version_conflict",
                extensions={"expected_version": 7, "current_version": 8},
            ),
            request=request,
        )

        self.assertEqual(status, 409)
        self.assertEqual(payload["code"], "version_conflict")
        self.assertEqual(payload["expected_version"], 7)
        self.assertEqual(payload["current_version"], 8)

    def test_problem_details_decorator_returns_rfc7807_response(self) -> None:
        @problem_details
        def boom(request: HttpRequest):
            raise ValueError("Malformed JSON.")

        request = HttpRequest()
        request.path = "/rooms/v1/"
        response = boom(request)
        body = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response["Content-Type"], "application/problem+json")
        self.assertEqual(body["type"], "https://mobboss.dev/problems/unprocessable-entity")
        self.assertEqual(body["title"], "Unprocessable Entity")
        self.assertEqual(body["detail"], "Malformed JSON.")
        self.assertEqual(body["status"], 422)


if __name__ == "__main__":
    unittest.main()
