import hashlib
from datetime import datetime, timezone as dt_timezone

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from .models import OIDCIdentity


class AuthenticationError(Exception):
    pass


_jwks_clients = {}


def _jwks_client(url):
    if url not in _jwks_clients:
        _jwks_clients[url] = jwt.PyJWKClient(url, cache_keys=True, max_cached_keys=16)
    return _jwks_clients[url]


def authenticate_bearer(token):
    if not (settings.OIDC_ISSUER and settings.OIDC_AUDIENCE and settings.OIDC_JWKS_URL):
        raise AuthenticationError("Mobilinloggning är inte konfigurerad.")
    try:
        key = _jwks_client(settings.OIDC_JWKS_URL).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=settings.OIDC_AUDIENCE,
            issuer=settings.OIDC_ISSUER,
            leeway=30,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Ogiltig eller utgången inloggning.") from exc
    scope = set(str(claims.get("scope", "")).split())
    if settings.OIDC_REQUIRED_SCOPE and settings.OIDC_REQUIRED_SCOPE not in scope:
        raise AuthenticationError("Inloggningen saknar rätt API-behörighet.")
    issuer, subject = claims["iss"].rstrip("/"), str(claims["sub"])
    try:
        identity = OIDCIdentity.objects.select_related("user").get(issuer=issuer, subject=subject)
    except OIDCIdentity.DoesNotExist:
        if not settings.OIDC_AUTO_PROVISION:
            raise AuthenticationError("Kontot är inte aktiverat för Trädgårdsrytmen.")
        try:
            with transaction.atomic():
                identity = OIDCIdentity.objects.select_related("user").filter(issuer=issuer, subject=subject).first()
                if identity is None:
                    digest = hashlib.sha256(f"{issuer}\0{subject}".encode()).hexdigest()[:32]
                    user = get_user_model().objects.create_user(username=f"oidc_{digest}")
                    user.set_unusable_password()
                    user.first_name = str(claims.get("name", ""))[:150]
                    user.save(update_fields=["password", "first_name"])
                    identity = OIDCIdentity.objects.create(user=user, issuer=issuer, subject=subject)
        except IntegrityError:
            # A simultaneous first request may have created the deterministic
            # account and mapping while this transaction was waiting.
            identity = OIDCIdentity.objects.select_related("user").get(issuer=issuer, subject=subject)
    issued_at = datetime.fromtimestamp(int(claims["iat"]), tz=dt_timezone.utc)
    if identity.revoked_before and issued_at <= identity.revoked_before:
        raise AuthenticationError("Inloggningen har återkallats.")
    if not identity.user.is_active:
        raise AuthenticationError("Kontot är inaktiverat.")
    return identity.user


def authenticate_api_request(request):
    header = request.headers.get("Authorization", "")
    if header:
        scheme, separator, token = header.partition(" ")
        if scheme.lower() != "bearer" or not separator or not token.strip():
            raise AuthenticationError("Ogiltig Authorization-header.")
        return authenticate_bearer(token.strip())
    if getattr(request, "user", None) and request.user.is_authenticated and request.user.is_active:
        return request.user
    raise AuthenticationError("Logga in för att fortsätta.")
