from django.contrib.auth.views import LogoutView
from django.urls import path

from dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("login/", views.StaffLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("deliveries/<uuid:delivery_id>/", views.delivery_detail, name="delivery"),
    path("deliveries/<uuid:delivery_id>/replay/", views.replay_delivery, name="replay-delivery"),
    path("endpoints/<uuid:endpoint_id>/enable/", views.enable_endpoint, name="enable-endpoint"),
    path("endpoints/<uuid:endpoint_id>/replay-dead/", views.replay_dead_endpoint, name="replay-dead"),
]
