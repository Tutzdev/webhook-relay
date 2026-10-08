from django.contrib import admin

from webhooks.models import Delivery, DeliveryAttempt, Endpoint, Event


@admin.register(Endpoint)
class EndpointAdmin(admin.ModelAdmin):
    list_display = ("url", "tenant", "status", "consecutive_failures", "created_at")
    list_filter = ("status",)
    exclude = ("secret", "previous_secret")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "tenant", "created_at")
    list_filter = ("event_type",)


class DeliveryAttemptInline(admin.TabularInline):
    model = DeliveryAttempt
    extra = 0
    can_delete = False
    readonly_fields = ("number", "succeeded", "status_code", "error", "duration_ms", "created_at")
    fields = readonly_fields


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("event", "endpoint", "status", "attempt_count", "next_attempt_at")
    list_filter = ("status",)
    inlines = [DeliveryAttemptInline]
