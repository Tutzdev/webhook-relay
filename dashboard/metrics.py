from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import Avg, Count, Q

from webhooks.models import Delivery, DeliveryAttempt, Endpoint, Event

WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class Overview:
    events_24h: int
    attempts_24h: int
    success_rate_24h: float | None
    avg_latency_ms_24h: int | None
    in_flight: int
    dead_letters: int
    disabled_endpoints: int


def overview(now: datetime) -> Overview:
    since = now - WINDOW
    attempts = DeliveryAttempt.objects.filter(created_at__gte=since).aggregate(
        total=Count("id"),
        succeeded=Count("id", filter=Q(succeeded=True)),
        avg_ms=Avg("duration_ms"),
    )
    deliveries = Delivery.objects.aggregate(
        in_flight=Count("id", filter=Q(status__in=[Delivery.Status.PENDING, Delivery.Status.SENDING])),
        dead=Count("id", filter=Q(status=Delivery.Status.DEAD)),
    )
    total = attempts["total"]
    return Overview(
        events_24h=Event.objects.filter(created_at__gte=since).count(),
        attempts_24h=total,
        success_rate_24h=round(100 * attempts["succeeded"] / total, 1) if total else None,
        avg_latency_ms_24h=round(attempts["avg_ms"]) if attempts["avg_ms"] is not None else None,
        in_flight=deliveries["in_flight"],
        dead_letters=deliveries["dead"],
        disabled_endpoints=Endpoint.objects.filter(status=Endpoint.Status.DISABLED).count(),
    )


def endpoint_health(now: datetime):
    """One query for the whole table. ``distinct`` keeps the two joined counts from multiplying each other."""
    since = now - WINDOW
    recent = Q(deliveries__attempts__created_at__gte=since)
    return (
        Endpoint.objects.select_related("tenant")
        .annotate(
            attempts_24h=Count("deliveries__attempts", filter=recent, distinct=True),
            succeeded_24h=Count(
                "deliveries__attempts", filter=recent & Q(deliveries__attempts__succeeded=True), distinct=True
            ),
            dead=Count("deliveries", filter=Q(deliveries__status=Delivery.Status.DEAD), distinct=True),
        )
        .order_by("-status", "-consecutive_failures", "url")
    )
