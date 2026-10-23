# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/gasoges_rules.py
"""
H30 (S135). Pure rules of the GasoGes link (no Django): normalisation,
name matching, unit deduction and reading check.

---

H30 (S135). Reglas puras del enlace con GasoGes, sin Django, para
poder probarlas solas:
- `normalize`: mayúsculas, sin espacios ni guiones.
- `name_words` / `name_matches`: cruce del nombre de un usuario de
  GasoGes (cortado a 30 caracteres) con el nombre de una ficha.
- `deduce_unit`: si lo que el chófer teclea en KM son km u horas.
- `check_reading`: si un KM tecleado vale como lectura o es dudoso.

Las reglas de anomalía de este módulo son las primeras y provisionales:
Miguel Ángel (S135) definirá las suyas con la media de litros (los
litros los da la máquina y son exactos) y la pregunta por WhatsApp.
"""
import unicodedata
from statistics import median

GASOGES_NAME_LENGTH = 30

# Un horómetro no puede subir más de 24 horas al día. Por encima de
# este ritmo sostenido, lo tecleado son km.
# ---
# An hour meter cannot grow more than 24 hours per day.
KM_RATE_THRESHOLD = 30.0
MIN_SUPPLIES_FOR_RATE = 4
MIN_DAYS_FOR_RATE = 7

# Subida máxima creíble por día entre dos lecturas.
# ---
# Highest credible increase per day between two readings.
MAX_KM_PER_DAY = 1500
MAX_HOURS_PER_DAY = 24

UNIT_UNKNOWN = "UNKNOWN"
UNIT_KM = "KM"
UNIT_HOURS = "HOURS"


def normalize(value):
    """
    Uppercase without spaces or hyphens.

    ---

    Mayúsculas, sin espacios ni guiones.
    """
    if value is None:
        return ""
    return str(value).replace(" ", "").replace("-", "").strip().upper()


def name_words(value):
    """
    Words of a person name: ASCII uppercase, no punctuation, 2+ letters.

    ---

    Palabras de un nombre: sin tildes, mayúsculas, sin signos, de dos
    letras o más (la Ñ pasa a N, igual en los dos lados).
    """
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode()
    for sign in ",.()":
        text = text.replace(sign, " ")
    return [word for word in text.upper().split() if len(word) > 1]


def name_matches(gasoges_name, person_name):
    """
    True if every word of the GasoGes name is in the person name.

    Each person word is used once ("GOMEZ GOMEZ" needs two GOMEZ).
    When GasoGes cut the name at 30 characters, its last word may be
    the start of a person word ("...SALVADOR DAVI" -> DAVID).

    ---

    True si todas las palabras del nombre de GasoGes están en el de la
    ficha, cada palabra de la ficha usada una vez. Si GasoGes cortó el
    nombre a 30 caracteres, su última palabra puede ser el principio de
    una palabra de la ficha.
    """
    words = name_words(gasoges_name)
    available = name_words(person_name)
    if not words:
        return False
    truncated = len(str(gasoges_name or "").rstrip()) >= (
        GASOGES_NAME_LENGTH - 1)
    for position, word in enumerate(words):
        if word in available:
            available.remove(word)
            continue
        is_last = position == len(words) - 1
        prefix = [w for w in available if w.startswith(word)]
        if truncated and is_last and prefix:
            available.remove(prefix[0])
            continue
        return False
    return True


def deduce_unit(has_odometer, has_engine_hours, points):
    """
    Deduce what the driver types in KM: kilometres or hours.

    `points` is a list of (datetime, value) of the vehicle's supplies.
    Only the odometer flag -> KM; only the hour meter -> HOURS; both or
    none -> by the sustained rate of the values, KM only above what an
    hour meter can do. Returns (unit, reason).

    ---

    Deduce qué teclea el chófer en KM. Solo odómetro -> km; solo
    horómetro -> horas. Con los dos (o ninguno), por el ritmo sostenido
    de los valores: por encima de lo que puede subir un horómetro, km;
    si no, sin saber (se pregunta al chófer). Robusto al ruido (S135,
    A44/A33): compara la mediana del primer tercio con la del último.
    Devuelve (unidad, motivo).
    """
    if has_odometer and not has_engine_hours:
        return UNIT_KM, "solo tiene odómetro"
    if has_engine_hours and not has_odometer:
        return UNIT_HOURS, "solo tiene horómetro"
    clean = sorted((when, value) for when, value in points if value)
    if len(clean) < MIN_SUPPLIES_FOR_RATE:
        return UNIT_UNKNOWN, "pocos suministros para deducirla"
    days = (clean[-1][0] - clean[0][0]).total_seconds() / 86400
    if days < MIN_DAYS_FOR_RATE:
        return UNIT_UNKNOWN, "suministros de pocos días"
    third = max(1, len(clean) // 3)
    first = median(value for _when, value in clean[:third])
    last = median(value for _when, value in clean[-third:])
    first_day = clean[third // 2][0]
    last_day = clean[-1 - third // 2][0]
    span = max((last_day - first_day).total_seconds() / 86400, 1)
    rate = (last - first) / span
    if rate > KM_RATE_THRESHOLD:
        return UNIT_KM, "sube %.0f al día (más que un horómetro)" % rate
    return UNIT_UNKNOWN, "sube %.0f al día (puede ser km u horas)" % rate


def check_reading(value, unit, previous_value, previous_when, when):
    """
    Decide if a typed value is a credible reading. Returns (ok, reason).

    ---

    Decide si un valor tecleado vale como lectura. Dudoso si está vacío
    o a 0, si es menor que la lectura anterior, o si sube más de lo
    creíble por día (1.500 km o 24 horas). Sin lectura anterior se
    acepta. Devuelve (vale, motivo).
    """
    if not value:
        return False, "KM vacío o a 0"
    if previous_value is None:
        return True, "primera lectura"
    if value < previous_value:
        return False, "menor que la lectura anterior (%s)" % previous_value
    days = max((when - previous_when).total_seconds() / 86400, 1)
    limit = MAX_KM_PER_DAY if unit == UNIT_KM else MAX_HOURS_PER_DAY
    if (value - previous_value) / days > limit:
        return False, "sube %s en %.0f días desde %s" % (
            value - previous_value, days, previous_value)
    return True, "coherente con la lectura anterior"
