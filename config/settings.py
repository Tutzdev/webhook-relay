from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_int, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = env_bool("DJANGO_DEBUG")
SECRET_KEY = env_str("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when DJANGO_DEBUG is off.")
    SECRET_KEY = "dev-only-insecure-secret-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "tenants",
    "webhooks",
    "dashboard",
    "demo",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=60,
        conn_health_checks=True,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env_str("REDIS_URL")
CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
        if REDIS_URL
        else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

LOGIN_URL = "dashboard:login"
LOGIN_REDIRECT_URL = "dashboard:overview"
LOGOUT_REDIRECT_URL = "dashboard:login"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["tenants.authentication.ApiKeyAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["tenants.authentication.IsTenant"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_RATES": {"events": env_str("RELAY_EVENTS_RATE", "1200/min")},
    "EXCEPTION_HANDLER": "webhooks.api.problems.problem_details_handler",
    "UNAUTHENTICATED_USER": None,
}

CELERY_BROKER_URL = REDIS_URL or "redis://localhost:6379/0"
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER")
CELERY_BEAT_SCHEDULE = {
    "requeue-due-deliveries": {
        "task": "webhooks.tasks.requeue_due_deliveries",
        "schedule": 30.0,
    },
}

# Delivery behaviour. Defaults follow what public webhook providers do; every value can be tuned per environment.
RELAY_MAX_ATTEMPTS = env_int("RELAY_MAX_ATTEMPTS", 8)
RELAY_RETRY_BASE_SECONDS = env_int("RELAY_RETRY_BASE_SECONDS", 10)
RELAY_RETRY_MAX_SECONDS = env_int("RELAY_RETRY_MAX_SECONDS", 6 * 60 * 60)
RELAY_CONNECT_TIMEOUT_SECONDS = env_int("RELAY_CONNECT_TIMEOUT_SECONDS", 3)
RELAY_READ_TIMEOUT_SECONDS = env_int("RELAY_READ_TIMEOUT_SECONDS", 10)
RELAY_CIRCUIT_FAILURE_THRESHOLD = env_int("RELAY_CIRCUIT_FAILURE_THRESHOLD", 15)
RELAY_CIRCUIT_MIN_FAILING_SECONDS = env_int("RELAY_CIRCUIT_MIN_FAILING_SECONDS", 60 * 60)
RELAY_SENDING_LEASE_SECONDS = env_int("RELAY_SENDING_LEASE_SECONDS", 60)
RELAY_SECRET_ROTATION_GRACE_SECONDS = env_int("RELAY_SECRET_ROTATION_GRACE_SECONDS", 24 * 60 * 60)
RELAY_ALLOW_PRIVATE_URLS = env_bool("RELAY_ALLOW_PRIVATE_URLS")
RELAY_DEMO_RECEIVER = env_bool("RELAY_DEMO_RECEIVER")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env_str("LOG_LEVEL", "INFO")},
}
