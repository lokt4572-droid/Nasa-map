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
    "apps.weather",
    "apps.geocoding",
    "apps.earth",
    "apps.ai",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Serves collected static files (admin) in production when whitenoise is installed.
    *(["whitenoise.middleware.WhiteNoiseMiddleware"] if __import__("importlib").util.find_spec("whitenoise") else []),
    "apps.core.middleware.PublicReadOnlyMiddleware",
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

def database_from_url(url: str) -> dict:
    """postgres://user:pass@host:port/name?sslmode=require -> Django settings (no extra dependency)."""
    from urllib.parse import parse_qs, unquote, urlparse

    u = urlparse(url)
    if u.scheme not in ("postgres", "postgresql", "postgis"):
        raise ValueError(f"Unsupported DATABASE_URL scheme {u.scheme!r} (use postgres://)")
    opts = {k: v[-1] for k, v in parse_qs(u.query).items()}
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(u.path.lstrip("/")),
        "USER": unquote(u.username or ""),
        "PASSWORD": unquote(u.password or ""),
        "HOST": u.hostname or "",
        "PORT": str(u.port or ""),
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
        "OPTIONS": opts,
    }


# PostgreSQL when DATABASE_URL is set (production); SQLite file for local development.
DATABASES = {
    "default": database_from_url(os.environ["DATABASE_URL"]) if os.environ.get("DATABASE_URL") else {
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
STATIC_ROOT = BASE_DIR / "staticfiles"  # collectstatic target (production)

# --- Production security (all from the environment; defaults are safe for local development)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")
if not DEBUG:
    # Behind a TLS-terminating proxy (Render, Railway, ...): trust its X-Forwarded-Proto header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
    SECURE_CONTENT_TYPE_NOSNIFF = True

# --- Public demo protection. When PUBLIC_READ_ONLY is on, the API refuses changes to shared records
# (missions, hazards, dataset files) from anonymous visitors; computations (route planning, terrain
# patches, catalogue registration, AI interpretation) stay available. An operator can still write
# with the header "X-Api-Token: <WRITE_API_TOKEN>" (backend secret; never in the frontend).
PUBLIC_READ_ONLY = env_bool("PUBLIC_READ_ONLY", False)
WRITE_API_TOKEN = os.environ.get("WRITE_API_TOKEN", "")
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
    # No user accounts: a local single-user tool, and a public demo protected by PUBLIC_READ_ONLY
    # (see above). Add authentication before letting several users edit shared mission data.
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

APP_VERSION = "0.5.0"

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

# --- External providers (v0.2). All overridable via environment variables.
HTTP_USER_AGENT = os.environ.get("HTTP_USER_AGENT", "Nova/0.5 (planetary GIS prototype; local)")

# Remote elevation data (v0.4): DTMs found in the USGS STAC catalogue are read window by window
# with HTTP range requests. Set REMOTE_DEM_ENABLED=0 to keep the backend fully local.
REMOTE_DEM_ENABLED = os.environ.get("REMOTE_DEM_ENABLED", "1") not in ("0", "false", "False", "")
# Decoded remote windows kept in memory per process (repeat views, profiles, routes).
REMOTE_WINDOW_CACHE_MB = int(os.environ.get("REMOTE_WINDOW_CACHE_MB", "256"))
REMOTE_RASTER_HOSTS = tuple(
    h.strip() for h in os.environ.get("REMOTE_RASTER_HOSTS", "astrogeo-ard.s3-us-west-2.amazonaws.com,copernicus-dem-30m.s3.amazonaws.com").split(",") if h.strip()
)
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
OPEN_METEO_URL = os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
NASA_POWER_URL = os.environ.get("NASA_POWER_URL", "https://power.larc.nasa.gov/api/temporal/daily/point")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "mars-explorer"}}

# Files registered through the browser/API must be small; big DEMs go through the CLI.
MAX_REGISTER_FILE_BYTES = int(os.environ.get("MAX_REGISTER_FILE_BYTES", str(500 * 1024 * 1024)))


# Optional AI assistance (v0.4). The route engine never depends on it.
#   AI_PROVIDER: rules (default: deterministic parser, no model) | ollama (local, free) |
#                anthropic (remote; ANTHROPIC_API_KEY must be set in the BACKEND environment) | none
AI_PROVIDER = os.environ.get("AI_PROVIDER", "rules")
AI_MODEL = os.environ.get("AI_MODEL", "")
AI_BASE_URL = os.environ.get("AI_BASE_URL", "")
AI_EFFORT = os.environ.get("AI_EFFORT", "medium")
AI_TIMEOUT_S = float(os.environ.get("AI_TIMEOUT_S", "60"))
# Ingest detections from an external, separately validated perception model (off by default).
AI_PERCEPTION_INGEST_ENABLED = os.environ.get("AI_PERCEPTION_INGEST_ENABLED", "0") in ("1", "true", "True")
