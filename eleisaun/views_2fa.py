import segno
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import twofa
from .i18n import tr
from .models import AuditLog, RecoveryCode, TOTPDevice


def _throttle_key(request):
    return f"otp:{request.user.id}"


def _locked(request):
    return cache.get(_throttle_key(request), 0) >= settings.LOGIN_MAX_ATTEMPTS


def _fail(request):
    k = _throttle_key(request)
    cache.set(k, cache.get(k, 0) + 1, settings.LOGIN_LOCK_SECONDS)
    AuditLog.record(request, "2fa_failed")


def mark_verified(request):
    request.session["otp_ok"] = True
    request.session.cycle_key()
    cache.delete(_throttle_key(request))


def _new_codes(user):
    RecoveryCode.objects.filter(user=user).delete()
    codes = twofa.make_recovery_codes()
    RecoveryCode.objects.bulk_create(RecoveryCode(user=user, code_hash=twofa.hash_code(c)) for c in codes)
    return codes


def _required(user):
    return getattr(getattr(user, "profile", None), "role", "") in settings.TWOFA_REQUIRED_ROLES


@login_required
def setup(request):
    dev = TOTPDevice.objects.filter(user=request.user).first()
    if dev and dev.confirmed:
        return render(request, "twofa/manage.html", {"required": _required(request.user), "page": "2fa",
                                                      "remaining": request.user.recovery_codes.filter(used_at=None).count()})
    if not dev:
        dev = TOTPDevice.objects.create(user=request.user, secret=twofa.new_secret())
    if request.method == "POST":
        if _locked(request):
            messages.error(request, tr("login_locked", request.lang) % {"m": settings.LOGIN_LOCK_SECONDS // 60})
        else:
            counter = twofa.verify(dev.secret, request.POST.get("code", ""), dev.last_counter)
            if counter:
                dev.confirmed, dev.last_counter = True, counter
                dev.save()
                mark_verified(request)
                AuditLog.record(request, "2fa_enabled")
                codes = _new_codes(request.user)
                return render(request, "twofa/codes.html", {"codes": codes, "page": "2fa"})
            _fail(request)
            messages.error(request, tr("twofa_bad_code", request.lang))
    uri = twofa.otpauth_uri(dev.secret, request.user.get_username())
    qr = segno.make(uri, error="m").svg_data_uri(scale=6, border=2, dark="#0f172a", light="#ffffff")
    return render(request, "twofa/setup.html", {"qr": qr, "secret": dev.secret, "page": "2fa"})


@login_required
def verify(request):
    dev = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    if not dev or request.session.get("otp_ok"):
        return redirect("home")
    if request.method == "POST":
        if _locked(request):
            messages.error(request, tr("login_locked", request.lang) % {"m": settings.LOGIN_LOCK_SECONDS // 60})
        else:
            raw = request.POST.get("code", "").strip()
            counter = twofa.verify(dev.secret, raw, dev.last_counter)
            if counter:
                dev.last_counter = counter
                dev.save(update_fields=["last_counter"])
                mark_verified(request)
                AuditLog.record(request, "2fa_ok")
                return redirect(request.GET.get("next") if (request.GET.get("next", "").startswith("/")
                                                            and not request.GET.get("next", "").startswith("//")) else "home")
            rc = request.user.recovery_codes.filter(code_hash=twofa.hash_code(raw), used_at=None).first()
            if rc:
                rc.used_at = timezone.now()
                rc.save(update_fields=["used_at"])
                mark_verified(request)
                AuditLog.record(request, "2fa_recovery_used")
                messages.warning(request, tr("twofa_recovery_used", request.lang))
                return redirect("home")
            _fail(request)
            messages.error(request, tr("twofa_bad_code", request.lang))
    return render(request, "twofa/verify.html", {})


@login_required
@require_POST
def regenerate(request):
    dev = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    if not dev or not request.session.get("otp_ok"):
        return redirect("twofa_setup")
    counter = twofa.verify(dev.secret, request.POST.get("code", ""), dev.last_counter)
    if not counter:
        _fail(request)
        messages.error(request, tr("twofa_bad_code", request.lang))
        return redirect("twofa_setup")
    dev.last_counter = counter
    dev.save(update_fields=["last_counter"])
    AuditLog.record(request, "2fa_codes_regenerated")
    return render(request, "twofa/codes.html", {"codes": _new_codes(request.user), "page": "2fa"})


@login_required
@require_POST
def disable(request):
    if _required(request.user):
        messages.error(request, tr("twofa_required", request.lang))
        return redirect("twofa_setup")
    dev = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    if dev and request.session.get("otp_ok") and request.user.check_password(request.POST.get("password", "")):
        counter = twofa.verify(dev.secret, request.POST.get("code", ""), dev.last_counter)
        if counter:
            dev.delete()
            request.user.recovery_codes.all().delete()
            request.session.pop("otp_ok", None)
            AuditLog.record(request, "2fa_disabled")
            messages.success(request, tr("twofa_disabled", request.lang))
            return redirect("home")
        _fail(request)
    messages.error(request, tr("twofa_bad_code", request.lang))
    return redirect("twofa_setup")
