from django.contrib import admin
from .models import Resource, Booking


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity", "price_per_hour", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("resource", "user", "start_time", "end_time", "status")
    list_filter = ("status", "resource")
    search_fields = ("user__username", "resource__name")