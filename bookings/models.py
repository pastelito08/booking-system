from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import F, Q, Func


class Resource(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    capacity = models.PositiveIntegerField(default=1)
    price_per_hour = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings"
    )
    resource = models.ForeignKey(
        Resource, on_delete=models.PROTECT, related_name="bookings"
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_time"]
        indexes = [models.Index(fields=["resource", "start_time", "end_time"])]
        constraints = [
            models.CheckConstraint(
            condition=Q(end_time__gt=F("start_time")),
            name="booking_end_after_start",
        ),
            # Database-level guarantee: no overlapping active bookings per resource
            ExclusionConstraint(
                name="no_overlapping_bookings",
                expressions=[
                    (
                        Func(F("start_time"), F("end_time"),
                             function="tstzrange", output_field=DateTimeRangeField()),
                        RangeOperators.OVERLAPS,
                    ),
                    ("resource", RangeOperators.EQUAL),
                ],
                condition=~Q(status="cancelled"),
            ),
        ]

    def __str__(self):
        return f"{self.resource} | {self.start_time:%Y-%m-%d %H:%M}"