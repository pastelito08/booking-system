from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone
from .models import Booking


@shared_task
def send_booking_email(booking_id, event):
    """event is one of: created, confirmed, cancelled."""
    try:
        booking = Booking.objects.select_related("user", "resource").get(pk=booking_id)
    except Booking.DoesNotExist:
        return "booking not found"

    if not booking.user.email:
        return "user has no email"

    subjects = {
        "created": "Booking received",
        "confirmed": "Booking confirmed",
        "cancelled": "Booking cancelled",
    }
    message = (
        f"Hi {booking.user.username},\n\n"
        f"Your booking for {booking.resource.name} "
        f"({booking.start_time:%Y-%m-%d %H:%M} to {booking.end_time:%H:%M}) "
        f"is now: {booking.status}.\n"
    )
    send_mail(subjects[event], message, None, [booking.user.email])
    return f"sent {event} email to {booking.user.email}"

@shared_task
def complete_past_bookings():
    """Mark confirmed bookings whose end time has passed as completed."""
    count = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        end_time__lt=timezone.now(),
    ).update(status=Booking.Status.COMPLETED)
    return f"completed {count} booking(s)"