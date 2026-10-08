from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from webhooks.api.serializers import (
    DeliveryDetailSerializer,
    DeliverySerializer,
    EndpointSerializer,
    EventCreateSerializer,
    EventDetailSerializer,
    EventSerializer,
)
from webhooks.models import Delivery, Endpoint, Event
from webhooks.services.delivery import ReplayNotAllowed, replay, replay_dead
from webhooks.services.publishing import publish_event


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


class TenantScopedMixin:
    """Every query starts from the tenant of the API key, so one tenant can never read another's data."""

    @property
    def tenant(self):
        return self.request.user.tenant


class EventViewSet(
    TenantScopedMixin, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet
):
    throttle_scope = "events"

    def get_queryset(self):
        queryset = Event.objects.filter(tenant=self.tenant).order_by("-created_at")
        if self.action == "retrieve":
            return queryset.prefetch_related("deliveries")
        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return EventCreateSerializer
        if self.action == "retrieve":
            return EventDetailSerializer
        return EventSerializer

    def get_throttles(self):
        return [ScopedRateThrottle()] if self.action == "create" else []

    def create(self, request, *args, **kwargs):
        serializer = EventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = publish_event(self.tenant, **serializer.validated_data)

        body = EventDetailSerializer(result.event).data
        return Response(body, status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK)


class EndpointViewSet(TenantScopedMixin, ModelViewSet):
    serializer_class = EndpointSerializer

    def get_queryset(self):
        return Endpoint.objects.filter(tenant=self.tenant).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        endpoint = serializer.save(tenant=self.tenant)
        # The signing secret is returned here and by GET /secret, never in listings.
        return Response({**serializer.data, "secret": endpoint.secret}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def secret(self, request, pk=None):
        endpoint = self.get_object()
        return Response({"secret": endpoint.secret, "previous_secret_expires_at": endpoint.previous_secret_expires_at})

    @action(detail=True, methods=["post"], url_path="rotate-secret")
    def rotate_secret(self, request, pk=None):
        endpoint = self.get_object()
        endpoint.rotate_secret(timezone.now(), timedelta(seconds=settings.RELAY_SECRET_ROTATION_GRACE_SECONDS))
        endpoint.save()
        return Response({"secret": endpoint.secret, "previous_secret_expires_at": endpoint.previous_secret_expires_at})

    @action(detail=True, methods=["post"])
    def enable(self, request, pk=None):
        endpoint = self.get_object()
        endpoint.enable()
        endpoint.save()
        return Response(self.get_serializer(endpoint).data)

    @action(detail=True, methods=["post"], url_path="replay-dead")
    def replay_dead(self, request, pk=None):
        try:
            replayed = replay_dead(self.get_object())
        except ReplayNotAllowed as error:
            raise Conflict(str(error)) from error
        return Response({"replayed": replayed})


class DeliveryViewSet(TenantScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    def get_queryset(self):
        queryset = Delivery.objects.filter(endpoint__tenant=self.tenant).select_related("event").order_by("-created_at")
        if self.action == "retrieve":
            return queryset.prefetch_related("attempts")
        if status_filter := self.request.query_params.get("status"):
            queryset = queryset.filter(status=status_filter)
        if endpoint_filter := self.request.query_params.get("endpoint"):
            queryset = queryset.filter(endpoint_id=endpoint_filter)
        return queryset

    def get_serializer_class(self):
        return DeliveryDetailSerializer if self.action == "retrieve" else DeliverySerializer

    @action(detail=True, methods=["post"])
    def replay(self, request, pk=None):
        delivery = self.get_object()
        try:
            with transaction.atomic():
                replay(delivery)
        except ReplayNotAllowed as error:
            raise Conflict(str(error)) from error
        delivery.refresh_from_db()
        return Response(DeliverySerializer(delivery).data, status=status.HTTP_202_ACCEPTED)
