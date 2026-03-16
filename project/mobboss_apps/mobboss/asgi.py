import os
import sys
from pathlib import Path

from django.core.asgi import get_asgi_application

apps_root = Path(__file__).resolve().parents[1]
repo_root = Path(__file__).resolve().parents[3]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
if str(apps_root) not in sys.path:
    sys.path.insert(0, str(apps_root))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.mobboss_apps.mobboss.settings")
application = get_asgi_application()

