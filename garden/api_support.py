import hashlib
import json
from functools import wraps
from uuid import UUID, uuid4

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.views.decorators.csrf import csrf_exempt

from accounts.authentication import AuthenticationError, authenticate_api_request
from .models import GardenMembership, IdempotencyRecord


def api_error(code, message, status, fields=None):
    return JsonResponse({"error": {"code": code, "message": message, "fields": fields or {}, "request_id": f"req_{uuid4().hex}"}}, status=status)


def api_authenticated(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        if request.method not in ("GET", "HEAD", "OPTIONS", "TRACE") and not authorization:
            # The v1 callback is globally exempt so native Bearer requests do not
            # need a browser CSRF token. Session-backed private-web requests still do.
            csrf_result = CsrfViewMiddleware(lambda _: None).process_view(
                request, _session_csrf_probe, (), {}
            )
            if csrf_result is not None:
                return api_error("forbidden", "Säkerhetskontrollen misslyckades. Ladda om och försök igen.", 403)
        try:
            request.api_user = authenticate_api_request(request)
        except AuthenticationError:
            return api_error("unauthenticated", "Logga in för att fortsätta.", 401)
        return view(request, *args, **kwargs)
    return csrf_exempt(wrapped)


def _session_csrf_probe(request):
    """Non-exempt callback used only to run Django's standard CSRF checks."""


def legacy_garden_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not getattr(request, "user", None) or not request.user.is_authenticated or not request.user.is_active:
            return JsonResponse({"error": "Logga in för att fortsätta."}, status=401)
        membership = active_membership(request)
        if membership is None:
            return JsonResponse({"error": "Välj vilken trädgård du vill öppna."}, status=409)
        request.garden = membership.garden
        request.garden_membership = membership
        return view(request, *args, **kwargs)
    return wrapped


def active_membership(request):
    memberships = GardenMembership.objects.select_related("garden").filter(user=request.user)
    selected = request.session.get("active_garden_id")
    membership = memberships.filter(garden__public_id=selected).first() if selected else None
    if membership is None:
        candidates = list(memberships[:2])
        if len(candidates) != 1:
            return None
        membership = candidates[0]
        request.session["active_garden_id"] = str(membership.garden.public_id)
    return membership


def parse_json_object(request):
    try:
        value = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


def idempotency_key(request):
    raw = request.headers.get("Idempotency-Key", "")
    try:
        return UUID(raw)
    except (ValueError, TypeError, AttributeError):
        return None


def request_hash(body):
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def idempotent_mutation(request, body, callback, replay_authorized=None):
    key = idempotency_key(request)
    if key is None:
        return api_error("validation_error", "Kontrollera uppgifterna.", 400, {"idempotency_key": ["invalid"]})
    fingerprint = request_hash(body)
    lookup = {"user": request.api_user, "method": request.method, "path": request.path, "key": key}
    existing = IdempotencyRecord.objects.filter(**lookup).first()
    if existing:
        if existing.request_hash != fingerprint:
            return api_error("idempotency_conflict", "Samma återförsöksnyckel har använts för en annan begäran.", 409)
        if existing.response_body is None:
            return api_error("temporarily_unavailable", "Begäran behandlas fortfarande. Försök igen.", 503)
        if replay_authorized and not replay_authorized(existing.response_body):
            return api_error("not_found", "Resursen finns inte.", 404)
        return JsonResponse(existing.response_body, status=existing.response_status)
    try:
        with transaction.atomic():
            record = IdempotencyRecord.objects.create(request_hash=fingerprint, **lookup)
            status, payload = callback()
            if status < 200 or status >= 300:
                transaction.set_rollback(True)
                return JsonResponse(payload, status=status)
            record.response_status = status
            record.response_body = payload
            record.save(update_fields=["response_status", "response_body"])
            return JsonResponse(payload, status=status)
    except IntegrityError:
        existing = IdempotencyRecord.objects.filter(**lookup).first()
        if existing and existing.request_hash == fingerprint and existing.response_body is not None:
            if replay_authorized and not replay_authorized(existing.response_body):
                return api_error("not_found", "Resursen finns inte.", 404)
            return JsonResponse(existing.response_body, status=existing.response_status)
        if existing and existing.request_hash != fingerprint:
            return api_error("idempotency_conflict", "Samma återförsöksnyckel har använts för en annan begäran.", 409)
        return api_error("temporarily_unavailable", "Begäran kunde inte slutföras. Försök igen.", 503)
