import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")

from config.settings import *  # noqa: E402,F403

MIDDLEWARE = [middleware for middleware in MIDDLEWARE if "whitenoise" not in middleware]  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
CELERY_TASK_ALWAYS_EAGER = False
RELAY_ALLOW_PRIVATE_URLS = True
