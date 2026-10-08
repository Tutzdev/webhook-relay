from rest_framework.routers import SimpleRouter

from webhooks.api.views import DeliveryViewSet, EndpointViewSet, EventViewSet

router = SimpleRouter(trailing_slash=False)
router.register("events", EventViewSet, basename="event")
router.register("endpoints", EndpointViewSet, basename="endpoint")
router.register("deliveries", DeliveryViewSet, basename="delivery")

urlpatterns = router.urls
