import hashlib
import json
import uuid

from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


# --------------------------------------------------------------------------
# Jeografia: Municipality > AdministrativePost > Village > Aldeia > Centre
# + Nasaun (diáspora: sentru votasaun iha rai-li'ur)
# --------------------------------------------------------------------------
class Municipality(models.Model):
    code = models.CharField(max_length=5, null=True)
    name = models.CharField(max_length=50, verbose_name="Naran")
    hckey = models.CharField(max_length=10, null=True, blank=True, help_text="Highcharts hc-key, ez. tl-dl")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        template = '{0.name}'
        return template.format(self)


class AdministrativePost(models.Model):
    municipality = models.ForeignKey(Municipality, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=100, verbose_name="Naran")

    class Meta:
        ordering = ["municipality__name", "name"]

    def __str__(self):
        template = '{0.name}'
        return template.format(self)


class Village(models.Model):
    administrativepost = models.ForeignKey(AdministrativePost, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=100, verbose_name="Naran")

    class Meta:
        ordering = ["administrativepost__name", "name"]

    def __str__(self):
        template = '{0.name}'
        return template.format(self)


class Aldeia(models.Model):
    village = models.ForeignKey(Village, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        template = '{0.name}'
        return template.format(self)


class Nasaun(models.Model):
    name = models.CharField(max_length=50, verbose_name='Nasaun')

    class Meta:
        ordering = ["name"]

    def __str__(self):
        template = '{0.name}'
        return template.format(self)


class Centre(models.Model):
    """Sentru votasaun: iha Timor (village/aldeia) ka diáspora (nasaun)."""

    village = models.ForeignKey(Village, on_delete=models.CASCADE, null=True, blank=True, related_name="centres")
    aldeia = models.ForeignKey(Aldeia, on_delete=models.SET_NULL, null=True, blank=True)
    nasaun = models.ForeignKey(Nasaun, on_delete=models.CASCADE, null=True, blank=True, related_name="centres",
                               help_text="Hili de'it ba sentru diáspora (la iha village)")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, unique=True)
    registered_voters = models.PositiveIntegerField("Eleitór rejistadu", default=0)

    class Meta:
        ordering = ["code"]
        verbose_name = "Sentru votasaun"
        verbose_name_plural = "Sentru votasaun"

    def __str__(self):
        return f"{self.code} · {self.name}"

    @property
    def is_diaspora(self):
        return self.village_id is None and self.nasaun_id is not None

    @property
    def municipality(self):
        return self.village.administrativepost.municipality if self.village_id else None

    @property
    def location(self):
        if self.is_diaspora:
            return f"Diáspora · {self.nasaun}"
        if not self.village_id:
            return "—"
        v = self.village
        return f"{v.name} · {v.administrativepost.name} · {v.administrativepost.municipality.name}"


# --------------------------------------------------------------------------
# Eleisaun, Partidu, Kandidatu/Lista
# --------------------------------------------------------------------------
class Election(models.Model):
    PRESIDENTIAL = "presidential"
    PARLIAMENTARY = "parliamentary"
    KINDS = [(PRESIDENTIAL, "Prezidensiál"), (PARLIAMENTARY, "Parlamentu Nasionál")]

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=KINDS)
    round = models.PositiveSmallIntegerField(default=1)
    date = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-date", "name"]
        verbose_name = "Eleisaun"
        verbose_name_plural = "Eleisaun"

    def __str__(self):
        return self.name


class Party(models.Model):
    name = models.CharField(max_length=120)
    acronym = models.CharField(max_length=20, unique=True)
    color = models.CharField(max_length=7, default="#3b82f6", help_text="Hex, ez. #e11d48")

    class Meta:
        ordering = ["acronym"]
        verbose_name = "Partidu"
        verbose_name_plural = "Partidu"

    def __str__(self):
        return self.acronym


class Contestant(models.Model):
    """Lista partidu (parlamentu) ka kandidatu (prezidensiál) iha boletin."""

    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="contestants")
    party = models.ForeignKey(Party, on_delete=models.SET_NULL, null=True, blank=True, related_name="contestants")
    name = models.CharField(max_length=120)
    ballot_number = models.PositiveSmallIntegerField("Númeru iha boletin")

    class Meta:
        ordering = ["election", "ballot_number"]
        unique_together = [("election", "ballot_number")]
        verbose_name = "Kandidatu / Lista"
        verbose_name_plural = "Kandidatu / Lista"

    def __str__(self):
        return f"{self.ballot_number}. {self.name}"

    @property
    def color(self):
        return self.party.color if self.party else "#64748b"

    @property
    def short(self):
        return self.party.acronym if self.party else self.name[:6]


# --------------------------------------------------------------------------
# Utilizadór ho papél
# --------------------------------------------------------------------------
class Profile(models.Model):
    ADMIN = "admin"
    FISKAL = "fiskal"
    MONITOR = "monitor"
    ROLES = [
        (ADMIN, "Verifikadór / Admin"),
        (FISKAL, "Fiskál"),
        (MONITOR, "Monitór (organizasaun / partidu)"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=ROLES, default=MONITOR)
    organization = models.CharField("Organizasaun", max_length=120, blank=True, help_text="Ez. MDI, ONG, media")
    party = models.ForeignKey(Party, on_delete=models.SET_NULL, null=True, blank=True)
    centres = models.ManyToManyField(Centre, blank=True, related_name="fiskais",
                                     help_text="Sentru ne'ebé fiskál ne'e iha direitu atu hatama dadus")
    language = models.CharField(max_length=3, default="tet")

    class Meta:
        verbose_name = "Perfíl"
        verbose_name_plural = "Perfíl"

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == self.ADMIN or self.user.is_superuser

    @property
    def is_fiskal(self):
        return self.role == self.FISKAL

    @property
    def can_monitor(self):
        return self.is_admin or self.role == self.MONITOR


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(
            user=instance, defaults={"role": Profile.ADMIN if instance.is_superuser else Profile.MONITOR}
        )


# --------------------------------------------------------------------------
# Relatóriu rezultadu husi fiskál + prova foto
# --------------------------------------------------------------------------
class Report(models.Model):
    PENDING, VERIFIED, REJECTED = "pending", "verified", "rejected"
    STATUSES = [(PENDING, "Hein verifikasaun"), (VERIFIED, "Verifikadu"), (REJECTED, "Rejeitadu")]

    election = models.ForeignKey(Election, on_delete=models.PROTECT, related_name="reports")
    centre = models.ForeignKey(Centre, on_delete=models.PROTECT, related_name="reports")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reports")
    voted = models.PositiveIntegerField("Total eleitór ne'ebé vota")
    blank = models.PositiveIntegerField("Votu brankus", default=0)
    invalid = models.PositiveIntegerField("Votu nulu", default=0)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    review_note = models.CharField(max_length=300, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="reviewed_reports")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    flags = models.JSONField(default=list, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("election", "centre", "submitted_by")]
        ordering = ["-updated_at"]
        verbose_name = "Relatóriu"
        verbose_name_plural = "Relatóriu"

    def __str__(self):
        return f"{self.centre.code} / {self.submitted_by} v{self.version}"

    @property
    def total_candidate_votes(self):
        return sum(line.votes for line in self.lines.all())

    def signature(self):
        """Asinatura rezultadu — hodi kompara relatóriu husi fiskál oioin."""
        return (
            self.voted, self.blank, self.invalid,
            tuple(sorted((l.contestant_id, l.votes) for l in self.lines.all())),
        )

    def compute_hash(self):
        payload = {
            "election": self.election_id, "centre": self.centre_id, "by": self.submitted_by_id,
            "voted": self.voted, "blank": self.blank, "invalid": self.invalid, "version": self.version,
            "lines": sorted((l.contestant_id, l.votes) for l in self.lines.all()),
            "evidence": sorted(e.sha256 for e in self.evidence.all()),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def integrity_ok(self):
        return bool(self.content_hash) and self.content_hash == self.compute_hash()


class ResultLine(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="lines")
    contestant = models.ForeignKey(Contestant, on_delete=models.PROTECT)
    votes = models.PositiveIntegerField()

    class Meta:
        unique_together = [("report", "contestant")]


def evidence_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"evidence/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.{ext}"


class Evidence(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="evidence")
    image = models.ImageField(upload_to=evidence_path)
    sha256 = models.CharField(max_length=64)
    size = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Prova foto"
        verbose_name_plural = "Prova foto"


# --------------------------------------------------------------------------
# Audit log ho korrente hash (tamper-evident) — la bele muda/hamoos
# --------------------------------------------------------------------------
class AuditLog(models.Model):
    created = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=40)
    target = models.CharField(max_length=200, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    prev_hash = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Audit log"
        verbose_name_plural = "Audit log"

    def _digest(self):
        body = json.dumps(
            {"c": self.created.isoformat(), "u": self.username, "a": self.action, "t": self.target,
             "d": self.detail, "ip": self.ip, "p": self.prev_hash},
            sort_keys=True, default=str,
        )
        return hashlib.sha256(body.encode()).hexdigest()

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("Audit log la bele muda.")
        with transaction.atomic():
            last = AuditLog.objects.select_for_update().order_by("-id").first()
            self.prev_hash = last.hash if last else "0" * 64
            self.hash = self._digest()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit log la bele hamoos.")

    @classmethod
    def record(cls, request_or_user, action, target="", ip=None, **detail):
        user = getattr(request_or_user, "user", request_or_user)
        if ip is None and hasattr(request_or_user, "META"):
            ip = client_ip(request_or_user)
        authed = user is not None and getattr(user, "is_authenticated", False)
        return cls.objects.create(
            user=user if authed else None,
            username=user.get_username() if authed else detail.pop("username", ""),
            action=action, target=target, detail=detail, ip=ip,
        )

    @classmethod
    def verify_chain(cls):
        """Return (ok, id_ne'ebé kuak ka None, total)."""
        prev = "0" * 64
        n = 0
        for row in cls.objects.order_by("id").iterator():
            n += 1
            if row.prev_hash != prev or row.hash != row._digest():
                return False, row.id, n
            prev = row.hash
        return True, None, n


def client_ip(request):
    return request.META.get("REMOTE_ADDR") or None


# --------------------------------------------------------------------------
# 2FA (TOTP, RFC 6238) + kódigu rekuperasaun
# --------------------------------------------------------------------------
class TOTPDevice(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="totp")
    secret = models.CharField(max_length=64)
    confirmed = models.BooleanField(default=False)
    last_counter = models.BigIntegerField(default=0)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Dispozitivu 2FA"
        verbose_name_plural = "Dispozitivu 2FA"


class RecoveryCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)


@receiver(post_save, sender=Profile)
def sync_group(sender, instance, **kwargs):
    """Papél -> Django Group ho naran hanesan (admin / fiskal / monitor), ba admin site no relatóriu."""
    from django.contrib.auth.models import Group
    names = [r for r, _ in Profile.ROLES]
    keep, _ = Group.objects.get_or_create(name=instance.role)
    instance.user.groups.remove(*Group.objects.filter(name__in=names).exclude(pk=keep.pk))
    instance.user.groups.add(keep)
