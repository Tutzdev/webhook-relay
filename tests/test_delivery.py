import time

import pytest
import requests
import responses
from django.utils import timezone

from webhooks.models import Delivery, Endpoint
from webhooks.services.delivery import ReplayNotAllowed, attempt_delivery, replay
from webhooks.services.signing import verify


@responses.activate
def test_a_successful_delivery_is_signed_and_finished(make_delivery):
    delivery = make_delivery()
    responses.post(delivery.endpoint.url, status=200, body="ok")

    assert attempt_delivery(str(delivery.id)) is None

    delivery.refresh_from_db()
    request = responses.calls[0].request
    assert delivery.status == Delivery.Status.SUCCEEDED
    assert delivery.attempts.get().status_code == 200
    assert request.headers["webhook-id"] == delivery.event.message_id
    assert verify(delivery.endpoint.secret, request.headers, request.body, int(time.time()))


@responses.activate
def test_a_failed_attempt_schedules_a_retry(make_delivery):
    delivery = make_delivery()
    responses.post(delivery.endpoint.url, status=500)

    retry_at = attempt_delivery(str(delivery.id))

    delivery.refresh_from_db()
    assert retry_at is not None and retry_at > timezone.now()
    assert delivery.status == Delivery.Status.PENDING
    assert delivery.attempt_count == 1
    assert delivery.last_error == "HTTP 500"


@responses.activate
def test_a_network_error_counts_as_a_failed_attempt(make_delivery):
    delivery = make_delivery()
    responses.post(delivery.endpoint.url, body=requests.ConnectionError("refused"))

    attempt_delivery(str(delivery.id))

    delivery.refresh_from_db()
    assert delivery.status == Delivery.Status.PENDING
    assert delivery.last_error.startswith("ConnectionError")


@responses.activate
def test_the_delivery_goes_to_the_dead_letter_queue_after_the_last_attempt(settings, make_delivery):
    settings.RELAY_MAX_ATTEMPTS = 2
    delivery = make_delivery()
    responses.post(delivery.endpoint.url, status=503)

    attempt_delivery(str(delivery.id))
    Delivery.objects.filter(id=delivery.id).update(next_attempt_at=timezone.now())
    assert attempt_delivery(str(delivery.id)) is None

    delivery.refresh_from_db()
    assert delivery.status == Delivery.Status.DEAD
    assert delivery.attempts.count() == 2


@responses.activate
def test_the_circuit_breaker_disables_an_endpoint_that_keeps_failing(settings, make_delivery):
    settings.RELAY_CIRCUIT_FAILURE_THRESHOLD = 1
    settings.RELAY_CIRCUIT_MIN_FAILING_SECONDS = 0
    delivery = make_delivery()
    responses.post(delivery.endpoint.url, status=500)

    attempt_delivery(str(delivery.id))

    delivery.refresh_from_db()
    delivery.endpoint.refresh_from_db()
    assert delivery.endpoint.status == Endpoint.Status.DISABLED
    assert delivery.status == Delivery.Status.DEAD


@responses.activate
def test_a_delivery_is_sent_once_even_if_the_task_runs_twice(make_delivery):
    delivery = make_delivery()
    responses.post(delivery.endpoint.url, status=200)

    attempt_delivery(str(delivery.id))
    attempt_delivery(str(delivery.id))

    assert len(responses.calls) == 1


@responses.activate
def test_requests_to_internal_addresses_are_blocked_at_send_time(settings, make_endpoint, make_delivery):
    settings.RELAY_ALLOW_PRIVATE_URLS = False
    delivery = make_delivery(endpoint=make_endpoint(url="http://127.0.0.1:6379/"))

    attempt_delivery(str(delivery.id))

    delivery.refresh_from_db()
    assert len(responses.calls) == 0
    assert delivery.last_error.startswith("Blocked")


def test_replay_reopens_a_dead_delivery(make_delivery, django_capture_on_commit_callbacks):
    delivery = make_delivery()
    Delivery.objects.filter(id=delivery.id).update(status=Delivery.Status.DEAD, attempt_count=8)
    delivery.refresh_from_db()

    with django_capture_on_commit_callbacks() as callbacks:
        replay(delivery)

    delivery.refresh_from_db()
    assert delivery.status == Delivery.Status.PENDING
    assert delivery.attempt_count == 0
    assert len(callbacks) == 1


def test_a_delivery_in_progress_cannot_be_replayed(make_delivery):
    delivery = make_delivery()

    with pytest.raises(ReplayNotAllowed):
        replay(delivery)
