from django.core.management.base import BaseCommand

from tenants.models import ApiKey, Tenant


class Command(BaseCommand):
    help = "Creates a tenant and prints its API key. The key is shown only once."

    def add_arguments(self, parser):
        parser.add_argument("name")

    def handle(self, *args, name: str, **options):
        tenant, _ = Tenant.objects.get_or_create(name=name)
        _, plain_key = ApiKey.issue(tenant)
        self.stdout.write(f"Tenant: {tenant.name} ({tenant.id})")
        self.stdout.write(self.style.SUCCESS(f"API key: {plain_key}"))
