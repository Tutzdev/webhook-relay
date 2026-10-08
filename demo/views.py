"""
A receiver to watch the relay working locally. It verifies the signature exactly like a real
consumer should, then answers according to its mode: ok, fail, flaky or slow.
"""

import random
import time

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from webhooks.models import Endpoint
from webhooks.services.signing import verify

FLAKY_FAILURE_RATE = 0.5
SLOW_SECONDS = 2


@csrf_exempt
@require_POST
def receiver(request, mode: str):
    endpoint = Endpoint.objects.filter(url=request.build_absolute_uri()).first()
    if endpoint is None:
        return JsonResponse({"error": "unknown endpoint"}, status=404)

    headers = {name: request.headers.get(name, "") for name in ("webhook-id", "webhook-timestamp", "webhook-signature")}
    now = int(time.time())
    if not any(verify(secret, headers, request.body, now) for secret in endpoint.signing_secrets(timezone.now())):
        return JsonResponse({"error": "invalid signature"}, status=401)

    if mode == "fail":
        return JsonResponse({"error": "simulated outage"}, status=503)
    if mode == "flaky" and random.random() < FLAKY_FAILURE_RATE:
        return JsonResponse({"error": "simulated flake"}, status=500)
    if mode == "slow":
        time.sleep(SLOW_SECONDS)
    return JsonResponse({"received": headers["webhook-id"]})
