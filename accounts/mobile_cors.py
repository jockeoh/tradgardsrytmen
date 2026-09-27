from django.conf import settings
from django.http import HttpResponse
from django.utils.cache import patch_vary_headers


class MobileCorsMiddleware:
    """Exact opt-in development origins. Never cookies or wildcard origins."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")
        api = request.path.startswith("/api/v1/")
        allowed = api and origin in settings.MOBILE_WEB_ORIGINS
        response = HttpResponse(status=204) if allowed and request.method == "OPTIONS" else self.get_response(request)
        if api:
            response["Cache-Control"] = "no-store"
            patch_vary_headers(response, ["Origin"])
        if allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Idempotency-Key, X-Private-Mobile"
            response["Access-Control-Expose-Headers"] = "Retry-After"
        return response
