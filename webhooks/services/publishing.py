from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from tenants.models import Tenant
from webhooks.models import Delivery, Endpoint, Event


@dataclass(frozen=True)
class PublishResult:
    event: Event
    created: bool


def publish_event(tenant: Tenant, event_type: str, payload: dict, idempotency_key: str | None = None) -> PublishResult:
    """
    Stores the event and one delivery per subscribed endpoint in a single transaction.
    Tasks are queued only after the commit, so a worker never looks for a row that is not there yet.
    """
    if idempotency_key:
        existing = Event.objects.filter(tenant=tenant, idempotency_key=idempotency_key).first()
        if existing:
            return PublishResult(existing, created=False)

    try:
        with transaction.atomic():
            event = Event.objects.create(
                tenant=tenant, event_type=event_type, payload=payload, idempotency_key=idempotency_key
            )
            delivery_ids = [str(delivery.id) for delivery in _fan_out(event)]
            transaction.on_commit(lambda: _enqueue(delivery_ids))
    except IntegrityError:
        # A concurrent request with the same idempotency key committed first.
        return PublishResult(Event.objects.get(tenant=tenant, idempotency_key=idempotency_key), created=False)

    return PublishResult(event, created=True)


def _fan_out(event: Event) -> list[Delivery]:
    now = timezone.now()
    endpoints = Endpoint.objects.filter(tenant=event.tenant, status=Endpoint.Status.ACTIVE)
    deliveries = [
        Delivery(event=event, endpoint=endpoint, next_attempt_at=now)
        for endpoint in endpoints
        if endpoint.subscribes_to(event.event_type)
    ]
    return Delivery.objects.bulk_create(deliveries)


def _enqueue(delivery_ids: list[str]) -> None:
    from webhooks.tasks import deliver_webhook

    for delivery_id in delivery_ids:
        deliver_webhook.delay(delivery_id)
