# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/filename_date_service.py
"""
H30 (S50). Heurística de fecha por NOMBRE de archivo (Fase B0),
extraída de `run_fase_b0_filename_dates.py` (S48) para que el mismo
código sirva tanto al barrido histórico por lote como al pipeline de
clasificación en tiempo real (`apply_quarantine_classification`,
S50) -- un único punto de verdad, nunca dos copias que puedan
divergir.

Criterios confirmados por Miguel Ángel con datos reales (S48), nunca
generalizados sin evidencia -- ver docstring original en
`run_fase_b0_filename_dates.py` para el detalle completo de cada
patrón.
"""
import re
from datetime import date

FIELD_BY_CODE = {
    "ITV": "expiry",
    "OCA": "expiry",
    "CARNET_CONDUCIR": "expiry",
    "PERMISO_CIRCULACION": "issue",
    "FORMACION": "issue",
}

_DATE_RE = re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})")
_RANGE_RE = re.compile(
    r"(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})\s*[aA]\s*"
    r"(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})",
)
_TRIMESTRE_RE = re.compile(
    r"([1-4])\s*[ºo]?\s*TR\.?\s*(\d{4})", re.IGNORECASE,
)

_QUARTER_FIRST_MONTH = {1: 1, 2: 4, 3: 7, 4: 10}


def _parse_date(day_s, month_s, year_s):
    try:
        day, month = int(day_s), int(month_s)
        year = int(year_s)
    except ValueError:
        return None
    if year < 100:
        year += 2000
    if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_date(name):
    """
    Devuelve la ÚLTIMA fecha valida encontrada en el nombre -- por
    convencion real observada en el corpus, la fecha va al final del
    nombre, justo antes de la extension; cuando hay mas de un numero
    con forma de fecha, el ultimo es el fiable (el primero suele ser
    parte de un codigo de maquina/matricula).
    """
    matches = list(_DATE_RE.finditer(name))
    for match in reversed(matches):
        parsed = _parse_date(*match.groups())
        if parsed:
            return parsed
    return None


def _parse_single_date_str(date_str):
    parts = re.split(r"[-./]", date_str)
    if len(parts) != 3:
        return None
    return _parse_date(*parts)


def _extract_seguro(name):
    """
    Devuelve (field, date) segun los tres subpatrones confirmados por
    Miguel Angel en S48. None si no hay ningun patron reconocible --
    nunca se adivina, se deja para Fase B1 (OCR).
    """
    range_match = _RANGE_RE.search(name)
    if range_match:
        end_date = _parse_single_date_str(range_match.group(2))
        if end_date:
            return "expiry", end_date

    trimestre_match = _TRIMESTRE_RE.search(name)
    if trimestre_match:
        quarter = int(trimestre_match.group(1))
        year = int(trimestre_match.group(2))
        month = _QUARTER_FIRST_MONTH[quarter]
        return "issue", date(year, month, 1)

    simple_date = _extract_date(name)
    if simple_date:
        return "issue", simple_date

    return None


def extract_date_by_filename(code, name):
    """
    Punto de entrada único del servicio. Devuelve (field, date) donde
    field es "expiry" o "issue", o None si el nombre no trae ningun
    patron reconocible para este `code` -- nunca se adivina, es la
    señal de pasar al siguiente paso (OCR).
    """
    if code == "SEGURO":
        return _extract_seguro(name)
    if code not in FIELD_BY_CODE:
        return None
    found = _extract_date(name)
    if not found:
        return None
    return FIELD_BY_CODE[code], found
