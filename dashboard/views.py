import json

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from dashboard import metrics
from webhooks.models import Delivery, Endpoint
from webhooks.services.delivery import ReplayNotAllowed, replay, replay_dead

RECENT_DELIVERIES = 25

staff_required = user_passes_test(lambda user: user.is_active and user.is_staff, login_url="dashboard:login")


class StaffLoginView(LoginView):
    template_name = "dashboard/login.html"
    redirect_authenticated_user = True


@staff_required
def overview(request):
    status_filter = request.GET.get("status")
    if status_filter not in Delivery.Status.values:
        status_filter = None

    deliveries = Delivery.objects.select_related("event", "endpoint", "endpoint__tenant").order_by("-created_at")
    if status_filter:
        deliveries = deliveries.filter(status=status_filter)

    now = timezone.now()
    context = {
        "overview": metrics.overview(now),
        "endpoints": metrics.endpoint_health(now),
        "deliveries": deliveries[:RECENT_DELIVERIES],
        "statuses": Delivery.Status.choices,
        "status_filter": status_filter,
    }
    return render(request, "dashboard/overview.html", context)


@staff_required
def delivery_detail(request, delivery_id):
    delivery = get_object_or_404(
        Delivery.objects.select_related("event", "endpoint", "endpoint__tenant").prefetch_related("attempts"),
        id=delivery_id,
    )
    context = {"delivery": delivery, "payload": json.dumps(delivery.event.payload, indent=2)}
    return render(request, "dashboard/delivery_detail.html", context)


@staff_required
@require_POST
def replay_delivery(request, delivery_id):
    delivery = get_object_or_404(Delivery.objects.select_related("endpoint"), id=delivery_id)
    try:
        with transaction.atomic():
            replay(delivery)
        messages.success(request, "Delivery queued again.")
    except ReplayNotAllowed as error:
        messages.error(request, str(error))
    return redirect("dashboard:delivery", delivery_id=delivery.id)


@staff_required
@require_POST
def enable_endpoint(request, endpoint_id):
    endpoint = get_object_or_404(Endpoint, id=endpoint_id)
    endpoint.enable()
    endpoint.save()
    messages.success(request, f"{endpoint.url} is active again.")
    return redirect("dashboard:overview")


@staff_required
@require_POST
def replay_dead_endpoint(request, endpoint_id):
    endpoint = get_object_or_404(Endpoint, id=endpoint_id)
    try:
        replayed = replay_dead(endpoint)
        messages.success(request, f"{replayed} dead deliveries queued again.")
    except ReplayNotAllowed as error:
        messages.error(request, str(error))
    return redirect("dashboard:overview")
