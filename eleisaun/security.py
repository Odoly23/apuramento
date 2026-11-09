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
            if user.is_authenticated and getattr(getattr(user, "profile", None), "language", None) in LANGS:
                lang = user.profile.language
        request.lang = lang
        return self.get_response(request)


class TwoFactorMiddleware:
    """Utilizadór ho 2FA ativu tenke verifika kódigu iha kada sesaun; papél iha TWOFA_REQUIRED_ROLES obrigatóriu."""

    EXEMPT = ("/login/", "/logout/", "/2fa/", "/lang/", "/static/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (user.is_authenticated and not request.session.get("otp_ok")
                and not request.path.startswith(self.EXEMPT)):
            from django.shortcuts import redirect
            from .models import TOTPDevice
            from django.contrib import messages
            from .i18n import tr
            if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
                return redirect(f"/2fa/verify/?next={request.path}")
            role = getattr(getattr(user, "profile", None), "role", "")
            if role in settings.TWOFA_REQUIRED_ROLES or (user.is_superuser and "admin" in settings.TWOFA_REQUIRED_ROLES):
                messages.info(request, tr("twofa_must", getattr(request, "lang", "tet")))
                return redirect("/2fa/setup/")
        return self.get_response(request)
