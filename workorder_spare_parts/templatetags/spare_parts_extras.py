# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/workorder_spare_parts/templatetags/spare_parts_extras.py
"""
Template filters for the spare parts / warehouse module.

level_label: traduce los codigos de nivel de stock incontable
(FULL/MEDIUM/LOW/EMPTY, anexo H10 seccion 3.7) a su etiqueta en
castellano para mostrar al usuario. Los codigos en ingles se
mantienen sin cambios como valor almacenado en
SparePartEntry.stock_level y como valor de los <option> -- confirmado
por Miguel Angel (2026-07-07): solo la etiqueta visible debe estar en
castellano, no el valor interno, para no romper la validacion ya
existente en StockAssignmentService.LEVEL_CHOICES ni requerir
migracion de datos.

---

Filtros de plantilla para el modulo de repuestos / almacen.

level_label: translates the uncountable stock level codes
(FULL/MEDIUM/LOW/EMPTY, annex H10 section 3.7) into their Spanish
label for display. The English codes remain unchanged as the stored
value in SparePartEntry.stock_level and as the <option> value --
confirmed by Miguel Angel (2026-07-07): only the visible label must
be in Spanish, not the internal value, to avoid breaking the existing
validation in StockAssignmentService.LEVEL_CHOICES or requiring a
data migration.
"""
from django import template

register = template.Library()

_LEVEL_LABELS_ES = {
    'FULL': 'Lleno',
    'MEDIUM': 'Medio',
    'LOW': 'Bajo',
    'EMPTY': 'Vacío',
}


@register.filter
def level_label(value):
    """
    Devuelve la etiqueta en castellano del codigo de nivel, o el
    valor tal cual si no es uno de los cuatro codigos conocidos
    (incluye cadena vacia -- el llamante decide el fallback con
    |default:"—" antes o despues de este filtro).
    """
    return _LEVEL_LABELS_ES.get(value, value)
