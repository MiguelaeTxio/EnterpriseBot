# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/templatetags/budgets_extras.py
"""
Custom template filters for the budgets application.
Provides human-readable labels for TariffLine concept and unit codes.
---
Filtros de template personalizados para la aplicacion de presupuestos.
Proporciona etiquetas legibles para los codigos de concepto y unidad de TariffLine.
"""

from django import template

register = template.Library()

# ---------------------------------------------------------------------------
# Concept code -> human-readable label in Spanish
# Codigo de concepto -> etiqueta legible en castellano
# ---------------------------------------------------------------------------
CONCEPT_LABELS = {
    "DEPARTURE":        "Salida / Enganche",
    "SERVICE_LOCAL":    "Servicio local / Urbano",
    "KM_NORMAL":        "Kilometros (normal)",
    "KM_LONG":          "Kilometros (largo recorrido)",
    "UNLOCK":           "Desbloqueo / Eslingas",
    "RESCUE_HOUR":      "Hora de rescate",
    "WAIT_HOUR":        "Hora de espera",
    "WORKER_HOUR":      "Hora de mano de obra",
    "ASSISTANT_HOUR":   "Hora de ayudante",
    "CUSTODY_DAY":      "Custodia por dia",
    "NYF_PERCENT":      "Recargo nocturno/festivo (%)",
    "LOADED_PERCENT":   "Recargo vehiculo cargado (%)",
    "MANAGEMENT_FEE":   "Gastos de gestion (%)",
    "IVA":              "IVA",
}

# ---------------------------------------------------------------------------
# Unit code -> human-readable label in Spanish
# Codigo de unidad -> etiqueta legible en castellano
# ---------------------------------------------------------------------------
UNIT_LABELS = {
    "FIXED":    "Fijo",
    "PER_KM":   "Por km",
    "PERCENT":  "Porcentaje",
}


@register.filter(name="concept_label")
def concept_label(value):
    """
    Return the human-readable Spanish label for a TariffLine concept code.
    Falls back to the raw value if no mapping exists.
    ---
    Devuelve la etiqueta legible en castellano para un codigo de concepto
    de TariffLine. Devuelve el valor crudo si no existe mapeo.
    """
    return CONCEPT_LABELS.get(value, value)


@register.filter(name="unit_label")
def unit_label(value):
    """
    Return the human-readable Spanish label for a TariffLine unit code.
    Falls back to the raw value if no mapping exists.
    ---
    Devuelve la etiqueta legible en castellano para un codigo de unidad
    de TariffLine. Devuelve el valor crudo si no existe mapeo.
    """
    return UNIT_LABELS.get(value, value)
