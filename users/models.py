from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    pass  # custom model now, so you can extend it later (phone, role, etc.)