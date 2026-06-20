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
# Fallback dict for legacy string codes (BudgetLine.concept_code snapshots
# and any context where concept is passed as a raw string).
# Dict de respaldo para códigos string legacy (snapshots BudgetLine.concept_code
# y cualquier contexto donde concept se pase como string crudo).
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
    "TOLL_COST":        "Peajes de ruta",
}

# ---------------------------------------------------------------------------
# Unit code -> human-readable label in Spanish
# Codigo de unidad -> etiqueta legible en castellano
# ---------------------------------------------------------------------------
UNIT_LABELS = {
    "FIXED":    "Fijo",
    "PER_KM":   "Por km",
    "PER_HOUR": "Por hora",
    "PER_DAY":  "Por dia",
    "PERCENT":  "Porcentaje",
}


@register.filter(name="concept_label")
def concept_label(value):
    """
    Return the human-readable Spanish label for a TariffLine concept.
    Accepts either a TariffConcept instance (FK) or a raw string code
    (used by BudgetLine.concept_code legacy snapshots).
    Falls back to the raw value if no mapping exists.
    ---
    Devuelve la etiqueta legible en castellano para un concepto de TariffLine.
    Acepta un objeto TariffConcept (FK) o un código string crudo
    (usado por snapshots legacy BudgetLine.concept_code).
    Devuelve el valor crudo si no existe mapeo.
    """
    # TariffConcept instance — read label directly.
    # Instancia TariffConcept — leer label directamente.
    if hasattr(value, "label"):
        return value.label
    # Legacy string code — look up in fallback dict.
    # Código string legacy — buscar en dict de respaldo.
    return CONCEPT_LABELS.get(str(value), str(value))


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


# ---------------------------------------------------------------------------
# Weekday names for calendar display
# Nombres de días de la semana para visualización de calendario
# ---------------------------------------------------------------------------

_WEEKDAY_NAMES = [
    "Lunes", "Martes", "Miércoles", "Jueves",
    "Viernes", "Sábado", "Domingo",
]


@register.filter(name="weekday_name")
def weekday_name(iso_date_str):
    """
    Return the Spanish weekday name for an ISO date string (YYYY-MM-DD).
    Returns the original string if parsing fails.
    ---
    Devuelve el nombre del día de la semana en castellano para un string
    de fecha ISO (YYYY-MM-DD). Devuelve el string original si el parsing
    falla.
    """
    import datetime
    try:
        d = datetime.date.fromisoformat(str(iso_date_str))
        return _WEEKDAY_NAMES[d.weekday()]
    except (ValueError, TypeError):
        return str(iso_date_str)
