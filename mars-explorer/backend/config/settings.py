"""Django settings for the MARS EXPLORER backend.

Configuration comes from environment variables (optionally loaded from backend/.env).
See backend/.env.example.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or os.environ.get("DJANGO_TESTING") == "1":
        SECRET_KEY = "insecure-local-development-key-do-not-use-in-production"
    else:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DEBUG is False.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.core",
    "apps.datasets",
    "apps.missions",
    "apps.hazards",
    "apps.terrain",
    "apps.routing",
    "apps.planets",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- CORS: only the configured frontend origin may call the API from a browser.
CORS_ALLOWED_ORIGINS = env_list("FRONTEND_ORIGIN", "http://127.0.0.1:5173,http://localhost:5173")
# Terrain render metadata headers must be readable by the frontend.
CORS_EXPOSE_HEADERS = ["X-Visualization", "X-Value-Min", "X-Value-Max", "X-Value-Units", "X-Valid-Fraction", "X-Dataset"]

# --- Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # First technical version: no authentication yet (local single-user tool).
    # Replace before exposing the API on any shared network.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 100,
}

# --- Mars scientific data directory (never inside frontend/public)
_data_dir = Path(os.environ.get("MARS_DATA_DIR", "../data/mars"))
MARS_DATA_DIR = (_data_dir if _data_dir.is_absolute() else (BASE_DIR / _data_dir)).resolve()

# Server-side only secret; not used by NASA Trek WMTS.
NASA_API_KEY = os.environ.get("NASA_API_KEY", "")

APP_VERSION = "0.1.0"

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
        "mars": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
