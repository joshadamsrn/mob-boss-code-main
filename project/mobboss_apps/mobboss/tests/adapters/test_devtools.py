import os
import sys
from pathlib import Path
from unittest.mock import patch

import django
from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.mobboss_apps.mobboss.settings")
django.setup()

from project.mobboss_apps.mobboss.devtools import (  # noqa: E402
    ensure_dev_tools_account,
    is_dev_tools_user,
)


class DevToolsAccountTests(TestCase):
    @override_settings(
        DEV_TOOLS_USERNAME="devmode-test",
        DEV_TOOLS_PASSWORD="devmode-pass-123",
        DEV_TOOLS_GROUP_NAME="dev_tools_test",
    )
    def test_ensure_dev_tools_account_creates_and_tags_user(self) -> None:
        ensure_dev_tools_account()

        user_model = get_user_model()
        user = user_model.objects.get(username="devmode-test")

        self.assertTrue(user.check_password("devmode-pass-123"))
        self.assertTrue(is_dev_tools_user(user))

    def test_ensure_dev_tools_account_uses_default_live_credentials(self) -> None:
        ensure_dev_tools_account()

        user_model = get_user_model()
        user = user_model.objects.get(username="devmode")

        self.assertTrue(user.check_password("devmode1234"))
        self.assertTrue(is_dev_tools_user(user))


class DevToolsAccountBootstrapFailureTests(SimpleTestCase):
    @override_settings(
        DEV_TOOLS_USERNAME="devmode-test",
        DEV_TOOLS_PASSWORD="devmode-pass-123",
        DEV_TOOLS_GROUP_NAME="dev_tools_test",
    )
    @patch("django.contrib.auth.models.Group.objects.get_or_create", side_effect=OperationalError("db unavailable"))
    def test_ensure_dev_tools_account_ignores_database_errors(self, _mock_get_or_create) -> None:
        ensure_dev_tools_account()
