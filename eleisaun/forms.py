import hashlib
import io

from django import forms
from django.conf import settings
from PIL import Image, UnidentifiedImageError

from .i18n import tr

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/jpeg,image/png,image/webp",
                                                              "capture": "environment"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data if d]
        return [single(data, initial)] if data else []


def validate_image(f):
    """Valida foto loloos (la sufisiente ho extensaun): konteúdu real, formatu, tamañu."""
    if f.size > settings.MAX_EVIDENCE_BYTES:
        raise ValueError("size")
    data = f.read()
    f.seek(0)
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError("format")
    if fmt not in ALLOWED_FORMATS:
        raise ValueError("format")
    return hashlib.sha256(data).hexdigest(), len(data)


class ReportForm(forms.Form):
    voted = forms.IntegerField(min_value=0)
    blank = forms.IntegerField(min_value=0, initial=0)
    invalid = forms.IntegerField(min_value=0, initial=0)
    notes = forms.CharField(required=False, max_length=1000, widget=forms.Textarea(attrs={"rows": 2}))
    photos = MultipleFileField(required=False)

    def __init__(self, *args, contestants, centre, lang="tet", has_photos=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.contestants, self.centre, self.lang, self.has_photos = contestants, centre, lang, has_photos
        for c in contestants:
            self.fields[f"c_{c.id}"] = forms.IntegerField(min_value=0, initial=0, label=c.name)
        self.checked_photos = []

    def clean(self):
        data = super().clean()
        needed = ["voted", "blank", "invalid"] + [f"c_{c.id}" for c in self.contestants]
        if any(k not in data for k in needed):
            return data
        voted = data["voted"]
        total = data["blank"] + data["invalid"] + sum(data[f"c_{c.id}"] for c in self.contestants)
        if total != voted:
            self.add_error("voted", tr("err_sum", self.lang))
        if self.centre.registered_voters and voted > self.centre.registered_voters:
            self.add_error("voted", tr("err_registered", self.lang) % {"n": self.centre.registered_voters})

        photos = data.get("photos") or []
        if len(photos) > settings.MAX_EVIDENCE_FILES:
            photos = photos[: settings.MAX_EVIDENCE_FILES]
        if not photos and not self.has_photos:
            self.add_error("photos", tr("err_photo", self.lang))
        for p in photos:
            try:
                sha, size = validate_image(p)
            except ValueError:
                self.add_error("photos", tr("err_photo_bad", self.lang) % {"f": p.name})
                continue
            self.checked_photos.append((p, sha, size))
        return data
