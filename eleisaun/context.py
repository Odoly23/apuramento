from .i18n import LANGS, all_for, tr
from .models import Election


def globals(request):
    lang = getattr(request, "lang", "tet")
    ctx = {"lang": lang, "langs": LANGS, "i18n_all": all_for(lang)}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and hasattr(user, "profile"):
        ctx["profile"] = user.profile
        ctx["elections"] = Election.objects.all()
        ctx["election"] = getattr(request, "election", None)
    return ctx
