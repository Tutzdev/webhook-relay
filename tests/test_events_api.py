import socket

from tenants.models import Tenant
from webhooks.models import Delivery, Endpoint, Event


def test_the_api_requires_an_api_key(db):
    from rest_framework.test import APIClient

    response = APIClient().get("/api/v1/events")

    assert response.status_code == 401
    assert response["Content-Type"] == "application/problem+json"
    assert response.json()["code"] == "not_authenticated"


def test_an_event_fans_out_only_to_active_subscribed_endpoints(api_client, make_endpoint):
    every_event = make_endpoint(url="https://a.example.com/hook")
    deposits_only = make_endpoint(url="https://b.example.com/hook", event_types=["deposit.posted"])
    make_endpoint(url="https://c.example.com/hook", event_types=["transfer.posted"])
    make_endpoint(url="https://d.example.com/hook", status=Endpoint.Status.DISABLED)

    response = api_client.post(
        "/api/v1/events", {"event_type": "deposit.posted", "payload": {"amount": "10.00"}}, format="json"
    )

    assert response.status_code == 201
    endpoint_ids = {delivery["endpoint_id"] for delivery in response.json()["deliveries"]}
    assert endpoint_ids == {str(every_event.id), str(deposits_only.id)}


def test_the_same_idempotency_key_returns_the_original_event(api_client, make_endpoint):
    make_endpoint()
    body = {"event_type": "deposit.posted", "payload": {"amount": "10.00"}, "idempotency_key": "outbox-42"}

    first = api_client.post("/api/v1/events", body, format="json")
    retry = api_client.post("/api/v1/events", body, format="json")

    assert (first.status_code, retry.status_code) == (201, 200)
    assert first.json()["id"] == retry.json()["id"]
    assert Event.objects.count() == 1
    assert Delivery.objects.count() == 1


def test_a_tenant_cannot_see_another_tenants_endpoint(api_client):
    other_tenant = Tenant.objects.create(name="Someone else")
    foreign = Endpoint.objects.create(tenant=other_tenant, url="https://other.example.com/hook")

    assert api_client.get(f"/api/v1/endpoints/{foreign.id}").status_code == 404


def test_creating_an_endpoint_returns_its_secret_once(api_client):
    response = api_client.post("/api/v1/endpoints", {"url": "https://hooks.example.com/ledger"}, format="json")
    listing = api_client.get("/api/v1/endpoints")

    assert response.status_code == 201
    assert response.json()["secret"].startswith("whsec_")
    assert "secret" not in listing.json()["results"][0]


def test_an_endpoint_pointing_to_an_internal_address_is_rejected(api_client, settings, monkeypatch):
    settings.RELAY_ALLOW_PRIVATE_URLS = False
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))]
    )

    response = api_client.post("/api/v1/endpoints", {"url": "https://internal.example.com/"}, format="json")

    assert response.status_code == 400
    assert "url" in response.json()["errors"]
