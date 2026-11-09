import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from . import chatbot
from . import twofa
from .auth_utils import c_user_fun, c_user_party
from .models import (AdministrativePost, AuditLog, Centre, Contestant, Election, Municipality, Nasaun, Party,
                     Profile, Report, TOTPDevice, Village)
from .services import build_snapshot

User = get_user_model()
TMP = tempfile.mkdtemp()


def jpg(size=(40, 40)):
    b = BytesIO()
    Image.new("RGB", size, "white").save(b, "JPEG")
    return SimpleUploadedFile("a.jpg", b.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=TMP)
class Base(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        cache.clear()
        mu = Municipality.objects.create(code="DL", name="Dili", hckey="tl-dl")
        po = AdministrativePost.objects.create(municipality=mu, name="P1")
        su = Village.objects.create(administrativepost=po, name="S1")
        self.c1 = Centre.objects.create(village=su, name="C1", code="DL-1", registered_voters=1000)
        self.c2 = Centre.objects.create(village=su, name="C2", code="DL-2", registered_voters=500)
        self.pt = Nasaun.objects.create(name="Portugal")
        self.c3 = Centre.objects.create(nasaun=self.pt, name="Lisboa", code="DP-1", registered_voters=800)
        self.pa = Party.objects.create(acronym="AAA", name="Alfa", color="#ff0000")
        self.pb = Party.objects.create(acronym="BBB", name="Beta", color="#0000ff")
        self.el = Election.objects.create(name="E", kind="parliamentary", date="2026-01-01")
        self.ka = Contestant.objects.create(election=self.el, party=self.pa, name="Alfa", ballot_number=1)
        self.kb = Contestant.objects.create(election=self.el, party=self.pb, name="Beta", ballot_number=2)
        self.f1 = self.mk("f1", Profile.FISKAL, centres=[self.c1, self.c2])
        self.f2 = self.mk("f2", Profile.FISKAL, centres=[self.c1, self.c2])
        self.admin = self.mk("adm", Profile.ADMIN)
        self.mon = self.mk("mon", Profile.MONITOR)

    def mk(self, name, role, centres=()):
        u = User.objects.create_user(name, password="Str0ng-pass-123")
        u.profile.role = role
        u.profile.save()
        u.profile.centres.set(centres)
        return u

    def login(self, user):
        self.client.force_login(user)
        s = self.client.session
        s["otp_ok"] = True  # 2FA diskute iha TwoFactorTests
        s.save()

    def post(self, user, centre, a, b, blank=0, invalid=0, voted=None, photo=True):
        self.login(user)
        data = {"c_%d" % self.ka.id: a, "c_%d" % self.kb.id: b, "blank": blank, "invalid": invalid,
                "voted": a + b + blank + invalid if voted is None else voted, "notes": ""}
        if photo:
            data["photos"] = jpg()
        return self.client.post(reverse("submit_report", args=[centre.id]), data)


class SubmitTests(Base):
    def test_valid_submission_creates_hashed_report(self):
        r = self.post(self.f1, self.c1, 300, 200, 5, 5)
        self.assertEqual(r.status_code, 302)
        rep = Report.objects.get()
        self.assertTrue(rep.integrity_ok())
        self.assertEqual(rep.evidence.count(), 1)
        self.assertEqual(len(rep.content_hash), 64)

    def test_sum_mismatch_rejected(self):
        r = self.post(self.f1, self.c1, 300, 200, 5, 5, voted=999)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Report.objects.exists())

    def test_cannot_exceed_registered(self):
        r = self.post(self.f1, self.c2, 400, 200)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Report.objects.exists())

    def test_photo_required_and_validated(self):
        self.post(self.f1, self.c1, 10, 10, photo=False)
        self.assertFalse(Report.objects.exists())
        self.login(self.f1)
        bad = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
        self.client.post(reverse("submit_report", args=[self.c1.id]),
                         {"c_%d" % self.ka.id: 1, "c_%d" % self.kb.id: 1, "blank": 0, "invalid": 0, "voted": 2,
                          "photos": bad})
        self.assertFalse(Report.objects.exists())

    def test_fiskal_only_assigned_centre(self):
        other = self.mk("f3", Profile.FISKAL)
        self.login(other)
        self.assertEqual(self.client.get(reverse("submit_report", args=[self.c1.id])).status_code, 403)

    def test_verified_report_locked(self):
        self.post(self.f1, self.c1, 10, 10)
        rep = Report.objects.get()
        rep.status = Report.VERIFIED
        rep.save()
        self.post(self.f1, self.c1, 20, 20)
        rep.refresh_from_db()
        self.assertEqual(rep.voted, 20)  # la muda


class ConsolidationTests(Base):
    def snap(self):
        cache.clear()
        return build_snapshot(self.el, use_cache=False)

    def test_single_is_provisional_and_counted(self):
        self.post(self.f1, self.c1, 300, 200)
        s = self.snap()
        self.assertEqual(s["states"]["provisional"], 1)
        self.assertEqual(s["national"]["valid"], 500)

    def test_two_identical_is_consensus(self):
        self.post(self.f1, self.c1, 300, 200)
        self.post(self.f2, self.c1, 300, 200)
        s = self.snap()
        self.assertEqual(s["states"]["consensus"], 1)
        self.assertEqual(s["national"]["valid"], 500)  # la dupla

    def test_conflict_excluded_until_verified(self):
        self.post(self.f1, self.c1, 300, 200)
        self.post(self.f2, self.c1, 310, 190)
        s = self.snap()
        self.assertEqual(s["states"]["conflict"], 1)
        self.assertEqual(s["national"]["valid"], 0)
        self.assertEqual(s["national"]["conflicts"], 1)
        rep = Report.objects.get(submitted_by=self.f2)
        self.login(self.admin)
        self.client.post(reverse("report_review", args=[rep.id]), {"action": "verify"})
        s = self.snap()
        self.assertEqual(s["states"]["verified"], 1)
        self.assertEqual(s["national"]["votes"][str(self.ka.id)], 310)

    def test_reject_requires_reason_and_excludes(self):
        self.post(self.f1, self.c1, 300, 200)
        rep = Report.objects.get()
        self.login(self.admin)
        self.client.post(reverse("report_review", args=[rep.id]), {"action": "reject"})
        rep.refresh_from_db()
        self.assertEqual(rep.status, Report.PENDING)
        self.client.post(reverse("report_review", args=[rep.id]), {"action": "reject", "note": "foto la klaru"})
        rep.refresh_from_db()
        self.assertEqual(rep.status, Report.REJECTED)
        self.assertEqual(self.snap()["national"]["valid"], 0)

    def test_tampered_report_cannot_be_verified(self):
        self.post(self.f1, self.c1, 300, 200)
        Report.objects.update(voted=999)  # manipulasaun diretu iha DB
        rep = Report.objects.get()
        # hash la hatene voted, tamba ne'e muda lines
        rep.lines.filter(contestant=self.ka).update(votes=1)
        self.assertFalse(Report.objects.get().integrity_ok())
        self.login(self.admin)
        self.client.post(reverse("report_review", args=[rep.id]), {"action": "verify"})
        self.assertEqual(Report.objects.get().status, Report.PENDING)


class SecurityTests(Base):
    def test_audit_chain_detects_tampering(self):
        self.post(self.f1, self.c1, 1, 1)
        self.post(self.f2, self.c1, 1, 1)
        ok, bad, n = AuditLog.verify_chain()
        self.assertTrue(ok)
        self.assertGreaterEqual(n, 2)
        first = AuditLog.objects.order_by("id").first()
        AuditLog.objects.filter(pk=first.pk).update(target="TAMPERED")
        ok, bad, _ = AuditLog.verify_chain()
        self.assertFalse(ok)
        self.assertEqual(bad, first.pk)

    def test_audit_immutable(self):
        a = AuditLog.record(self.admin, "x")
        with self.assertRaises(PermissionError):
            a.delete()
        with self.assertRaises(PermissionError):
            a.save()

    def test_login_lockout(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "adm", "password": "wrong"})
        r = self.client.post(reverse("login"), {"username": "adm", "password": "Str0ng-pass-123"})
        self.assertEqual(r.status_code, 429)

    def test_anonymous_redirected(self):
        for name in ("dashboard", "compare", "api_live", "fiskal_home", "verification", "audit", "twofa_setup"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_role_isolation(self):
        self.login(self.f1)
        for name in ("dashboard", "compare", "api_live", "verification", "audit"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.login(self.mon)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("verification")).status_code, 403)
        self.assertEqual(self.client.get(reverse("fiskal_home")).status_code, 403)

    def test_evidence_protected(self):
        self.post(self.f1, self.c1, 1, 1)
        ev = Report.objects.get().evidence.get()
        self.client.logout()
        self.assertEqual(self.client.get(reverse("evidence_file", args=[ev.id])).status_code, 302)
        outsider = self.mk("f9", Profile.FISKAL)
        self.login(outsider)
        self.assertEqual(self.client.get(reverse("evidence_file", args=[ev.id])).status_code, 403)
        self.login(self.mon)
        self.assertEqual(self.client.get(reverse("evidence_file", args=[ev.id])).status_code, 200)

    def test_security_headers(self):
        r = self.client.get(reverse("login"))
        self.assertIn("default-src 'self'", r["Content-Security-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")


class ApiAndChatTests(Base):
    def test_api_and_csv(self):
        self.post(self.f1, self.c1, 300, 200, 5, 5)
        self.login(self.mon)
        d = self.client.get(reverse("api_live")).json()
        self.assertEqual(d["national"]["valid"], 500)
        self.assertEqual(d["national"]["leader"], self.ka.id)
        self.assertEqual(self.client.get(reverse("api_live") + "?level=suku").json()["level"], "suku")
        r = self.client.get(reverse("export_csv", args=["municipality"]))
        self.assertIn("Dili", r.content.decode())

    def test_chatbot_multilingual(self):
        self.post(self.f1, self.c1, 300, 200)
        p = self.mon.profile
        for lang, q in (("tet", "Sé lidera?"), ("pt", "Quem lidera?"), ("en", "who leads?"), ("id", "siapa unggul?")):
            a = chatbot.answer(q, lang, p, self.el)
            self.assertIn("AAA", a, (lang, a))
        self.assertIn("Dili", chatbot.answer("rezultadu Dili", "tet", p, self.el))
        self.assertIn("AAA", chatbot.answer("AAA", "en", p, self.el))
        self.assertIn("SHA-256", chatbot.answer("oinsá hatama dadus", "tet", p, self.el))

    def test_chatbot_fiskal_no_results(self):
        a = chatbot.answer("who leads?", "en", self.f1.profile, self.el)
        self.assertIn("no access", a)

    def test_chat_endpoint(self):
        self.login(self.mon)
        r = self.client.post(reverse("chat_api"), data='{"q":"seguransa"}', content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("hash", r.json()["a"].lower())


class TwoFactorTests(Base):
    def test_rfc6238_vector(self):
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"
        self.assertEqual(twofa.totp_at(secret, 59, digits=8), "94287082")
        self.assertEqual(twofa.totp_at(secret, 1111111109, digits=8), "07081804")

    def test_verify_window_and_replay(self):
        sec = twofa.new_secret()
        code = twofa.totp_at(sec)
        c = twofa.verify(sec, code)
        self.assertTrue(c)
        self.assertIsNone(twofa.verify(sec, code, last_counter=c))  # replay
        self.assertIsNone(twofa.verify(sec, "000000" if code != "000000" else "111111"))
        self.assertIsNone(twofa.verify(sec, "abc"))

    def enable(self, user):
        self.client.force_login(user)
        self.client.get(reverse("twofa_setup"))
        dev = TOTPDevice.objects.get(user=user)
        r = self.client.post(reverse("twofa_setup"), {"code": twofa.totp_at(dev.secret)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(user.recovery_codes.count(), 8)
        return TOTPDevice.objects.get(user=user), r.context["codes"]

    def test_admin_forced_to_setup(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("audit"))
        self.assertRedirects(r, reverse("twofa_setup"), fetch_redirect_response=False)
        self.client.force_login(self.mon)  # monitór la obrigatóriu
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_full_flow_enable_logout_verify(self):
        dev, codes = self.enable(self.mon)
        self.client.post(reverse("logout"))
        r = self.client.post(reverse("login"), {"username": "mon", "password": "Str0ng-pass-123"})
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(self.client.get(reverse("dashboard")), "/2fa/verify/?next=/painel/", fetch_redirect_response=False)
        # kódigu sala
        self.client.post(reverse("twofa_verify"), {"code": "123456"})
        self.assertRedirects(self.client.get(reverse("dashboard")), "/2fa/verify/?next=/painel/", fetch_redirect_response=False)
        dev.refresh_from_db()
        ok = self.client.post(reverse("twofa_verify"), {"code": twofa.totp_at(dev.secret, __import__("time").time() + 30)})
        self.assertEqual(ok.status_code, 302)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_recovery_code_single_use(self):
        dev, codes = self.enable(self.mon)
        for _ in range(2):
            self.client.post(reverse("logout"))
            self.client.post(reverse("login"), {"username": "mon", "password": "Str0ng-pass-123"})
            self.client.post(reverse("twofa_verify"), {"code": codes[0]})
            ok = self.client.get(reverse("dashboard")).status_code == 200
            self.assertEqual(ok, _ == 0)

    def test_2fa_lockout(self):
        self.enable(self.mon)
        self.client.post(reverse("logout"))
        self.client.post(reverse("login"), {"username": "mon", "password": "Str0ng-pass-123"})
        for _ in range(5):
            self.client.post(reverse("twofa_verify"), {"code": "000000"})
        dev = TOTPDevice.objects.get(user=self.mon)
        self.client.post(reverse("twofa_verify"), {"code": twofa.totp_at(dev.secret, __import__("time").time() + 30)})
        self.assertRedirects(self.client.get(reverse("dashboard")), "/2fa/verify/?next=/painel/", fetch_redirect_response=False)

    def test_admin_cannot_disable(self):
        dev, _ = self.enable(self.admin)
        r = self.client.post(reverse("twofa_disable"), {"password": "Str0ng-pass-123", "code": "1"})
        self.assertTrue(TOTPDevice.objects.filter(user=self.admin).exists())


class DiasporaAndHelperTests(Base):
    def test_helpers(self):
        self.assertEqual(c_user_fun(self.f1), self.f1.profile)
        self.assertEqual(c_user_fun(User(username="ghost")), "")
        self.assertEqual(c_user_fun(None), "")
        self.f1.profile.party = self.pa
        self.f1.profile.save()
        self.assertEqual(c_user_party(self.f1), self.pa)
        self.assertEqual(c_user_party(self.f2), "")

    def test_groups_synced(self):
        self.assertEqual(list(self.admin.groups.values_list("name", flat=True)), ["admin"])
        self.assertEqual(list(self.f1.groups.values_list("name", flat=True)), ["fiskal"])

    def test_diaspora_counted_and_listed(self):
        f = self.mk("fd", Profile.FISKAL, centres=[self.c3])
        self.post(f, self.c3, 300, 100)
        self.post(self.f1, self.c1, 10, 5)
        cache.clear()
        s = build_snapshot(self.el, use_cache=False)
        self.assertEqual(s["national"]["valid"], 415)
        self.assertEqual(s["diaspora"]["valid"], 400)
        self.assertEqual(s["nasauns"][0]["name"], "Portugal")
        self.assertEqual(s["municipalities"][0]["hckey"], "tl-dl")
        self.assertEqual(s["municipalities"][0]["valid"], 15)
        self.login(self.mon)
        self.assertEqual(self.client.get(reverse("api_live") + "?level=nasaun").json()["nodes"][0]["valid"], 400)
        self.assertIn("Portugal", self.client.get(reverse("export_csv", args=["nasaun"])).content.decode())
        self.assertIn("Portugal", chatbot.answer("resultados Portugal", "pt", self.mon.profile, self.el))
        self.assertIn("Diáspora", chatbot.answer("diaspora", "pt", self.mon.profile, self.el))
        self.login(f)
        self.assertEqual(self.client.get(reverse("fiskal_list")).status_code, 200)
        self.assertIn("Diáspora", self.c3.location)

    def test_geojson_served_and_matches_hckeys(self):
        import json
        from django.conf import settings
        d = json.load(open(settings.BASE_DIR / "static/geo/tl-all.geo.json"))
        keys = {f["properties"]["hc-key"] for f in d["features"]}
        self.assertIn("tl-dl", keys)
        self.login(self.mon)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("geo/tl-all.geo.json", html)


class OnceEditTests(Base):
    def test_login_redirects_to_form_then_list(self):
        self.login(self.f1)
        r = self.client.get(reverse("fiskal_home"))
        self.assertRedirects(r, reverse("submit_report", args=[self.c1.id]), fetch_redirect_response=False)
        self.post(self.f1, self.c1, 10, 10)
        r = self.client.get(reverse("fiskal_home"))  # sentru 2 seidauk
        self.assertRedirects(r, reverse("submit_report", args=[self.c2.id]), fetch_redirect_response=False)
        self.post(self.f1, self.c2, 5, 5)
        self.assertRedirects(self.client.get(reverse("fiskal_home")), reverse("fiskal_list"), fetch_redirect_response=False)

    def test_input_once_edit_once(self):
        self.post(self.f1, self.c1, 10, 10)
        self.post(self.f1, self.c1, 20, 20, photo=False)  # edit #1 OK
        rep = Report.objects.get()
        self.assertEqual((rep.voted, rep.version), (40, 2))
        self.post(self.f1, self.c1, 30, 30, photo=False)  # edit #2 BLOKE
        rep.refresh_from_db()
        self.assertEqual((rep.voted, rep.version), (40, 2))
        r = self.client.get(reverse("submit_report", args=[self.c1.id]))
        self.assertTrue(r.context["locked"])
        self.assertContains(r, "once locked")

    def test_rejected_can_be_corrected(self):
        self.post(self.f1, self.c1, 10, 10)
        self.post(self.f1, self.c1, 11, 11, photo=False)
        rep = Report.objects.get()
        self.login(self.admin)
        self.client.post(reverse("report_review", args=[rep.id]), {"action": "reject", "note": "foto la klaru"})
        self.post(self.f1, self.c1, 12, 12, photo=False)
        rep.refresh_from_db()
        self.assertEqual((rep.voted, rep.status), (24, Report.PENDING))

    def test_dashboard_is_sidebar_free_fullscreen(self):
        self.login(self.mon)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn('class="shell focus"', html)
        self.assertNotIn('id="side"', html)
        self.assertIn('id="fsBtn"', html)
        self.login(self.f1)
        html = self.client.get(reverse("submit_report", args=[self.c1.id])).content.decode()
        self.assertNotIn('id="side"', html)
        # halaman seluk mantein sidebar
        self.login(self.mon)
        self.assertIn('id="side"', self.client.get(reverse("compare")).content.decode())
