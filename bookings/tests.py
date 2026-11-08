from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Booking, Resource

User = get_user_model()

BOOKINGS_URL = "/api/bookings/"


def slot(start_hour, end_hour, days_ahead=5):
    """Return (start, end) datetimes on a future day, in the local timezone."""
    base = timezone.localtime(timezone.now() + timedelta(days=days_ahead))
    base = base.replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(hours=start_hour), base + timedelta(hours=end_hour)


class BookingTests(APITestCase):
    def setUp(self):
        cache.clear()  # reset throttle counters
        self.ram = User.objects.create_user("ram", password="StrongPass#2026")
        self.sita = User.objects.create_user("sita", password="StrongPass#2026")
        self.admin = User.objects.create_user(
            "admin", password="StrongPass#2026", is_staff=True
        )
        self.room = Resource.objects.create(name="Meeting Room A", capacity=10)

    def book(self, start_hour, end_hour, resource=None, days_ahead=5):
        start, end = slot(start_hour, end_hour, days_ahead)
        return self.client.post(
            BOOKINGS_URL,
            {
                "resource": (resource or self.room).id,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            },
            format="json",
        )

    # ---------- creating ----------

    def test_create_booking_is_pending_and_owned_by_user(self):
        self.client.force_authenticate(self.ram)
        res = self.book(14, 16)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "pending")
        self.assertEqual(res.data["user"], self.ram.id)

    def test_user_cannot_set_status_or_user(self):
        self.client.force_authenticate(self.ram)
        start, end = slot(14, 16)
        res = self.client.post(
            BOOKINGS_URL,
            {
                "resource": self.room.id,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "status": "confirmed",
                "user": self.sita.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "pending")
        self.assertEqual(res.data["user"], self.ram.id)

    def test_login_required(self):
        res = self.book(14, 16)
        self.assertEqual(res.status_code, 401)

    # ---------- double booking ----------

    def test_overlapping_booking_rejected(self):
        self.client.force_authenticate(self.ram)
        self.assertEqual(self.book(14, 16).status_code, 201)
        self.client.force_authenticate(self.sita)
        res = self.book(15, 17)
        self.assertEqual(res.status_code, 400)
        self.assertIn("already booked", str(res.data))

    def test_identical_slot_rejected(self):
        self.client.force_authenticate(self.ram)
        self.book(14, 16)
        self.assertEqual(self.book(14, 16).status_code, 400)

    def test_back_to_back_booking_allowed(self):
        self.client.force_authenticate(self.ram)
        self.assertEqual(self.book(14, 16).status_code, 201)
        self.assertEqual(self.book(16, 18).status_code, 201)

    def test_same_time_different_resource_allowed(self):
        room_b = Resource.objects.create(name="Room B")
        self.client.force_authenticate(self.ram)
        self.assertEqual(self.book(14, 16).status_code, 201)
        self.assertEqual(self.book(14, 16, resource=room_b).status_code, 201)

    def test_cancelled_booking_frees_the_slot(self):
        self.client.force_authenticate(self.ram)
        booking_id = self.book(14, 16).data["id"]
        self.client.post(f"{BOOKINGS_URL}{booking_id}/cancel/")
        self.client.force_authenticate(self.sita)
        self.assertEqual(self.book(14, 16).status_code, 201)

    def test_database_constraint_blocks_overlap_without_serializer(self):
        """Proves the PostgreSQL ExclusionConstraint works on its own."""
        start, end = slot(14, 16)
        Booking.objects.create(
            user=self.ram, resource=self.room, start_time=start, end_time=end
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.create(
                user=self.sita,
                resource=self.room,
                start_time=start + timedelta(hours=1),
                end_time=end + timedelta(hours=1),
            )

    # ---------- validation ----------

    def test_end_before_start_rejected(self):
        self.client.force_authenticate(self.ram)
        self.assertEqual(self.book(16, 14).status_code, 400)

    def test_past_booking_rejected(self):
        self.client.force_authenticate(self.ram)
        self.assertEqual(self.book(14, 16, days_ahead=-2).status_code, 400)

    def test_longer_than_8_hours_rejected(self):
        self.client.force_authenticate(self.ram)
        self.assertEqual(self.book(8, 18).status_code, 400)

    def test_inactive_resource_rejected(self):
        self.room.is_active = False
        self.room.save()
        self.client.force_authenticate(self.ram)
        self.assertEqual(self.book(14, 16).status_code, 400)

    # ---------- permissions ----------

    def test_user_sees_only_own_bookings(self):
        self.client.force_authenticate(self.ram)
        self.book(10, 11)
        self.client.force_authenticate(self.sita)
        self.book(12, 13)
        res = self.client.get(BOOKINGS_URL)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["user"], self.sita.id)

    def test_admin_sees_all_bookings(self):
        self.client.force_authenticate(self.ram)
        self.book(10, 11)
        self.client.force_authenticate(self.sita)
        self.book(12, 13)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(BOOKINGS_URL).data["count"], 2)

    def test_user_cannot_cancel_someone_elses_booking(self):
        self.client.force_authenticate(self.ram)
        booking_id = self.book(14, 16).data["id"]
        self.client.force_authenticate(self.sita)
        res = self.client.post(f"{BOOKINGS_URL}{booking_id}/cancel/")
        self.assertEqual(res.status_code, 404)

    def test_user_cannot_confirm(self):
        self.client.force_authenticate(self.ram)
        booking_id = self.book(14, 16).data["id"]
        res = self.client.post(f"{BOOKINGS_URL}{booking_id}/confirm/")
        self.assertEqual(res.status_code, 403)

    def test_admin_can_confirm_pending_only(self):
        self.client.force_authenticate(self.ram)
        booking_id = self.book(14, 16).data["id"]
        self.client.force_authenticate(self.admin)
        url = f"{BOOKINGS_URL}{booking_id}/confirm/"
        first = self.client.post(url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["status"], "confirmed")
        self.assertEqual(self.client.post(url).status_code, 400)

    def test_cancel_twice_rejected(self):
        self.client.force_authenticate(self.ram)
        booking_id = self.book(14, 16).data["id"]
        url = f"{BOOKINGS_URL}{booking_id}/cancel/"
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 400)

    # ---------- delete ----------

    def test_normal_user_cannot_delete(self):
        self.client.force_authenticate(self.ram)
        booking_id = self.book(14, 16).data["id"]
        res = self.client.delete(f"{BOOKINGS_URL}{booking_id}/")
        self.assertEqual(res.status_code, 403)

    def test_admin_can_delete(self):
        self.client.force_authenticate(self.ram)
        booking_id = self.book(14, 16).data["id"]
        self.client.force_authenticate(self.admin)
        res = self.client.delete(f"{BOOKINGS_URL}{booking_id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Booking.objects.filter(pk=booking_id).exists())


class ResourceTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.ram = User.objects.create_user("ram", password="StrongPass#2026")
        self.admin = User.objects.create_user(
            "admin", password="StrongPass#2026", is_staff=True
        )
        self.room = Resource.objects.create(name="Meeting Room A")

    def test_user_can_list_but_not_create_resources(self):
        self.client.force_authenticate(self.ram)
        self.assertEqual(self.client.get("/api/resources/").status_code, 200)
        res = self.client.post("/api/resources/", {"name": "Hacked"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_admin_can_create_resource(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/resources/", {"name": "Room C"}, format="json")
        self.assertEqual(res.status_code, 201)

    def test_inactive_resource_hidden_from_users(self):
        hidden = Resource.objects.create(name="Broken Room", is_active=False)
        self.client.force_authenticate(self.ram)
        self.assertEqual(self.client.get(f"/api/resources/{hidden.id}/").status_code, 404)

    def test_cannot_delete_resource_with_bookings(self):
        start, end = slot(11, 13)
        Booking.objects.create(
            user=self.ram, resource=self.room, start_time=start, end_time=end
        )
        self.client.force_authenticate(self.admin)
        res = self.client.delete(f"/api/resources/{self.room.id}/")
        self.assertEqual(res.status_code, 400)
        self.assertTrue(Resource.objects.filter(pk=self.room.pk).exists())

    def test_availability_splits_day_into_booked_and_free(self):
        start, end = slot(11, 13)
        Booking.objects.create(
            user=self.ram, resource=self.room, start_time=start, end_time=end
        )
        self.client.force_authenticate(self.ram)
        date_str = start.date().isoformat()
        res = self.client.get(f"/api/resources/{self.room.id}/availability/?date={date_str}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["booked"]), 1)
        self.assertEqual(len(res.data["free"]), 2)  # 9-11 and 13-18

    def test_availability_requires_valid_date(self):
        self.client.force_authenticate(self.ram)
        base = f"/api/resources/{self.room.id}/availability/"
        self.assertEqual(self.client.get(base).status_code, 400)
        self.assertEqual(self.client.get(base + "?date=hello").status_code, 400)


class RegistrationTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_register_and_login(self):
        res = self.client.post(
            "/api/auth/register/",
            {"username": "newuser", "email": "n@example.com", "password": "StrongPass#2026"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertNotIn("password", res.data)

        login = self.client.post(
            "/api/auth/login/",
            {"username": "newuser", "password": "StrongPass#2026"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("access", login.data)

    def test_weak_password_rejected(self):
        res = self.client.post(
            "/api/auth/register/",
            {"username": "weak", "email": "weak@example.com", "password": "12345678"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("password", res.data)


class ThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.ram = User.objects.create_user("ram", password="StrongPass#2026")

    def test_eleventh_request_is_throttled(self):
        self.client.force_authenticate(self.ram)
        for _ in range(10):
            self.assertEqual(self.client.get("/api/resources/").status_code, 200)
        res = self.client.get("/api/resources/")
        self.assertEqual(res.status_code, 429)
        self.assertIn("1 hour", res.data["detail"])