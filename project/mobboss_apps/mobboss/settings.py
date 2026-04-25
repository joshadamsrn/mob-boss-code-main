from pathlib import Path
import os


def _split_csv_env(name: str, default: str = "") -> list[str]:
    raw_value = os.getenv(name, default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = _split_csv_env("DJANGO_ALLOWED_HOSTS", "*" if DEBUG else "localhost,127.0.0.1")
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "webpack_loader",
    "iam",
    "rooms",
    "gameplay",
    "economy",
    "notebook",
    "events",
    "moderation",
    "web",
    "operations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "project.mobboss_apps.mobboss.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "project.mobboss_apps.mobboss.wsgi.application"
ASGI_APPLICATION = "project.mobboss_apps.mobboss.asgi.application"

if DB_ENGINE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "mobboss"),
            "USER": os.getenv("POSTGRES_USER", "mobboss"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "mobboss"),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "TEST": {
                "NAME": ":memory:",
            },
        }
    }

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

WEBPACK_LOADER = {
    "DEFAULT": {
        "CACHE": not DEBUG,
        "BUNDLE_DIR_NAME": "dist/",
        "STATS_FILE": BASE_DIR / "webpack-stats.json",
        "POLL_INTERVAL": 0.1,
        "IGNORE": [r".+\\.hot-update.js", r".+\\.map"],
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_X_FORWARDED_HOST = os.getenv("DJANGO_USE_X_FORWARDED_HOST", "1") == "1"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = _split_csv_env("DJANGO_CSRF_TRUSTED_ORIGINS")

HTTPS_ENABLED = os.getenv("DJANGO_HTTPS_ENABLED", "0") == "1"
SECURE_SSL_REDIRECT = HTTPS_ENABLED
SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0" if not HTTPS_ENABLED else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "1") == "1"
SECURE_HSTS_PRELOAD = os.getenv("DJANGO_SECURE_HSTS_PRELOAD", "1") == "1"
SECURE_REFERRER_POLICY = os.getenv("DJANGO_SECURE_REFERRER_POLICY", "same-origin")

# Room dev/testing controls.
ROOM_DEV_MODE = os.getenv("ROOM_DEV_MODE", "0") == "1"
ROOM_MIN_LAUNCH_PLAYERS = int(os.getenv("ROOM_MIN_LAUNCH_PLAYERS", "7"))
MODERATOR_ACCESS_CODE = os.getenv("MODERATOR_ACCESS_CODE", "adamspham")
MODERATOR_ACCESS_GROUP_NAME = os.getenv("MODERATOR_ACCESS_GROUP_NAME", "paid_moderator")
DEV_TOOLS_USERNAME = "devmode"
DEV_TOOLS_PASSWORD = "devmode1234"
DEV_TOOLS_GROUP_NAME = "dev_tools"
DEV_TOOLS_ROOM_MIN_LAUNCH_PLAYERS = int(os.getenv("DEV_TOOLS_ROOM_MIN_LAUNCH_PLAYERS", "2"))

# Room page polling configuration (seconds).
ROOM_STATE_POLL_INTERVAL_SECONDS = int(os.getenv("ROOM_STATE_POLL_INTERVAL_SECONDS", "5"))
ROOM_AUTO_SHUFFLE_INTERVAL_SECONDS = int(os.getenv("ROOM_AUTO_SHUFFLE_INTERVAL_SECONDS", "60"))
