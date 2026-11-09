from django import template

from ..i18n import tr

register = template.Library()


@register.simple_tag(takes_context=True)
def t(context, key):
    return tr(key, context.get("lang", "tet"))


@register.filter
def fmt(value):
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return value


@register.filter
def status_class(value):
    return {"verified": "ok", "consensus": "ok", "pending": "warn", "provisional": "warn",
            "rejected": "bad", "conflict": "bad"}.get(value, "muted")
