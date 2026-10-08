import json

from django.conf import settings
from rest_framework import serializers

from webhooks.models import Delivery, DeliveryAttempt, Endpoint, Event
from webhooks.services.url_guard import UnsafeUrl, check_url

EVENT_TYPE_PATTERN = r"^[a-z0-9][a-z0-9_.-]{0,99}$"
MAX_PAYLOAD_BYTES = 64 * 1024


class EventCreateSerializer(serializers.Serializer):
    event_type = serializers.RegexField(EVENT_TYPE_PATTERN)
    payload = serializers.JSONField()
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_null=True)

    def validate_payload(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("payload must be a JSON object.")
        if len(json.dumps(value)) > MAX_PAYLOAD_BYTES:
            raise serializers.ValidationError("payload must be at most 64 KB.")
        return value


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ["id", "event_type", "payload", "idempotency_key", "created_at"]


class EventDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        fields = ["id", "endpoint_id", "status", "attempt_count", "next_attempt_at"]


class EventDetailSerializer(EventSerializer):
    deliveries = EventDeliverySerializer(many=True, read_only=True)

    class Meta(EventSerializer.Meta):
        fields = [*EventSerializer.Meta.fields, "deliveries"]


class EndpointSerializer(serializers.ModelSerializer):
    event_types = serializers.ListField(child=serializers.RegexField(EVENT_TYPE_PATTERN), required=False, max_length=50)
    rate_limit_per_second = serializers.IntegerField(min_value=1, max_value=1000, required=False)

    class Meta:
        model = Endpoint
        fields = [
            "id",
            "url",
            "description",
            "event_types",
            "status",
            "disabled_reason",
            "consecutive_failures",
            "rate_limit_per_second",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "disabled_reason", "consecutive_failures"]

    def validate_url(self, value: str) -> str:
        try:
            check_url(value, allow_private=settings.RELAY_ALLOW_PRIVATE_URLS)
        except UnsafeUrl as error:
            raise serializers.ValidationError(str(error)) from error
        return value

    def validate_event_types(self, value: list[str]) -> list[str]:
        return sorted(set(value))


class DeliveryAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryAttempt
        fields = ["number", "succeeded", "status_code", "error", "response_excerpt", "duration_ms", "created_at"]


class DeliverySerializer(serializers.ModelSerializer):
    event_type = serializers.CharField(source="event.event_type", read_only=True)

    class Meta:
        model = Delivery
        fields = [
            "id",
            "event_id",
            "event_type",
            "endpoint_id",
            "status",
            "attempt_count",
            "next_attempt_at",
            "last_status_code",
            "last_error",
            "completed_at",
            "created_at",
        ]


class DeliveryDetailSerializer(DeliverySerializer):
    attempts = DeliveryAttemptSerializer(many=True, read_only=True)

    class Meta(DeliverySerializer.Meta):
        fields = [*DeliverySerializer.Meta.fields, "attempts"]
