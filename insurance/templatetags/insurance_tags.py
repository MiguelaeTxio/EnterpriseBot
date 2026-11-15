# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/insurance/templatetags/insurance_tags.py
"""
Template filters of the insurance report.
---
Filtros de plantilla del informe de seguros.
"""
from django import template

from insurance.exports import eur as _eur

register = template.Library()


@register.filter
def eur(value, decimals=2):
    """
    "1.234,56 €".
    ---
    Importe con formato español ("" si no hay).
    """
    if value is None or value == "":
        return ""
    return _eur(float(value), int(decimals))


@register.filter
def days_label(days):
    """
    "en 12 d", "hoy", "hace 3 d".
    ---
    Días que faltan (o que han pasado) hasta el vencimiento.
    """
    if days is None:
        return ""
    if days < 0:
        return "hace %d d" % -days
    if days == 0:
        return "hoy"
    return "en %d d" % days
