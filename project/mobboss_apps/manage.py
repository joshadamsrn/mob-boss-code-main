#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main() -> None:
    apps_root = Path(__file__).resolve().parent
    repo_root = apps_root.parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(apps_root) not in sys.path:
        sys.path.insert(0, str(apps_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.mobboss_apps.mobboss.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

