from rest_framework.exceptions import Throttled
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if isinstance(exc, Throttled):
        response.data = {
            "detail": "Request limit reached (10 requests per hour). "
                      "Please try again after 1 hour.",
            "retry_after_seconds": int(exc.wait) if exc.wait else 3600,
        }
    return response