"""Helper ba utilizadór -> perfíl/partidu (padraun hanesan `c_user_fun` iha projetu funsionario).

Kontratu: fila objetu ka "" (string mamuk) se la iha, nune'e template/view bele uza `if obj:`.
"""
from .models import Party, Profile


def c_user_fun(user):
    """Perfíl (fiskál / monitór / verifikadór) ne'ebé liga ba `user`."""
    if user is None or not getattr(user, "is_authenticated", False) or not user.pk:
        return ""
    objects = (Profile.objects.filter(user=user).select_related("party", "user")
               .prefetch_related("centres").first())
    obj = ""
    if objects:
        obj = objects
    return obj


def c_user_party(user):
    """Partidu ne'ebé utilizadór ne'e reprezenta (fiskál ka nain-partidu), ka ""."""
    fun = c_user_fun(user)
    return fun.party if fun and fun.party_id else ""


def c_party_users(party, role=None):
    """Utilizadór hotu husi partidu ida (opsionál: filtra papél)."""
    qs = Profile.objects.filter(party=party).select_related("user")
    if role:
        qs = qs.filter(role=role)
    return [p.user for p in qs]


def c_party_centres(party):
    """Sentru hotu ne'ebé fiskál husi partidu ne'e bele hatama dadus."""
    from .models import Centre
    return Centre.objects.filter(fiskais__party=party).distinct()
