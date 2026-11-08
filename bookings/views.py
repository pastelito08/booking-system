from datetime import datetime, time

from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .tasks import send_booking_email
from .models import Booking, Resource
from .serializers import BookingSerializer, ResourceSerializer

# Hours a resource can be booked (24-hour clock)
OPEN_HOUR, CLOSE_HOUR = 9, 18  # 9 AM to 6 PM


class IsAdminOrReadOnly(permissions.BasePermission):
    """Any logged-in user can read. Only staff can create, edit or delete."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_staff)


class ResourceViewSet(viewsets.ModelViewSet):
    serializer_class = ResourceSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ["name", "description"]

    def get_queryset(self):
        qs = Resource.objects.all().order_by("id")
        if not self.request.user.is_staff:
            qs = qs.filter(is_active=True)
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "date", str, description="Date in YYYY-MM-DD format", required=True
            )
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"])
    def availability(self, request, pk=None):
        """GET /api/resources/<id>/availability/?date=YYYY-MM-DD"""
        resource = self.get_object()

        date_str = request.query_params.get("date")
        if not date_str:
            return Response({"detail": "Provide ?date=YYYY-MM-DD"}, status=400)
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"detail": "Invalid date. Use YYYY-MM-DD."}, status=400)

        def at(hour):
            return timezone.make_aware(datetime.combine(day, time(hour)))

        window_start, window_end = at(OPEN_HOUR), at(CLOSE_HOUR)

        bookings = (
            Booking.objects.filter(
                resource=resource,
                start_time__lt=window_end,
                end_time__gt=window_start,
            )
            .exclude(status=Booking.Status.CANCELLED)
            .order_by("start_time")
        )

        booked, free = [], []
        cursor = window_start
        for b in bookings:
            start = max(b.start_time, window_start)
            end = min(b.end_time, window_end)
            if start > cursor:
                free.append({"start": cursor, "end": start})
            booked.append({"start": start, "end": end})
            cursor = max(cursor, end)
        if cursor < window_end:
            free.append({"start": cursor, "end": window_end})

        return Response(
            {"resource": resource.id, "date": date_str, "booked": booked, "free": free}
        )

class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    filterset_fields = ["status", "resource"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action == "destroy":
            return [permissions.IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()
        qs = Booking.objects.select_related("resource", "user")
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)
        return qs

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                booking = serializer.save(user=self.request.user)
        except IntegrityError:
            # Two requests raced; the database constraint caught the second one
            raise serializers.ValidationError(
                {"non_field_errors": ["This time slot was just booked by someone else."]}
            )
        transaction.on_commit(lambda: send_booking_email.delay(booking.id, "created"))

    @extend_schema(request=None, responses=BookingSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if booking.status == Booking.Status.CANCELLED:
            return Response({"detail": "Already cancelled."}, status=400)
        if booking.status == Booking.Status.COMPLETED:
            return Response(
                {"detail": "A completed booking cannot be cancelled."}, status=400
            )
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status"])
        transaction.on_commit(lambda: send_booking_email.delay(booking.id, "cancelled"))
        return Response(self.get_serializer(booking).data)

    @extend_schema(request=None, responses=BookingSerializer)
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def confirm(self, request, pk=None):
        booking = self.get_object()
        if booking.status != Booking.Status.PENDING:
            return Response({"detail": "Only pending bookings can be confirmed."}, status=400)
        booking.status = Booking.Status.CONFIRMED
        booking.save(update_fields=["status"])
        transaction.on_commit(lambda: send_booking_email.delay(booking.id, "confirmed"))
        return Response(self.get_serializer(booking).data)