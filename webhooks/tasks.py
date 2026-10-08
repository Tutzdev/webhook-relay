from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from webhooks.services.delivery import attempt_delivery, requeue_due

REQUEUE_GRACE = timedelta(seconds=30)


@shared_task(acks_late=True)
def deliver_webhook(delivery_id: str) -> None:
    retry_at = attempt_delivery(delivery_id)
    if retry_at is not None:
        deliver_webhook.apply_async(args=[delivery_id], eta=retry_at)


@shared_task
def requeue_due_deliveries() -> int:
    delivery_ids = requeue_due(timezone.now(), REQUEUE_GRACE)
    for delivery_id in delivery_ids:
        deliver_webhook.delay(delivery_id)
    return len(delivery_ids)
