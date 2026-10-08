import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from webhooks.models import Delivery, DeliveryAttempt, Endpoint
from webhooks.services import rate_limit
from webhooks.services.retry_policy import RetryPolicy
from webhooks.services.signing import signature_header
from webhooks.services.url_guard import UnsafeUrl, check_url

logger = logging.getLogger(__name__)

RESPONSE_EXCERPT_BYTES = 1024
THROTTLE_DELAY = timedelta(seconds=1)
USER_AGENT = "webhook-relay/1.0"


@dataclass(frozen=True)
class AttemptOutcome:
    succeeded: bool
    status_code: int | None
    error: str
    response_excerpt: str
    duration_ms: int


class ReplayNotAllowed(Exception):
    pass


def attempt_delivery(delivery_id: str) -> datetime | None:
    """
    Runs one attempt and returns when the next one is due, or None when there is nothing left to do.
    Safe to call twice for the same delivery: only the caller that claims the row sends the request.
    """
    now = timezone.now()
    delivery = _claim(delivery_id, now)
    if delivery is None:
        return None

    endpoint = delivery.endpoint
    if not endpoint.is_active:
        _finish_as_dead(delivery, now, "Endpoint is disabled.")
        return None
    if not rate_limit.try_acquire(endpoint.id, endpoint.rate_limit_per_second):
        return _release(delivery, now + THROTTLE_DELAY)

    outcome = _send(delivery, now)
    return _record(delivery, outcome, timezone.now())


def replay(delivery: Delivery) -> None:
    if not delivery.endpoint.is_active:
        raise ReplayNotAllowed("Enable the endpoint before replaying.")
    reopened = Delivery.objects.filter(
        id=delivery.id, status__in=[Delivery.Status.SUCCEEDED, Delivery.Status.DEAD]
    ).update(
        status=Delivery.Status.PENDING,
        attempt_count=0,
        next_attempt_at=timezone.now(),
        completed_at=None,
        updated_at=timezone.now(),
    )
    if not reopened:
        raise ReplayNotAllowed("Only finished deliveries can be replayed.")
    _enqueue_after_commit([str(delivery.id)])


def replay_dead(endpoint: Endpoint) -> int:
    if not endpoint.is_active:
        raise ReplayNotAllowed("Enable the endpoint before replaying.")
    now = timezone.now()
    with transaction.atomic():
        dead = Delivery.objects.select_for_update().filter(endpoint=endpoint, status=Delivery.Status.DEAD)
        delivery_ids = [str(delivery_id) for delivery_id in dead.values_list("id", flat=True)]
        Delivery.objects.filter(id__in=delivery_ids).update(
            status=Delivery.Status.PENDING, attempt_count=0, next_attempt_at=now, completed_at=None, updated_at=now
        )
        _enqueue_after_commit(delivery_ids)
    return len(delivery_ids)


def requeue_due(now: datetime, grace: timedelta, limit: int = 500) -> list[str]:
    """
    Safety net for lost queue messages and crashed workers: expired leases go back to pending,
    and deliveries that are overdue get a fresh task.
    """
    Delivery.objects.filter(status=Delivery.Status.SENDING, lease_expires_at__lt=now).update(
        status=Delivery.Status.PENDING, lease_expires_at=None, next_attempt_at=now, updated_at=now
    )
    overdue = Delivery.objects.filter(status=Delivery.Status.PENDING, next_attempt_at__lte=now - grace)
    return [str(delivery_id) for delivery_id in overdue.values_list("id", flat=True)[:limit]]


def _claim(delivery_id: str, now: datetime) -> Delivery | None:
    """Conditional UPDATE: the database decides which worker owns the attempt, no lock is held during HTTP."""
    lease = now + timedelta(seconds=settings.RELAY_SENDING_LEASE_SECONDS)
    claimed = Delivery.objects.filter(id=delivery_id, status=Delivery.Status.PENDING, next_attempt_at__lte=now).update(
        status=Delivery.Status.SENDING, lease_expires_at=lease, updated_at=now
    )
    if not claimed:
        return None
    return Delivery.objects.select_related("event", "endpoint").get(id=delivery_id)


def _release(delivery: Delivery, retry_at: datetime) -> datetime:
    Delivery.objects.filter(id=delivery.id).update(
        status=Delivery.Status.PENDING, next_attempt_at=retry_at, lease_expires_at=None, updated_at=timezone.now()
    )
    return retry_at


def _send(delivery: Delivery, now: datetime) -> AttemptOutcome:
    endpoint, event = delivery.endpoint, delivery.event
    try:
        # Checked again on every send: DNS can change after the endpoint was registered.
        check_url(endpoint.url, allow_private=settings.RELAY_ALLOW_PRIVATE_URLS)
    except UnsafeUrl as error:
        return AttemptOutcome(False, None, f"Blocked: {error}", "", 0)

    body = json.dumps(
        {"type": event.event_type, "timestamp": event.created_at.isoformat(), "data": event.payload},
        separators=(",", ":"),
    ).encode()
    timestamp = int(now.timestamp())
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "webhook-id": event.message_id,
        "webhook-timestamp": str(timestamp),
        "webhook-signature": signature_header(endpoint.signing_secrets(now), event.message_id, timestamp, body),
    }

    started = time.perf_counter()
    try:
        with requests.post(
            endpoint.url,
            data=body,
            headers=headers,
            timeout=(settings.RELAY_CONNECT_TIMEOUT_SECONDS, settings.RELAY_READ_TIMEOUT_SECONDS),
            allow_redirects=False,
            stream=True,
        ) as response:
            excerpt = next(response.iter_content(RESPONSE_EXCERPT_BYTES), b"").decode("utf-8", "replace")
            succeeded = 200 <= response.status_code < 300
            error = "" if succeeded else f"HTTP {response.status_code}"
            return AttemptOutcome(succeeded, response.status_code, error, excerpt, _elapsed_ms(started))
    except requests.RequestException as error:
        return AttemptOutcome(False, None, f"{type(error).__name__}: {error}"[:300], "", _elapsed_ms(started))


def _record(delivery: Delivery, outcome: AttemptOutcome, now: datetime) -> datetime | None:
    policy = RetryPolicy.from_settings()
    with transaction.atomic():
        endpoint = Endpoint.objects.select_for_update().get(id=delivery.endpoint_id)
        DeliveryAttempt.objects.create(
            delivery=delivery,
            number=delivery.attempts.count() + 1,
            succeeded=outcome.succeeded,
            status_code=outcome.status_code,
            error=outcome.error,
            response_excerpt=outcome.response_excerpt,
            duration_ms=outcome.duration_ms,
        )
        delivery.attempt_count += 1
        delivery.last_status_code = outcome.status_code
        delivery.last_error = outcome.error
        delivery.lease_expires_at = None

        if outcome.succeeded:
            endpoint.record_success()
            _mark_finished(delivery, Delivery.Status.SUCCEEDED, now)
        else:
            if endpoint.record_failure(
                now,
                threshold=settings.RELAY_CIRCUIT_FAILURE_THRESHOLD,
                min_failing=timedelta(seconds=settings.RELAY_CIRCUIT_MIN_FAILING_SECONDS),
            ):
                logger.warning("endpoint_disabled endpoint=%s failures=%s", endpoint.id, endpoint.consecutive_failures)
            delay = policy.delay_after(delivery.attempt_count)
            if delay is None or not endpoint.is_active:
                _mark_finished(delivery, Delivery.Status.DEAD, now)
            else:
                delivery.status = Delivery.Status.PENDING
                delivery.next_attempt_at = now + timedelta(seconds=delay)

        endpoint.save(
            update_fields=["consecutive_failures", "failing_since", "status", "disabled_reason", "updated_at"]
        )
        delivery.save()

    logger.info(
        "delivery_attempt delivery=%s status=%s code=%s duration_ms=%s",
        delivery.id,
        delivery.status,
        outcome.status_code,
        outcome.duration_ms,
    )
    return delivery.next_attempt_at if delivery.status == Delivery.Status.PENDING else None


def _finish_as_dead(delivery: Delivery, now: datetime, reason: str) -> None:
    delivery.last_error = reason
    delivery.lease_expires_at = None
    _mark_finished(delivery, Delivery.Status.DEAD, now)
    delivery.save()


def _mark_finished(delivery: Delivery, status: str, now: datetime) -> None:
    delivery.status = status
    delivery.completed_at = now
    delivery.next_attempt_at = None


def _enqueue_after_commit(delivery_ids: list[str]) -> None:
    from webhooks.tasks import deliver_webhook

    transaction.on_commit(lambda: [deliver_webhook.delay(delivery_id) for delivery_id in delivery_ids])


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
