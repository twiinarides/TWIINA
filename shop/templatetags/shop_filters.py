from django import template
from decimal import Decimal

register = template.Library()


@register.filter
def currency(value):
    if value is None:
        return "UGX 0.00"
    try:
        return f"UGX {float(value):,.0f}"
    except (ValueError, TypeError):
        return "UGX 0"


@register.filter
def percentage(value):
    try:
        return f"{float(value):.1f}%"
    except (ValueError, TypeError):
        return "0.0%"


@register.filter
def multiply(value, arg):
    try:
        return Decimal(str(value)) * Decimal(str(arg))
    except Exception:
        return 0


@register.filter
def subtract(value, arg):
    try:
        return Decimal(str(value)) - Decimal(str(arg))
    except Exception:
        return 0


@register.filter
def abs_value(value):
    try:
        return abs(value)
    except Exception:
        return value


@register.filter
def intcomma(value):
    """Format a number with commas — replaces Django humanize intcomma."""
    try:
        return f"{int(float(str(value))):,}"
    except (ValueError, TypeError):
        return value


@register.filter
def floatformat_intcomma(value, decimal_places=0):
    """Format a number to fixed decimals then add commas."""
    try:
        v = round(float(str(value)), int(decimal_places))
        if int(decimal_places) == 0:
            return f"{int(v):,}"
        return f"{v:,.{int(decimal_places)}f}"
    except (ValueError, TypeError):
        return value
