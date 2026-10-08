from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard:overview", permanent=False)),
    path("admin/", admin.site.urls),
    path("api/v1/", include("webhooks.api.urls")),
    path("dashboard/", include("dashboard.urls")),
]

if settings.RELAY_DEMO_RECEIVER:
    urlpatterns.append(path("demo/", include("demo.urls")))
