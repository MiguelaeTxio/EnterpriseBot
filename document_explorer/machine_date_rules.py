# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/machine_date_rules.py
"""
H30 (S119), punto 1 of the roadmap -- date rules by document type over
the cached OCR text of machine documents. Pure Python (re only): no
Django, no API. Written from real text samples (db_query.yml, S119).
---
H30 (S119), punto 1 de la hoja de ruta -- reglas de fecha por tipo
sobre el texto ya guardado (`ocr_text`) de los documentos de máquinas.
Python puro (solo `re`): sin Django y sin ninguna API. Escritas con
frases reales sacadas con `db_query.yml` en S119 (recibos MAPFRE,
Allianz, Generali, Helvetia, CASER, DAS; ITV; IVTM de Cajamar; OCA;
garantías; autorizaciones de la DGT; tacógrafo).

Orden de las reglas, de más fiable a menos:
1. Periodo de cobertura/vigencia ("VIGENCIA:DE X A Y", "DESDE X HASTA
   Y", "X AL Y" pegado, "DEL X AL Y", "GAR.S/P X Y", "VALIDEZ DE
   RECIBO X Y", "DESDE: AAAAMMDD HASTA: AAAAMMDD"): da emisión (X) y
   caducidad (Y). Solo se acepta si Y va después de X y el periodo
   dura entre 25 y 800 días -- así no se confunde con un "periodo de
   pago" de 10 días ni con dos fechas sueltas sin relación.
2. Caducidad con etiqueta ("VALIDEZ", "VALEDERA HASTA", "PRÓXIMA
   ITV/INSPECCIÓN/REVISIÓN", "VENCIMIENTO", "VÁLIDO HASTA"); en una
   tarjeta ITV con varias inspecciones, la más reciente.
3. Emisión con etiqueta ("FECHA DE INSPECCIÓN", "FECHA VALOR",
   "FECHA OPERACIÓN", "F. EXP.", "FECHA INICIO", "EL DÍA X", "FECHA:
   X", número de solicitud de la DGT AAAAMMDD/...).
4. Mes y año en el nombre del archivo ("ITV MAY-2015"): criterio S48
   de Miguel Ángel, en ITV/OCA es caducidad (último día del mes); en
   el resto, emisión (día 1).
5. Fecha larga ("28 de enero de 2022") y fecha escrita en palabras
   ("a nueve de febrero de dos mil veintiuno"): emisión.

Nunca devuelve una emisión futura ni fechas anteriores a 1980.
"""
import calendar
import re
import unicodedata
from datetime import date

from document_explorer.filename_date_service import _parse_date

MIN_DATE = date(1980, 1, 1)
MAX_EXPIRY = date(2045, 12, 31)
MIN_PERIOD_DAYS = 25
MAX_PERIOD_DAYS = 800
# IVTM: el impuesto es anual; un "periodo" más corto es el plazo de
# pago voluntario, nunca una vigencia (dry-run EnterpriseBot_001, S119).
MIN_PERIOD_DAYS_BY_CODE = {"IVTM": 300}
# Contexto previo que delata un plazo de pago o de devolución, no una
# cobertura: "Período de pago del ... al ...", "periodo voluntario".
_PAYMENT_CONTEXT = ("PAGO", "VOLUNTARI", "COBRO", "DEVOLUCION")
# Contexto previo de una fecha registral del propio banco: pie de
# Cajamar "Inscripción 1ª de fecha 31/10/2012" (id=4794, id=13337).
_REGISTRY_CONTEXT = ("INSCRIP", "REG. MERC", "REGISTRO MERCANTIL")

# Tipos cuya fecha en el nombre es caducidad (criterio S48).
EXPIRY_BY_NAME_CODES = {"ITV", "OCA"}

_D = r"(\d{1,2})[-./](\d{1,2})[-./](\d{4}|\d{2})(?!\d)"
_DATE_TOKEN_RE = re.compile(r"(?<!\d)" + _D)
_COMPACT_RE = r"((?:19|20)\d{2})(\d{2})(\d{2})"

_MONTHS = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5,
    "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9,
    "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
_MONTH_ABBR = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "SET": 9, "OCT": 10, "NOV": 11,
    "DIC": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_NUMBER_WORDS = {
    "UNO": 1, "UN": 1, "PRIMERO": 1, "DOS": 2, "TRES": 3, "CUATRO": 4,
    "CINCO": 5, "SEIS": 6, "SIETE": 7, "OCHO": 8, "NUEVE": 9,
    "DIEZ": 10, "ONCE": 11, "DOCE": 12, "TRECE": 13, "CATORCE": 14,
    "QUINCE": 15, "DIECISEIS": 16, "DIECISIETE": 17, "DIECIOCHO": 18,
    "DIECINUEVE": 19, "VEINTE": 20, "VEINTIUNO": 21, "VEINTIUN": 21,
    "VEINTIDOS": 22, "VEINTITRES": 23, "VEINTICUATRO": 24,
    "VEINTICINCO": 25, "VEINTISEIS": 26, "VEINTISIETE": 27,
    "VEINTIOCHO": 28, "VEINTINUEVE": 29, "TREINTA": 30,
    "TREINTA Y UNO": 31,
}
_WORD_ALT = "|".join(
    re.escape(w) for w in sorted(_NUMBER_WORDS, key=len, reverse=True)
)

# --- 1. Periodos -----------------------------------------------------
_PERIOD_PATTERNS = [
    # "VIGENCIA:DE 15-06-10 A 15-09-10" y "VIGENCIA: DE 30-01-13 ...
    # RECIBO: 472201086 A 15-06-13" (texto partido por el OCR).
    re.compile(
        r"VIGENCIA\s*:?\s*DE\s*" + _D + r".{0,90}?\bA\s*" + _D
    ),
    # Allianz: la fecha va pegada al importe total y a la otra fecha
    # ("TOT:1.109,4025-10-2023AL01-10-2024", "194,6801.01.2026AL...");
    # sin lookbehind y solo en formato estricto DD-MM-AAAA.
    re.compile(
        r"(\d{2})[-.](\d{2})[-.](\d{4})AL(\d{2})[-.](\d{2})[-.](\d{4})"
    ),
    # "desde las 00:00 horas del dia 01-01-2025 hasta las 24 horas del
    # 31-12-2025", "01/01/2023 A LAS 00:00 HORAS HASTA 01/01/2024",
    # "25-10-2023AL01-10-2024", "PERIODO: 15-12-2013 AL 01-01-2015",
    # "DE 31/12/2025 A 30/12/2026", "Efecto del 05/08/2013 al ...".
    re.compile(
        r"(?<!\d)" + _D + r"\s*(?:A LAS [\d:.]+ HORAS\s*)?"
        r"(?:AL|A|HASTA)"
        r"(?:\s*LAS \d{1,2}(?:[:.]\d{2})? HORAS)?(?:\s*DEL?(?: DIA)?)?"
        r"\s*" + _D
    ),
    # Helvetia: "Gar.s/p 06/02/2026 30/12/2026".
    re.compile(r"GAR\.?\s*S/P\s*" + _D + r"\s+" + _D),
    # Correduría: "VALIDEZ DE RECIBO TOTAL EUROS 15/12/2011 15/12/2012".
    re.compile(
        r"VALIDEZ DE(?:L)? RECIBO\D{0,40}" + _D + r"\s+" + _D
    ),
]
# CASER/Meditres: "DESDE: 20140820 HASTA: 20150820".
_COMPACT_PERIOD_RE = re.compile(
    r"DESDE\s*:?\s*" + _COMPACT_RE + r"\s*HASTA\s*:?\s*" + _COMPACT_RE
)

# --- 2. Caducidad con etiqueta ---------------------------------------
_EXPIRY_LABEL_RE = re.compile(
    r"(?:VALIDEZ|VALEDERA HASTA(?:/POR)?|PROXIMA (?:ITV|INSPECCION|"
    r"REVISION)|VENCIMIENTO|VALID[OA] HASTA(?: EL)?|FECHA DE CADUCIDAD|"
    r"CADUCA(?: EL)?)\s*:?\s*" + _D
)

# --- 3. Emisión con etiqueta ------------------------------------------
# Tarjeta ITV con varias inspecciones: se toma la más reciente.
_INSPECTION_RE = re.compile(r"FECHA DE (?:LA )?INSPECCION\s*:?\s*" + _D)
_ISSUE_LABEL_PATTERNS = [
    re.compile(r"FECHA INICIO[A-Z ]{0,30}:?\s*" + _D),
    re.compile(r"FECHA DE (?:ENTREGA|EFECTO|EMISION|EXPEDICION)\s*:?\s*"
               + _D),
    re.compile(r"\bEL DIA\s*" + _D),
    re.compile(r"FECHA VALOR\s*:?\s*" + _D),
    re.compile(r"FECHA OPERACION\s*:?\s*" + _D),
    re.compile(r"F\.\s*EXP\.?\s*:?\s*" + _D),
    re.compile(r"\bFECHA\s*:?\s*" + _D),
    re.compile(r"INFORME TECNICO DE TACOGRAFO\D{0,20}" + _D),
    # Cajamar (IVTM): "GRUAS ADOLFO ALVAREZ S.L. 05/07/2021 80,43 EUR",
    # fecha del cargo pegada al importe, sin etiqueta.
    re.compile(
        r"(?<!\d)" + _D + r"\s+\d{1,3}(?:\.\d{3})*,\d{2}\s*(?:EUR|€)"
    ),
    # CaixaBank: "CARGO 2.01.26 2100 2274 ..." y la misma fecha delante
    # de la cuenta cuando la etiqueta queda lejos.
    re.compile(r"(?<!\d)" + _D + r"\s+\d{4} \d{4} \d{2} \d{10}"),
]
# DGT: "Autorización Complementaria de Circulación, número
# 20220509/009373" -- la fecha de la solicitud.
_DGT_REQUEST_RE = re.compile(
    r"COMPLEMENTARIA DE CIRCULACION\s*,?\s*NUMERO\s*" + _COMPACT_RE + "/"
)

# OCA (ECA/Bureau Veritas): "No Notificación: 41-26052010.035" -- la
# fecha de la inspección va dentro del número (DDMMAAAA).
_OCA_NOTIFICATION_RE = re.compile(
    r"NOTIFICACION\s*:?\s*\d{1,3}-(\d{2})(\d{2})((?:19|20)\d{2})"
)

# Carta con lugar y fecha: "TUBINGEN, 20.07.2006" (DGT alemana, S119).
_PLACE_DATE_RE = re.compile(
    r"\b[A-Z]{3,}\s*,\s*(\d{1,2})[./-](\d{1,2})[./-]((?:19|20)\d{2})\b"
)
# Respaldo final: cualquier fecha con año de 4 dígitos.
_FULL_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})[-./](\d{1,2})[-./]((?:19|20)\d{2})(?!\d)"
)
# Nombre con DDMMAAAA suelto ("26012024_hijstechniek", "8233 CKZ
# 19062025"); nunca el sello canónico "_TIPO_AAAAMMDD", que puede ser la
# fecha de subida (S118).
_NAME_DDMMYYYY_RE = re.compile(
    r"(?<![\d_])(\d{2})(\d{2})((?:19|20)\d{2})(?!\d)"
)
_CANONICAL_NAME_RE = re.compile(r"_[A-Z_]+_\d{8}(?:_\d+)?\.[A-Z]+$")

# --- 4. Mes y año en el nombre ------------------------------------------
_NAME_MONTH_YEAR_RE = re.compile(
    r"\b(" + "|".join(_MONTH_ABBR) + r")[A-Z]*[-_. ]*((?:19|20)\d{2})\b"
)

# --- 5. Fecha larga y en palabras --------------------------------------
_LONG_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+DE\s+(" + _MONTH_ALT + r")\s+(?:DE(?:L)?\s+)?"
    r"((?:19|20)\d{2})\b"
)
_WORDS_DATE_RE = re.compile(
    r"\b(" + _WORD_ALT + r")\s+DE\s+(" + _MONTH_ALT + r")\s+DE(?:L)?\s+"
    r"DOS MIL(?:\s+(" + _WORD_ALT + r"))?\b"
)


def normalize(text):
    """
    Upper-case, accent-free, single-spaced text.
    ---
    Texto en mayúsculas, sin tildes y con un único espacio (los saltos
    de línea del OCR no deben romper una etiqueta de dos palabras).
    """
    plain = unicodedata.normalize("NFKD", text or "")
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", plain.upper()).strip()


def _from_groups(groups):
    return _parse_date(*groups)


def _compact(groups):
    year, month, day = groups
    return _parse_date(day, month, year)


def _valid_issue(value, today):
    return value is not None and MIN_DATE <= value <= today


def _valid_expiry(value):
    return value is not None and MIN_DATE <= value <= MAX_EXPIRY


def _valid_period(start, end, min_days):
    if start is None or end is None or start < MIN_DATE:
        return False
    if end > MAX_EXPIRY:
        return False
    days = (end - start).days
    return min_days <= days <= MAX_PERIOD_DAYS


def _preceded_by(norm, match, words, width=40):
    before = norm[max(0, match.start() - width):match.start()]
    return any(word in before for word in words)


def _find_period(norm, code):
    min_days = MIN_PERIOD_DAYS_BY_CODE.get(code, MIN_PERIOD_DAYS)
    for pattern in _PERIOD_PATTERNS:
        for match in pattern.finditer(norm):
            if _preceded_by(norm, match, _PAYMENT_CONTEXT):
                continue
            groups = match.groups()
            start = _from_groups(groups[0:3])
            end = _from_groups(groups[3:6])
            if _valid_period(start, end, min_days):
                return start, end
    match = _COMPACT_PERIOD_RE.search(norm)
    if match:
        start = _compact(match.groups()[0:3])
        end = _compact(match.groups()[3:6])
        if _valid_period(start, end, min_days):
            return start, end
    return None


def _find_expiry(norm):
    found = [
        _from_groups(m.groups()) for m in _EXPIRY_LABEL_RE.finditer(norm)
    ]
    found = [value for value in found if _valid_expiry(value)]
    # Tarjeta ITV con varias inspecciones: la más reciente manda.
    return max(found) if found else None


def _find_issue(norm, today, expiry=None):
    inspections = [
        _from_groups(m.groups()) for m in _INSPECTION_RE.finditer(norm)
    ]
    inspections = [
        value for value in inspections if _valid_issue(value, today)
        and (expiry is None or value < expiry)
    ]
    if inspections:
        return max(inspections)
    for pattern in _ISSUE_LABEL_PATTERNS:
        for match in pattern.finditer(norm):
            if _preceded_by(norm, match, _REGISTRY_CONTEXT):
                continue
            value = _from_groups(match.groups())
            if _valid_issue(value, today):
                return value
    match = _DGT_REQUEST_RE.search(norm)
    if match:
        value = _compact(match.groups())
        if _valid_issue(value, today):
            return value
    match = _OCA_NOTIFICATION_RE.search(norm)
    if match:
        value = _parse_date(*match.groups())
        if _valid_issue(value, today):
            return value
    return None


def _find_long_or_words(norm, today):
    for match in _LONG_DATE_RE.finditer(norm):
        day, month_name, year = match.groups()
        value = _parse_date(day, _MONTHS[month_name], year)
        if _valid_issue(value, today):
            return value
    for match in _WORDS_DATE_RE.finditer(norm):
        day_word, month_name, year_word = match.groups()
        year = 2000 + (_NUMBER_WORDS[year_word] if year_word else 0)
        value = _parse_date(
            _NUMBER_WORDS[day_word], _MONTHS[month_name], year,
        )
        if _valid_issue(value, today):
            return value
    return None


def _find_latest(norm, today):
    """
    Most recent full date of the text (fallback, S119).
    ---
    Respaldo: la fecha más reciente con año de 4 dígitos, sin las
    registrales ni las futuras. En justificantes bancarios las etiquetas
    y los valores van separados y esa es la fecha del cargo.
    """
    found = []
    for match in _FULL_DATE_RE.finditer(norm):
        if _preceded_by(norm, match, _REGISTRY_CONTEXT):
            continue
        value = _from_groups(match.groups())
        if _valid_issue(value, today):
            found.append(value)
    return max(found) if found else None


def _from_name_digits(name, today):
    upper = normalize(name)
    if _CANONICAL_NAME_RE.search(upper):
        return None
    for match in _NAME_DDMMYYYY_RE.finditer(upper):
        value = _from_groups(match.groups())
        if _valid_issue(value, today):
            return value
    return None


def _from_name(code, name):
    match = _NAME_MONTH_YEAR_RE.search(normalize(name))
    if not match:
        return None
    month = _MONTH_ABBR[match.group(1)]
    year = int(match.group(2))
    if code in EXPIRY_BY_NAME_CODES:
        last_day = calendar.monthrange(year, month)[1]
        return "expiry", date(year, month, last_day)
    return "issue", date(year, month, 1)


def dates_by_rules(code, name, text, today=None):
    """
    Return {"expiry": date|None, "issue": date|None, "source": str} or
    None when no rule applies.
    ---
    Devuelve las fechas halladas por las reglas de S119 y la regla que
    las dio, o None si ninguna aplica. Nunca inventa: si no hay
    evidencia en el texto o en el nombre, devuelve None.
    """
    today = today or date.today()
    norm = normalize(text)
    by_name = _from_name(code, name or "")
    if norm:
        period = _find_period(norm, code)
        if period:
            return {
                "issue": period[0] if period[0] <= today else None,
                "expiry": period[1], "source": "regla periodo",
            }
        expiry = _find_expiry(norm)
        issue = _find_issue(norm, today, expiry)
        # ITV/OCA: si el texto solo da la emisión, la caducidad del
        # nombre ("ITV SEP-2014", criterio S48) la completa (id=4715).
        if expiry is None and by_name and by_name[0] == "expiry":
            expiry = by_name[1]
        if expiry and issue and expiry <= issue:
            expiry = None
        if expiry or issue:
            return {
                "expiry": expiry, "issue": issue,
                "source": "regla etiqueta",
            }
    if by_name:
        field, value = by_name
        if field == "expiry" and _valid_expiry(value):
            return {"expiry": value, "issue": None,
                    "source": "regla mes-año del nombre"}
        if field == "issue" and _valid_issue(value, today):
            return {"expiry": None, "issue": value,
                    "source": "regla mes-año del nombre"}
    if norm:
        value = _find_long_or_words(norm, today)
        if value:
            return {"expiry": None, "issue": value,
                    "source": "regla fecha larga"}
    return None


def fallback_dates(name, text, today=None):
    """
    Weak fallback rules; only when nothing else found a date.
    ---
    Reglas de respaldo (S119): lugar y fecha, DDMMAAAA del nombre y la
    fecha más reciente del texto. El comando solo las usa cuando ni
    `dates_by_rules` ni el criterio S48 por nombre dan ninguna fecha.
    """
    today = today or date.today()
    norm = normalize(text)
    if norm:
        match = _PLACE_DATE_RE.search(norm)
        value = _from_groups(match.groups()) if match else None
        if _valid_issue(value, today):
            return {"expiry": None, "issue": value,
                    "source": "regla lugar y fecha"}
    value = _from_name_digits(name or "", today)
    if value:
        return {"expiry": None, "issue": value,
                "source": "regla DDMMAAAA del nombre"}
    if norm:
        value = _find_latest(norm, today)
        if value:
            return {"expiry": None, "issue": value,
                    "source": "regla fecha mas reciente"}
    return None
