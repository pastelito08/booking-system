from rest_framework.routers import DefaultRouter

from .views import BookingViewSet, ResourceViewSet

router = DefaultRouter()
router.register("resources", ResourceViewSet, basename="resource")
router.register("bookings", BookingViewSet, basename="booking")

urlpatterns = router.urls