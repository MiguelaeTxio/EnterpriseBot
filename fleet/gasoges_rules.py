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
- `best_series` / `series_reason`: qué KM tecleados forman la serie
  real del vehículo y, los que no, por qué son dudosos.

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

# Un número tan pequeño no es una lectura real (S135: Z01 con "1").
# ---
# Such a small number is never a real reading.
MIN_CREDIBLE_VALUE = 10

# S137: ningún horómetro llega a 50.000 horas; un número así en un
# vehículo de horas son kilómetros tecleados por costumbre. S163
# (23/11): tampoco cuentan para la serie de un vehículo de horas (B27).
# ---
# No hour meter reaches this: in an hours vehicle it is kilometres.
MAX_CREDIBLE_HOURS = 50000

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


# Miguel Ángel (S135): "Todas las Z son plataforma elevadora. Todas van
# con horas."
# ---
# Every Z cost centre is an aerial platform and goes by hours.
HOURS_CODE_PREFIXES = ("Z",)


# Regla del taller (S137, Miguel Ángel): turismos y furgonetas (X) y P
# van por km; grúas móviles (A, y la familia MÓVILES), brazos (B),
# carretillas (T) y plataformas elevadoras (Z), por horas. Manda sobre lo
# deducido y lo puesto a mano: un repostaje que no encaja con ella sale
# dudoso y se pregunta al repostador. La familia manda sobre el código
# (ADOLFO es un turismo aunque empiece por A; PAOLA, una plataforma
# aunque empiece por P).
# S137, Miguel Ángel: en la familia ASISTENCIA, las A (grúas de
# asistencia) van por horas; el resto (B, P, X...: camiones de rescate o
# plataformas de transporte, sin pluma ni hidráulico que cuente horas),
# por km.
# S142 (sesión invasora), Miguel Ángel, corrige lo de las A: "apuntan
# km. En asistencia se dijo que bueno, que vale." Los chóferes de las
# grúas de asistencia teclean en el surtidor los km del camión (A50 de
# 613.533 a 617.204, A39 de 53.048 a 66.973 en diez meses): toda la
# familia ASISTENCIA va por km.
# ---
# Workshop rule: which unit each kind of vehicle goes by.
KM_FAMILIES = ("TURISMOS",)
ASSISTANCE_FAMILY = "ASISTENCIA"
HOURS_FAMILIES = ("PLATAFORMAS", "CARRETILLAS", "MÓVILES")
HOURS_CONVENTION_PREFIXES = ("A", "B", "T", "Z")
KM_CODE_PREFIXES = ("P", "X")
# S154 (sesión invasora), Miguel Ángel: B38 y B41 son plataformas de
# transporte (familia PLATAFORMAS) y "van por kilómetros"; en GasoGes
# sus repostajes llevan los km del camión (B38 de 718.700 a 760.810,
# B41 hasta 762.515). Mandan sobre la familia y el prefijo B.
# ---
# Cost centres that go by km whatever their family or prefix.
KM_CODES = ("B38", "B41")


def convention_unit(code, family):
    """
    Unit set by the workshop rule, or None if the rule says nothing.

    ---

    Unidad que fija la regla del taller, o None si la regla no dice nada
    de ese centro de gasto (generadores, contenedores, la Kärcher...).
    """
    code = str(code or "").upper()
    family = str(family or "").upper()
    if code in KM_CODES:
        return UNIT_KM
    if family == ASSISTANCE_FAMILY:
        return UNIT_KM
    if family in KM_FAMILIES:
        return UNIT_KM
    if family in HOURS_FAMILIES:
        return UNIT_HOURS
    if code.startswith(HOURS_CONVENTION_PREFIXES):
        return UNIT_HOURS
    if code.startswith(KM_CODE_PREFIXES):
        return UNIT_KM
    return None


def deduce_unit(has_odometer, has_engine_hours, points, code=""):
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
    if str(code or "").upper().startswith(HOURS_CODE_PREFIXES):
        return UNIT_HOURS, "plataforma elevadora (todas las Z van por horas)"
    if has_odometer and not has_engine_hours:
        return UNIT_KM, "solo tiene odómetro"
    if has_engine_hours and not has_odometer:
        return UNIT_HOURS, "solo tiene horómetro"
    clean = sorted((when, value) for when, value in points
                   if value and value >= MIN_CREDIBLE_VALUE)
    if len(clean) < MIN_SUPPLIES_FOR_RATE:
        return UNIT_UNKNOWN, "pocos suministros para deducirla"
    days = (clean[-1][0] - clean[0][0]).total_seconds() / 86400
    if days < MIN_DAYS_FOR_RATE:
        return UNIT_UNKNOWN, "suministros de pocos días"
    # Mediana de las pendientes entre todos los pares separados al
    # menos un día (Theil-Sen): un valor absurdo suelto ("33333" en
    # A44, S135) no la mueve.
    # ---
    # Median of pairwise slopes (Theil-Sen), robust to outliers.
    slopes = []
    for i, (when_a, value_a) in enumerate(clean):
        for when_b, value_b in clean[i + 1:]:
            span = (when_b - when_a).total_seconds() / 86400
            if span >= 1:
                slopes.append((value_b - value_a) / span)
    if not slopes:
        return UNIT_UNKNOWN, "suministros de pocos días"
    rate = median(slopes)
    if rate > KM_RATE_THRESHOLD:
        return UNIT_KM, "sube %.0f al día (más que un horómetro)" % rate
    return UNIT_UNKNOWN, "sube %.0f al día (puede ser km u horas)" % rate


def _fits(earlier, later, limit):
    """
    True if `later` can follow `earlier` in a real meter series.

    ---

    True si `later` puede ir detrás de `earlier` en un contador real:
    no baja y no sube más de lo creíble por día (como mínimo un día).
    """
    (when_a, value_a), (when_b, value_b) = earlier, later
    if value_b < value_a:
        return False
    days = max((when_b - when_a).total_seconds() / 86400, 1)
    return (value_b - value_a) / days <= limit


def best_series(points, unit):
    """
    Indexes of the points forming the vehicle's real meter series.

    `points` is a time-ordered list of (datetime, value). The series is
    the longest chain that never goes down and never grows faster than
    a vehicle can (1.500 km or 24 hours per day). Ties go to the chain
    ending latest.

    ---

    Índices de los puntos que forman la serie real del contador del
    vehículo (S137). Antes cada KM se comparaba con la última lectura
    aceptada, y un solo dato malo aceptado (7245 GBM: 324.624 el 19/05,
    o 250.000 redondo el 10/03) hacía dudosas todas las lecturas buenas
    que venían detrás. Ahora manda la cadena más larga de valores que
    nunca bajan ni suben más de lo creíble por día (1.500 km o 24
    horas): la mayoría de repostajes bien tecleados deja fuera al dato
    suelto, esté donde esté. A igualdad, gana la cadena que acaba más
    tarde.
    """
    limit = MAX_KM_PER_DAY if unit == UNIT_KM else MAX_HOURS_PER_DAY
    # S163 (23/11, B27): en un vehículo de horas, los kilómetros que se
    # tecleaban antes (247.000...) no forman serie. Hacían la cadena más
    # larga y dejaban dudosas las primeras horas de verdad (25.734 y
    # 25.744), y se preguntaba al chófer aunque las había puesto bien.
    usable = [i for i, (_when, value) in enumerate(points)
              if value and value >= MIN_CREDIBLE_VALUE
              and (unit == UNIT_KM or value < MAX_CREDIBLE_HOURS)]
    score, back = {}, {}
    for pos, i in enumerate(usable):
        best, best_from = 0, None
        for j in usable[:pos]:
            if score[j] > best and _fits(points[j], points[i], limit):
                best, best_from = score[j], j
        score[i], back[i] = best + 1, best_from
    if not score:
        return set()
    end = max(score, key=lambda i: (score[i], i))
    chain = set()
    while end is not None:
        chain.add(end)
        end = back[end]
    return chain


def series_reason(points, index, chain, unit):
    """
    Why a point outside the series is doubtful (Spanish, one line).

    ---

    Por qué un KM que no entra en la serie es dudoso, comparado con las
    lecturas de la serie justo antes y justo después.
    """
    when, value = points[index]
    if not value:
        return "KM vacío o a 0"
    if value < MIN_CREDIBLE_VALUE:
        return "número demasiado pequeño (%s)" % value
    if unit != UNIT_KM and value >= MAX_CREDIBLE_HOURS:
        return "más de lo que marca un horómetro: parecen kilómetros"
    limit = MAX_KM_PER_DAY if unit == UNIT_KM else MAX_HOURS_PER_DAY
    before = [i for i in chain if i < index]
    after = [i for i in chain if i > index]
    prev_value = points[max(before)][1] if before else None
    next_value = points[min(after)][1] if after else None
    if prev_value is not None and value < prev_value:
        return "menor que la lectura anterior (%s)" % prev_value
    if next_value is not None and value > next_value:
        return "mayor que la lectura siguiente (%s)" % next_value
    if before and not _fits(points[max(before)], points[index], limit):
        prev_when = points[max(before)][0]
        days = max((when - prev_when).total_seconds() / 86400, 1)
        return "sube %s en %.0f días desde %s" % (
            value - prev_value, days, prev_value)
    return "no encaja con el resto de lecturas del vehículo"
