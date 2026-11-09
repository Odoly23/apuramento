import csv
import json
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import chatbot
from .auth_utils import c_user_fun
from .forms import ReportForm
from .i18n import LANGS, all_for, tr
from .models import AuditLog, Centre, Contestant, Evidence, Profile, Report, ResultLine, client_ip
from .services import (build_snapshot, compute_flags, consolidate, invalidate, pick_election,
                       resolve_centre)


# ---------------------------------------------------------------- dekorador
def role_view(*roles):
    """Login obrigatóriu + papél. roles: 'admin' | 'fiskal' | 'monitor' (monitor inklui admin)."""

    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(request, *args, **kwargs):
            p = c_user_fun(request.user)
            if not p:
                return render(request, "403.html", status=403)
            ok = (
                ("admin" in roles and p.is_admin)
                or ("fiskal" in roles and p.is_fiskal)
                or ("monitor" in roles and p.can_monitor)
                or not roles
            )
            if not ok:
                return render(request, "403.html", status=403)
            e = pick_election(request.GET.get("e") or request.session.get("election"))
            request.election = e
            if e:
                request.session["election"] = e.id
            return fn(request, *args, **kwargs)

        return wrapper

    return deco


LEVELS = {"municipality": "municipalities", "postu": "postus", "suku": "sukus", "nasaun": "nasauns"}


def _snapshot_for_page(election):
    snap = build_snapshot(election)
    return {k: v for k, v in snap.items() if k not in ("postus", "sukus")}


# ---------------------------------------------------------------- login
class ThrottledLoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def _key(self, request):
        user = (request.POST.get("username") or "").strip().lower()[:150]
        return f"login:{client_ip(request)}:{user}"

    def post(self, request, *args, **kwargs):
        key = self._key(request)
        if cache.get(key, 0) >= settings.LOGIN_MAX_ATTEMPTS:
            AuditLog.record(request, "login_locked", target=request.POST.get("username", "")[:150],
                            username=request.POST.get("username", "")[:150])
            form = self.get_form()
            form.add_error(None, tr("login_locked", request.lang) % {"m": settings.LOGIN_LOCK_SECONDS // 60})
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        key = self._key(self.request)
        cache.set(key, cache.get(key, 0) + 1, settings.LOGIN_LOCK_SECONDS)
        AuditLog.record(self.request, "login_failed", target=self.request.POST.get("username", "")[:150],
                        username=self.request.POST.get("username", "")[:150])
        form.errors.clear()
        form.add_error(None, tr("login_failed", self.request.lang))
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._key(self.request))
        resp = super().form_valid(form)
        self.request.session.pop("otp_ok", None)
        AuditLog.record(self.request.user, "login", ip=client_ip(self.request))
        return resp


def logout_view(request):
    if request.method == "POST" and request.user.is_authenticated:
        AuditLog.record(request, "logout")
        from django.contrib.auth import logout
        logout(request)
    return redirect("login")


def set_language(request, code):
    if code in LANGS:
        request.session["lang"] = code
        if request.user.is_authenticated:
            Profile.objects.filter(user=request.user).update(language=code)
    nxt = request.META.get("HTTP_REFERER", "")
    host = request.get_host()
    return redirect(nxt if nxt and host in nxt else "home")


# ---------------------------------------------------------------- home / painel
@login_required
def home(request):
    return redirect("fiskal_home" if request.user.profile.is_fiskal else "dashboard")


@role_view("monitor")
def dashboard(request):
    snap = _snapshot_for_page(request.election) if request.election else None
    return render(request, "dashboard.html", {
        "snap": snap, "page": "dashboard", "my_party": request.user.profile.party_id,
    })


@role_view("monitor")
def compare(request):
    snap = _snapshot_for_page(request.election) if request.election else None
    return render(request, "compare.html", {"snap": snap, "page": "compare",
                                            "my_party": request.user.profile.party_id})


@role_view("monitor")
def api_live(request):
    if not request.election:
        return JsonResponse({"error": "no election"}, status=404)
    snap = build_snapshot(request.election)
    level = request.GET.get("level", "municipality")
    key = LEVELS.get(level, "municipalities")
    nodes = snap[key]
    parent = request.GET.get("parent")
    if parent and parent.isdigit():
        if level == "postu":
            nodes = [n for n in nodes if n["parent"] == int(parent)]
        elif level == "suku":  # parent = munisípiu
            postu_ids = {p["id"] for p in snap["postus"] if p["parent"] == int(parent)}
            nodes = [n for n in nodes if n["parent"] in postu_ids]
    return JsonResponse({
        "election": snap["election"], "contestants": snap["contestants"], "national": snap["national"],
        "nodes": nodes, "level": level, "states": snap["states"], "recent": snap["recent"],
        "municipalities": snap["municipalities"], "nasauns": snap["nasauns"], "diaspora": snap["diaspora"],
        "now": timezone.now().isoformat(),
    })


def _csv_safe(v):
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


@role_view("monitor")
def export_csv(request, level):
    key = LEVELS.get(level)
    if not key or not request.election:
        raise Http404
    snap = build_snapshot(request.election)
    cs = snap["contestants"]
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="apuramentu_{level}_{request.election.id}.csv"'
    w = csv.writer(resp)
    w.writerow(["id", "name", "centres_total", "centres_reporting", "registered", "voted", "turnout_pct",
                "blank", "invalid", "valid"] + [f"{c['short']}_votes" for c in cs] + [f"{c['short']}_pct" for c in cs])
    for n in snap[key]:
        w.writerow([n["id"], _csv_safe(n["name"]), n["centres_total"], n["centres_reporting"], n["registered"],
                    n["voted"], n["turnout"], n["blank"], n["invalid"], n["valid"]]
                   + [n["votes"].get(str(c["id"]), 0) for c in cs] + [n["shares"].get(str(c["id"]), 0) for c in cs])
    AuditLog.record(request, "export_csv", target=level)
    return resp


# ---------------------------------------------------------------- fiskál
@role_view("fiskal")
def fiskal_home(request):
    e = request.election
    centres = list(request.user.profile.centres.select_related("village__administrativepost__municipality", "nasaun"))
    rows = []
    if e:
        reps = {}
        for r in (Report.objects.filter(election=e, centre__in=centres).exclude(status=Report.REJECTED)
                  .prefetch_related("lines")):
            reps.setdefault(r.centre_id, []).append(r)
        mine = {r.centre_id: r for r in Report.objects.filter(election=e, submitted_by=request.user)}
        for c in centres:
            own = mine.get(c.id)
            state = resolve_centre(reps[c.id])[1] if c.id in reps else None
            rows.append({"centre": c, "own": own, "state": state})
    done = sum(1 for r in rows if r["own"] and r["own"].status != Report.REJECTED)
    return render(request, "fiskal_home.html", {
        "rows": rows, "done": done, "total": len(rows), "page": "fiskal",
        "pct": round(100 * done / len(rows)) if rows else 0,
    })


@role_view("fiskal")
def submit_report(request, centre_id):
    e = request.election
    centre = get_object_or_404(Centre.objects.select_related("village__administrativepost__municipality", "nasaun"), pk=centre_id)
    if not request.user.profile.centres.filter(pk=centre.pk).exists():
        return render(request, "403.html", status=403)
    contestants = list(Contestant.objects.filter(election=e).select_related("party"))
    existing = Report.objects.filter(election=e, centre=centre, submitted_by=request.user).first()
    locked = bool(existing and existing.status == Report.VERIFIED) or not e.is_active

    initial = {}
    if existing:
        initial = {"voted": existing.voted, "blank": existing.blank, "invalid": existing.invalid,
                   "notes": existing.notes}
        initial.update({f"c_{l.contestant_id}": l.votes for l in existing.lines.all()})

    if request.method == "POST":
        if locked:
            messages.error(request, tr("err_locked", request.lang))
            return redirect("submit_report", centre_id=centre.id)
        form = ReportForm(request.POST, request.FILES, contestants=contestants, centre=centre, lang=request.lang,
                          has_photos=bool(existing and existing.evidence.exists()))
        if form.is_valid():
            d = form.cleaned_data
            with transaction.atomic():
                if existing:
                    report = existing
                    report.version += 1
                    report.status = Report.PENDING
                    report.review_note, report.reviewed_by, report.reviewed_at = "", None, None
                    report.lines.all().delete()
                else:
                    report = Report(election=e, centre=centre, submitted_by=request.user)
                report.voted, report.blank, report.invalid, report.notes = d["voted"], d["blank"], d["invalid"], d["notes"]
                report.save()
                ResultLine.objects.bulk_create(
                    ResultLine(report=report, contestant=c, votes=d[f"c_{c.id}"]) for c in contestants)
                for f, sha, size in form.checked_photos:
                    Evidence.objects.create(report=report, image=f, sha256=sha, size=size)
                report.flags = compute_flags(report, centre)
                report.content_hash = report.compute_hash()
                report.save(update_fields=["flags", "content_hash", "updated_at"])
                AuditLog.record(request, "report_submit" if not existing else "report_update",
                                target=f"{centre.code}", report=report.id, version=report.version,
                                voted=report.voted, hash=report.content_hash)
            invalidate(e.id)
            messages.success(request, tr("saved", request.lang) % {"h": report.content_hash[:16] + "…"})
            return redirect("fiskal_home")
    else:
        form = ReportForm(initial=initial, contestants=contestants, centre=centre, lang=request.lang)

    return render(request, "submit.html", {
        "form": form, "centre": centre, "report": existing, "locked": locked, "page": "fiskal",
        "contestants": [(c, form[f"c_{c.id}"]) for c in contestants],
    })


# ---------------------------------------------------------------- relatóriu / verifikasaun
def _can_view_report(user, report):
    p = user.profile
    return p.can_monitor or report.submitted_by_id == user.id


@role_view()
def report_detail(request, pk):
    report = get_object_or_404(
        Report.objects.select_related("centre__village__administrativepost__municipality", "centre__nasaun", "submitted_by",
                                      "reviewed_by",
                                      "election").prefetch_related("lines__contestant__party", "evidence"), pk=pk)
    if not _can_view_report(request.user, report):
        return render(request, "403.html", status=403)
    siblings = (Report.objects.filter(election=report.election, centre=report.centre).exclude(pk=report.pk)
                .select_related("submitted_by").prefetch_related("lines"))
    lines = sorted(report.lines.all(), key=lambda l: l.contestant.ballot_number)
    sig = report.signature()
    return render(request, "report_detail.html", {
        "report": report, "lines": lines, "siblings": [(s, s.signature() == sig) for s in siblings],
        "integrity": report.integrity_ok(), "page": "verification",
        "history": AuditLog.objects.filter(target=report.centre.code)[:15] if request.user.profile.is_admin else [],
    })


@role_view("admin")
@require_POST
def report_review(request, pk):
    report = get_object_or_404(Report, pk=pk)
    action = request.POST.get("action")
    note = (request.POST.get("note") or "").strip()[:300]
    if action == "verify":
        if not report.integrity_ok():
            messages.error(request, tr("integrity_bad", request.lang))
            return redirect("report_detail", pk=pk)
        report.status = Report.VERIFIED
    elif action == "reject":
        if not note:
            messages.error(request, tr("reason", request.lang))
            return redirect("report_detail", pk=pk)
        report.status = Report.REJECTED
    else:
        raise Http404
    report.review_note, report.reviewed_by, report.reviewed_at = note, request.user, timezone.now()
    report.save()
    AuditLog.record(request, f"report_{action}", target=report.centre.code, report=report.id, note=note,
                    hash=report.content_hash)
    invalidate(report.election_id)
    return redirect("report_detail", pk=pk)


@role_view("admin")
def verification(request):
    e = request.election
    conflicts, flagged, pending = [], [], []
    if e:
        by_centre = {}
        for r in (Report.objects.filter(election=e).exclude(status=Report.REJECTED)
                  .select_related("centre", "submitted_by").prefetch_related("lines")):
            by_centre.setdefault(r.centre_id, []).append(r)
        for cid, rs in by_centre.items():
            if resolve_centre(rs)[1] == "conflict":
                conflicts.append({"centre": rs[0].centre, "reports": rs})
        flagged = [r for rs in by_centre.values() for r in rs if r.flags and r.status == Report.PENDING]
        pending = [r for rs in by_centre.values() for r in rs if r.status == Report.PENDING and not r.flags]
    return render(request, "verification.html", {
        "conflicts": conflicts, "flagged": flagged[:100], "pending": pending[:100], "page": "verification",
    })


@role_view("admin")
def audit(request):
    ok, bad_id, n = AuditLog.verify_chain()
    return render(request, "audit.html", {
        "logs": AuditLog.objects.select_related("user")[:200], "chain_ok": ok, "bad_id": bad_id, "n": n,
        "page": "audit",
    })


@role_view()
def evidence_file(request, pk):
    ev = get_object_or_404(Evidence.objects.select_related("report"), pk=pk)
    if not _can_view_report(request.user, ev.report):
        return render(request, "403.html", status=403)
    try:
        resp = FileResponse(ev.image.open("rb"))
    except FileNotFoundError:
        raise Http404
    resp["Cache-Control"] = "private, no-store"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


# ---------------------------------------------------------------- chatbot
@role_view()
@require_POST
def chat_api(request):
    key = f"chat:{request.user.id}"
    n = cache.get(key, 0)
    if n >= 40:
        return JsonResponse({"a": "…"}, status=429)
    cache.set(key, n + 1, 60)
    try:
        q = json.loads(request.body or b"{}").get("q", "")
    except ValueError:
        q = ""
    q = str(q)[:300].strip()
    if not q:
        return JsonResponse({"a": tr("chat_hello", request.lang)})
    a = chatbot.answer(q, request.lang, request.user.profile, request.election)
    return JsonResponse({"a": a})


@login_required
def i18n_js(request):
    return JsonResponse(all_for(request.lang))
