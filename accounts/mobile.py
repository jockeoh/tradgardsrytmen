"""Opt-in private Django identity, without cookies or external identity services."""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .authentication import AuthenticationError
from .models import MobileLoginAttempt, MobileSession


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_stamp(user):
    return salted_hmac("private-mobile-password", user.password).hexdigest()


def authenticate_mobile(token):
    if not settings.PRIVATE_MOBILE_AUTH:
        raise AuthenticationError("Mobilinloggning är inte aktiverad.")
    session = MobileSession.objects.select_related("user").filter(token_hash=digest(token)).first()
    if (not session or session.expires_at <= timezone.now() or not session.user.is_active
            or not constant_time_compare(session.password_stamp, password_stamp(session.user))):
        raise AuthenticationError("Inloggningen har gått ut eller återkallats.")
    return session.user


@csrf_exempt
@never_cache
@require_POST
def login(request):
    from garden.api_support import api_error, parse_json_object
    if not settings.PRIVATE_MOBILE_AUTH:
        return api_error("not_found", "Mobilinloggning är inte aktiverad.", 404)
    if not settings.DEBUG and not request.is_secure():
        return api_error("forbidden", "Inloggning kräver HTTPS.", 403)
    # JSON + custom header cannot be sent by a cross-origin HTML form. No
    # credentialed CORS is allowed, and browser Origin is checked separately.
    origin = request.headers.get("Origin")
    allowed = {request.build_absolute_uri("/").rstrip("/"), *settings.MOBILE_WEB_ORIGINS}
    if (request.content_type != "application/json" or request.headers.get("X-Private-Mobile") != "1"
            or (origin and origin not in allowed)):
        return api_error("forbidden", "Inloggningen kommer från en otillåten klient.", 403)
    data = parse_json_object(request)
    if (not data or set(data) != {"username", "password"}
            or not all(isinstance(v, str) for v in data.values())
            or len(data["username"]) > 150 or len(data["password"]) > 1024):
        return api_error("validation_error", "Ange användarnamn och lösenord.", 400)
    now = timezone.now()
    identity = digest(data["username"].strip().casefold())
    address = digest(request.META.get("REMOTE_ADDR", ""))
    recent = MobileLoginAttempt.objects.filter(created_at__gte=now - timedelta(minutes=15))
    if recent.filter(Q(identity_hash=identity) | Q(address_hash=address)).count() >= 10:
        response = api_error("rate_limited", "För många inloggningsförsök. Vänta 15 minuter.", 429)
        response["Retry-After"] = "900"
        return response
    MobileLoginAttempt.objects.create(identity_hash=identity, address_hash=address)
    MobileLoginAttempt.objects.filter(created_at__lt=now - timedelta(days=1)).delete()
    user = authenticate(request, username=data["username"].strip(), password=data["password"])
    if user is None:
        return api_error("unauthenticated", "Fel användarnamn eller lösenord.", 401)
    token = "home_" + secrets.token_urlsafe(32)
    expiry = now + timedelta(days=14)
    MobileSession.objects.create(user=user, token_hash=digest(token), password_stamp=password_stamp(user), expires_at=expiry)
    MobileSession.objects.filter(expires_at__lt=now).delete()
    return JsonResponse({"token": token, "expires_at": expiry.isoformat(),
                         "account": {"id": str(user.public_id), "display_name": user.get_full_name() or user.username}})


@csrf_exempt
@never_cache
@require_POST
def logout(request):
    from garden.api_support import api_error
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer home_"):
        return api_error("unauthenticated", "Logga in för att fortsätta.", 401)
    MobileSession.objects.filter(token_hash=digest(header[7:])).delete()
    return JsonResponse({"revoked": True})
