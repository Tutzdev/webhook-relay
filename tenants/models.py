import hashlib
import hmac
import secrets
import uuid

from django.db import models

API_KEY_PREFIX = "rk"


def hash_api_key(plain_key: str) -> str:
    return hashlib.sha256(plain_key.encode()).hexdigest()


class Tenant(models.Model):
    """A customer of the platform. Every endpoint, event and delivery belongs to exactly one tenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class ApiKey(models.Model):
    """
    Keys look like ``rk_<lookup>_<secret>``. Only a SHA-256 hash is stored: the plain key is shown once,
    when it is issued. ``lookup`` finds the row without scanning every hash.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="api_keys")
    lookup = models.CharField(max_length=16, unique=True)
    key_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, tenant: Tenant) -> tuple["ApiKey", str]:
        lookup = secrets.token_hex(6)
        plain_key = f"{API_KEY_PREFIX}_{lookup}_{secrets.token_urlsafe(32)}"
        api_key = cls.objects.create(tenant=tenant, lookup=lookup, key_hash=hash_api_key(plain_key))
        return api_key, plain_key

    @staticmethod
    def lookup_of(plain_key: str) -> str | None:
        parts = plain_key.split("_", 2)
        if len(parts) != 3 or parts[0] != API_KEY_PREFIX:
            return None
        return parts[1]

    def matches(self, plain_key: str) -> bool:
        return hmac.compare_digest(self.key_hash, hash_api_key(plain_key))
