from django.contrib import admin

from tenants.models import ApiKey, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("tenant", "lookup", "created_at", "revoked_at")
    readonly_fields = ("lookup", "key_hash")
