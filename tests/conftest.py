import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from tenants.models import ApiKey, Tenant
from webhooks.models import Delivery, Endpoint, Event


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Wallet")


@pytest.fixture
def api_client(tenant):
    _, plain_key = ApiKey.issue(tenant)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {plain_key}")
    return client


@pytest.fixture
def make_endpoint(tenant):
    def make(url="https://hooks.example.com/ledger", **fields):
        return Endpoint.objects.create(tenant=tenant, url=url, **fields)

    return make


@pytest.fixture
def make_delivery(tenant, make_endpoint):
    def make(endpoint=None, event_type="deposit.posted"):
        event = Event.objects.create(tenant=tenant, event_type=event_type, payload={"amount": "10.00"})
        return Delivery.objects.create(
            event=event, endpoint=endpoint or make_endpoint(), next_attempt_at=timezone.now()
        )

    return make
