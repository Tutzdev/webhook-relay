import random
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tenants.models import ApiKey, Tenant
from webhooks.models import Endpoint
from webhooks.services.publishing import publish_event

ENDPOINTS = [
    ("ok", "Always answers 200", []),
    ("flaky", "Fails about half of the time", ["deposit.posted", "transfer.posted"]),
    ("slow", "Answers after two seconds", ["withdrawal.posted"]),
    ("fail", "Simulated outage, ends in the dead-letter queue", []),
]
EVENT_TYPES = ["deposit.posted", "withdrawal.posted", "transfer.posted", "reversal.posted"]


class Command(BaseCommand):
    help = "Creates a demo tenant, endpoints on the built-in receiver and publishes sample events."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default="http://localhost:8000")
        parser.add_argument("--events", type=int, default=20)

    def handle(self, *args, base_url: str, events: int, **options):
        if not (settings.RELAY_DEMO_RECEIVER and settings.RELAY_ALLOW_PRIVATE_URLS):
            raise CommandError("Set RELAY_DEMO_RECEIVER=true and RELAY_ALLOW_PRIVATE_URLS=true to run the demo.")

        tenant, _ = Tenant.objects.get_or_create(name="Demo Wallet")
        _, plain_key = ApiKey.issue(tenant)
        for mode, description, event_types in ENDPOINTS:
            Endpoint.objects.get_or_create(
                tenant=tenant,
                url=f"{base_url.rstrip('/')}/demo/receiver/{mode}/",
                defaults={"description": description, "event_types": event_types},
            )

        for _ in range(events):
            publish_event(
                tenant,
                random.choice(EVENT_TYPES),
                {
                    "transfer_id": str(uuid.uuid4()),
                    "amount": str(Decimal(random.randint(100, 50000)) / 100),
                    "currency": "BRL",
                },
                idempotency_key=f"demo-{uuid.uuid4()}",
            )

        self.stdout.write(f"Tenant: {tenant.name}")
        self.stdout.write(self.style.SUCCESS(f"API key: {plain_key}"))
        self.stdout.write(f"Published {events} events to {len(ENDPOINTS)} endpoints.")
