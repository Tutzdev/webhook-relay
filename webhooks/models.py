import base64
import secrets
import uuid
from datetime import datetime, timedelta

from django.db import models
from django.db.models import Q

from tenants.models import Tenant

SECRET_PREFIX = "whsec_"


def new_signing_secret() -> str:
    return SECRET_PREFIX + base64.b64encode(secrets.token_bytes(24)).decode()


class Endpoint(models.Model):
    """A URL that receives the tenant's events, with its own secret, filter, rate limit and health."""

    class Status(models.TextChoices):
        ACTIVE = "active"
        DISABLED = "disabled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="endpoints")
    url = models.URLField(max_length=500)
    description = models.CharField(max_length=200, blank=True)
    event_types = models.JSONField(default=list, blank=True, help_text="Empty means every event type.")
    secret = models.CharField(max_length=64, default=new_signing_secret)
    previous_secret = models.CharField(max_length=64, blank=True)
    previous_secret_expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    disabled_reason = models.CharField(max_length=200, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    failing_since = models.DateTimeField(null=True, blank=True)
    rate_limit_per_second = models.PositiveSmallIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "status"])]

    def __str__(self) -> str:
        return self.url

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE

    def subscribes_to(self, event_type: str) -> bool:
        return not self.event_types or event_type in self.event_types

    def signing_secrets(self, now: datetime) -> list[str]:
        """During a rotation both secrets sign, so receivers can switch without dropping a single event."""
        secrets_in_use = [self.secret]
        if self.previous_secret and self.previous_secret_expires_at and self.previous_secret_expires_at > now:
            secrets_in_use.append(self.previous_secret)
        return secrets_in_use

    def rotate_secret(self, now: datetime, grace: timedelta) -> None:
        self.previous_secret = self.secret
        self.previous_secret_expires_at = now + grace
        self.secret = new_signing_secret()

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.failing_since = None

    def record_failure(self, now: datetime, threshold: int, min_failing: timedelta) -> bool:
        """
        Circuit breaker. The endpoint is disabled only when it failed many times in a row *and* has been
        failing for a while, so a burst of errors during a deploy does not switch it off.
        Returns True when this failure opened the circuit.
        """
        self.consecutive_failures += 1
        self.failing_since = self.failing_since or now
        should_open = self.consecutive_failures >= threshold and now - self.failing_since >= min_failing
        if should_open and self.is_active:
            self.status = self.Status.DISABLED
            self.disabled_reason = f"Disabled after {self.consecutive_failures} consecutive failed deliveries."
            return True
        return False

    def enable(self) -> None:
        self.status = self.Status.ACTIVE
        self.disabled_reason = ""
        self.record_success()


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    idempotency_key = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uniq_event_idempotency_key",
            )
        ]
        indexes = [models.Index(fields=["tenant", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.event_type} {self.id}"

    @property
    def message_id(self) -> str:
        """Stable across retries and replays, so receivers can deduplicate."""
        return f"msg_{self.id.hex}"


class Delivery(models.Model):
    """One event going to one endpoint. Retries and replays happen on this row; each try is a DeliveryAttempt."""

    class Status(models.TextChoices):
        PENDING = "pending"
        SENDING = "sending"
        SUCCEEDED = "succeeded"
        DEAD = "dead"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="deliveries")
    endpoint = models.ForeignKey(Endpoint, on_delete=models.CASCADE, related_name="deliveries")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0, help_text="Attempts in the current retry cycle.")
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    last_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "endpoint"], name="uniq_delivery_event_endpoint")]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["endpoint", "-created_at"]),
        ]

    @property
    def is_finished(self) -> bool:
        return self.status in {self.Status.SUCCEEDED, self.Status.DEAD}


class DeliveryAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery = models.ForeignKey(Delivery, on_delete=models.CASCADE, related_name="attempts")
    number = models.PositiveIntegerField()
    succeeded = models.BooleanField()
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)
    response_excerpt = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["number"]
        indexes = [models.Index(fields=["-created_at"])]
