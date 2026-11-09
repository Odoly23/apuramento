from .auth_utils import c_user_fun
from .i18n import LANGS, all_for
from .models import Election


def globals(request):
    lang = getattr(request, "lang", "tet")
    ctx = {"lang": lang, "langs": LANGS, "i18n_all": all_for(lang)}
    user = getattr(request, "user", None)
    fun = c_user_fun(user) if user is not None else ""
    if fun:
        ctx["profile"] = ctx["fun"] = fun
        ctx["group"] = user.groups.values_list("name", flat=True).first() or ""
        ctx["elections"] = Election.objects.all()
        ctx["election"] = getattr(request, "election", None)
    return ctx
