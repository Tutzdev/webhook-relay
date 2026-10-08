from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from tenants.models import ApiKey, Tenant


class TenantPrincipal:
    """What ``request.user`` becomes on API calls: the tenant that owns the key, not a Django user."""

    is_authenticated = True

    def __init__(self, tenant: Tenant):
        self.tenant = tenant
        self.pk = tenant.pk


class ApiKeyAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = get_authorization_header(request).decode(errors="ignore")
        scheme, _, plain_key = header.partition(" ")
        if scheme != self.keyword or not plain_key:
            return None

        lookup = ApiKey.lookup_of(plain_key.strip())
        api_key = (
            ApiKey.objects.select_related("tenant").filter(lookup=lookup, revoked_at__isnull=True).first()
            if lookup
            else None
        )
        if api_key is None or not api_key.matches(plain_key.strip()):
            raise AuthenticationFailed("Invalid API key.")
        return TenantPrincipal(api_key.tenant), api_key

    def authenticate_header(self, request) -> str:
        return f'{self.keyword} realm="relay"'


class IsTenant(BasePermission):
    def has_permission(self, request, view) -> bool:
        return isinstance(request.user, TenantPrincipal)
