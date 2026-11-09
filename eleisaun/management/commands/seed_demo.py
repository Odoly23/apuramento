"""Hamosu dadus DEMO (fiktisiu) — la'ós rezultadu loloos. Partidu no kandidatu hotu imajinárius."""
import random
import secrets
from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from eleisaun.models import (AuditLog, Centre, Contestant, Election, Evidence, Municipality, Party, Postu,
                             Profile, Report, ResultLine, Suku)
from eleisaun.services import compute_flags

User = get_user_model()

MUNIS = [("AL", "Aileu"), ("AN", "Ainaro"), ("AT", "Atauro"), ("BC", "Baucau"), ("BB", "Bobonaro"),
         ("CL", "Cova Lima"), ("DL", "Dili"), ("ER", "Ermera"), ("LT", "Lautém"), ("LQ", "Liquiçá"),
         ("MT", "Manatuto"), ("MF", "Manufahi"), ("VQ", "Viqueque"), ("OE", "Oé-Cusse Ambeno")]

PARTIES = [("PAU", "Partidu Aurora Foun", "#e11d48"), ("PUN", "Partidu Unidade Nasionál", "#2563eb"),
           ("PHD", "Partidu Harii Dame", "#16a34a"), ("PBL", "Partidu Bandeira Liberdade", "#f59e0b"),
           ("PTF", "Partidu Timor Futuru", "#7c3aed"), ("PSD", "Partidu Solidariedade Demokrátiku", "#0891b2"),
           ("PKL", "Partidu Klibur Lian Povu", "#db2777"), ("PRM", "Partidu Reforma Moderna", "#64748b")]


def fake_sheet(centre, report_lines, voted, blank, invalid, who):
    img = Image.new("RGB", (720, 960), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 700, 940], outline="black", width=3)
    d.text((40, 40), f"DEMO · ATA APURAMENTU · {centre.code}", fill="black")
    d.text((40, 70), centre.name, fill="black")
    y = 120
    for name, v in report_lines:
        d.text((40, y), name, fill="black"); d.text((560, y), str(v), fill="black"); y += 34
    d.text((40, y + 10), f"Brankus: {blank}   Nulu: {invalid}   Total: {voted}", fill="black")
    d.text((40, 900), f"Fiskal: {who} (imajen DEMO)", fill="gray")
    buf = BytesIO(); img.save(buf, "JPEG", quality=70)
    return buf.getvalue()


class Command(BaseCommand):
    help = "Hamosu dadus DEMO fiktisiu ba teste (partidu, jeografia, relatóriu, utilizadór)."

    def add_arguments(self, p):
        p.add_argument("--reset", action="store_true", help="Hamoos dadus eleitorál molok hamosu fali.")
        p.add_argument("--seed", type=int, default=2026)
        p.add_argument("--password", default=None)

    @transaction.atomic
    def handle(self, *a, **o):
        rnd = random.Random(o["seed"])
        if o["reset"]:
            for m in (Evidence, ResultLine, Report, Contestant, Election, Party, Centre, Suku, Postu, Municipality,
                      AuditLog):
                m.objects.all().delete()
            User.objects.exclude(is_superuser=True).delete()
        elif Municipality.objects.exists():
            self.stderr.write("Dadus iha ona. Uza --reset.")
            return

        pw = o["password"] or secrets.token_urlsafe(10)

        # ---- jeografia
        centres_by_muni = {}
        n = 0
        for code, name in MUNIS:
            mu = Municipality.objects.create(code=code, name=name, is_special=(code == "OE"))
            lst = []
            for pi in range(1, 4):
                po = Postu.objects.create(municipality=mu, name=f"Postu {name} {pi}")
                for si in range(1, 4):
                    su = Suku.objects.create(postu=po, name=f"Suku {name} {pi}.{si}")
                    for ci in range(1, rnd.choice([2, 2, 3]) + 1):
                        n += 1
                        lst.append(Centre.objects.create(
                            suku=su, name=f"Sentru {su.name} #{ci}", code=f"{code}-{n:04d}",
                            registered_voters=rnd.randint(350, 1400)))
            centres_by_muni[mu.id] = lst

        # ---- partidu & eleisaun
        parties = [Party.objects.create(acronym=a, name=nm, color=c) for a, nm, c in PARTIES]
        par = Election.objects.create(name="Eleisaun Parlamentu Nasionál (DEMO)", kind=Election.PARLIAMENTARY,
                                      date=date.today())
        pres = Election.objects.create(name="Eleisaun Prezidensiál (DEMO)", kind=Election.PRESIDENTIAL,
                                       date=date.today())
        par_c = [Contestant.objects.create(election=par, party=p, name=p.name, ballot_number=i + 1)
                 for i, p in enumerate(parties)]
        pres_c = [Contestant.objects.create(election=pres, party=parties[i], name=f"Kandidatu {chr(65 + i)} (DEMO)",
                                            ballot_number=i + 1) for i in range(4)]

        # ---- utilizadór
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            admin = User.objects.create_superuser("admin", "admin@example.com", pw)
            admin.profile.role = Profile.ADMIN
            admin.profile.save()
        v = User.objects.create_user("verifikador", password=pw, is_staff=False)
        v.profile.role = Profile.ADMIN; v.profile.organization = "STAE/CNE (demo)"; v.profile.save()
        m1 = User.objects.create_user("mdi", password=pw)
        m1.profile.organization = "MDI"; m1.profile.save()
        m2 = User.objects.create_user("pau_nain", password=pw)
        m2.profile.organization = "Nain-Partidu PAU"; m2.profile.party = parties[0]; m2.profile.save()

        fiskais = {}
        for mu in Municipality.objects.all():
            fl = []
            for k in range(1, 4):
                u = User.objects.create_user(f"fiskal_{mu.code.lower()}_{k}", password=pw)
                pt = parties[(mu.id + k) % len(parties)]
                u.profile.role = Profile.FISKAL; u.profile.party = pt
                u.profile.organization = f"Fiskál {pt.acronym}"; u.profile.save()
                u.profile.centres.set(centres_by_muni[mu.id])
                fl.append(u)
            fiskais[mu.id] = fl

        # ---- relatóriu
        total_reports = 0
        for election, contestants, coverage in ((par, par_c, 0.7), (pres, pres_c, 0.35)):
            base = [rnd.uniform(0.6, 1.6) for _ in contestants]
            for mu in Municipality.objects.all():
                bias = [b * rnd.lognormvariate(0, 0.45) for b in base]
                for ce in centres_by_muni[mu.id]:
                    if rnd.random() > coverage:
                        continue
                    k = rnd.choices([1, 2, 3], [0.55, 0.35, 0.10])[0]
                    voted = int(ce.registered_voters * rnd.uniform(0.55, 0.92))
                    blank, invalid = int(voted * rnd.uniform(0.005, 0.03)), int(voted * rnd.uniform(0.005, 0.03))
                    valid = voted - blank - invalid
                    w = [b * rnd.uniform(0.8, 1.25) for b in bias]
                    s = sum(w)
                    votes = [int(valid * x / s) for x in w]
                    votes[0] += valid - sum(votes)
                    conflict = k >= 2 and rnd.random() < 0.15
                    for i, u in enumerate(rnd.sample(fiskais[mu.id], k)):
                        vts, bl, inv = list(votes), blank, invalid
                        if conflict and i == 1:
                            j, l = rnd.sample(range(len(vts)), 2)
                            shift = min(vts[j], rnd.randint(3, 20)); vts[j] -= shift; vts[l] += shift
                        r = Report.objects.create(election=election, centre=ce, submitted_by=u, voted=voted,
                                                  blank=bl, invalid=inv,
                                                  created_at=timezone.now() - timedelta(minutes=rnd.randint(1, 600)))
                        ResultLine.objects.bulk_create(ResultLine(report=r, contestant=c, votes=x)
                                                       for c, x in zip(contestants, vts))
                        img = fake_sheet(ce, [(c.name, x) for c, x in zip(contestants, vts)], voted, bl, inv,
                                         u.get_username())
                        import hashlib
                        ev = Evidence(report=r, sha256=hashlib.sha256(img).hexdigest(), size=len(img))
                        ev.image.save("ata.jpg", ContentFile(img), save=True)
                        r.flags = compute_flags(r, ce)
                        r.content_hash = r.compute_hash()
                        if not conflict and rnd.random() < 0.25:
                            r.status, r.reviewed_by, r.reviewed_at = Report.VERIFIED, v, timezone.now()
                        r.save()
                        AuditLog.record(u, "report_submit", target=ce.code, report=r.id, version=1, voted=voted,
                                        hash=r.content_hash)
                        total_reports += 1

        self.stdout.write(self.style.SUCCESS(f"Sentru: {n} · relatóriu: {total_reports}"))
        self.stdout.write("Utilizadór DEMO (password hanesan hotu): " + self.style.WARNING(pw))
        self.stdout.write("  admin / verifikador (admin) · mdi (monitór) · pau_nain (nain-partidu) · fiskal_dl_1 (fiskál Dili)")
        self.stdout.write(self.style.WARNING("DADUS FIKTISIU — la bele uza iha produksaun."))
