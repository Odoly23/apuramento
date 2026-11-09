"""Middleware seguransa: header CSP/permissions no seleksaun lian."""
from django.conf import settings

from .i18n import LANGS


class SecurityHeadersMiddleware:
    CSP = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'; object-src 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/admin/"):
            response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(self)")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if request.user.is_authenticated:
            # Dadus eleitorál la bele iha cache browser/proxy.
            response["Cache-Control"] = "no-store"
        return response


class LanguageMiddleware:
    """Lian husi sesaun -> perfíl -> tetun."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = request.session.get("lang")
        if lang not in LANGS:
            lang = "tet"
            user = request.user
            if user.is_authenticated and hasattr(user, "profile") and user.profile.language in LANGS:
                lang = user.profile.language
        request.lang = lang
        return self.get_response(request)
