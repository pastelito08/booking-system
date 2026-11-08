from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import Booking, Resource

MAX_DURATION = timedelta(hours=8)


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = ["id", "name", "description", "capacity", "price_per_hour", "is_active"]


class BookingSerializer(serializers.ModelSerializer):
    resource_name = serializers.CharField(source="resource.name", read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "user", "resource", "resource_name",
            "start_time", "end_time", "status", "notes", "created_at",
        ]
        read_only_fields = ["user", "status", "created_at"]

    def validate_resource(self, resource):
        if not resource.is_active:
            raise serializers.ValidationError("This resource is not available for booking.")
        return resource

    def validate(self, attrs):
        # On a PATCH, a field may be missing, so fall back to the existing booking
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        resource = attrs.get("resource", getattr(self.instance, "resource", None))

        if end <= start:
            raise serializers.ValidationError("End time must be after start time.")

        if start < timezone.now():
            raise serializers.ValidationError("You cannot book a time in the past.")

        if end - start > MAX_DURATION:
            raise serializers.ValidationError("A booking cannot be longer than 8 hours.")

        overlapping = Booking.objects.filter(
            resource=resource,
            start_time__lt=end,
            end_time__gt=start,
        ).exclude(status=Booking.Status.CANCELLED)

        if self.instance:
            overlapping = overlapping.exclude(pk=self.instance.pk)

        if overlapping.exists():
            raise serializers.ValidationError("This time slot is already booked.")

        return attrs