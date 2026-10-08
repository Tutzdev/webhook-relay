from django import template

register = template.Library()


@register.filter
def percentage(part: int, total: int) -> str:
    if not total:
        return "—"
    return f"{100 * part / total:.0f}%"
