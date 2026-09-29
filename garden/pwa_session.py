"""Non-secret browser boundary marker; no credentials or authorization in this cookie.
Old online pages also rotate it, so a new offline tab cannot expose a prior login.
"""
from uuid import uuid4
from django.conf import settings

COOKIE = 'garden_session_boundary'


class PwaSessionBoundaryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        marker = request.COOKIES.get(COOKIE) or uuid4().hex
        request.pwa_boundary = marker
        response = self.get_response(request)
        transition = request.method == 'POST' and request.path in (
            '/accounts/login/', '/accounts/logout/', '/gardens/select/',
        ) and 200 <= response.status_code < 400
        if transition:
            marker = uuid4().hex
        if transition or COOKIE not in request.COOKIES:
            response.set_cookie(COOKIE, marker, secure=not settings.DEBUG, httponly=False, samesite='Lax', max_age=365 * 24 * 60 * 60)
        return response
