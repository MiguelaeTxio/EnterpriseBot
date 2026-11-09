# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/postal_code_service.py
"""
H31 (S100). Búsqueda de código postal real a partir del nombre de una
población -- Miguel Ángel, verbatim: "yo no te estoy diciendo que lo
extraigas del DNI, pero lo que sí sabemos es la población donde vive
[...] Loja tiene un código postal: 18300 [...] debe de haber una
tabla [...] donde podamos descargarnos los códigos postales de las
poblaciones."

Fuente real: `data/codigos_postales_municipios.csv`, extraído del
Callejero del Censo Electoral del INE
(https://github.com/regi-es/ds-codigos-postales-ine-es, licencia
CC BY 4.0 / ODC-PDDL -- datos abiertos oficiales, generados y
actualizados automáticamente contra el INE). NUNCA inventado ni
tecleado a mano aquí.

Un municipio puede tener varios códigos postales reales (ciudades
grandes con varios distritos postales). Sin calle para desambiguar,
se usa el MÁS BAJO de los reales del municipio -- convención habitual
de "código postal del centro/casco urbano" (verificado con Loja: el
dataset real trae 18300/18311/18312/18313/18314/18360, y 18300 -- el
más bajo -- es justo el que dio Miguel Ángel como referencia). Nunca
se inventa un código para una población que no aparece en el dataset.
"""
import csv
import os
import unicodedata

_CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "codigos_postales_municipios.csv")

_lookup_cache = None


def _normalize(name: str) -> str:
    value = unicodedata.normalize("NFKD", (name or "").strip().upper())
    return "".join(c for c in value if not unicodedata.combining(c))


def _load_lookup():
    global _lookup_cache
    if _lookup_cache is not None:
        return _lookup_cache
    lookup = {}
    with open(_CSV_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = _normalize(row["municipio_nombre"])
            codigo = row["codigo_postal"].strip()
            lookup.setdefault(key, []).append(codigo)
    for key, codes in lookup.items():
        lookup[key] = sorted(codes)
    _lookup_cache = lookup
    return lookup


def lookup_postal_code(city: str) -> str:
    """
    Devuelve el código postal más bajo real del municipio dado, o
    cadena vacía si el municipio no aparece en el dataset real -- NO
    lanza, nunca inventa un código para no dejar constancia falsa.
    """
    if not city:
        return ""
    lookup = _load_lookup()
    codes = lookup.get(_normalize(city))
    return codes[0] if codes else ""


def unique_postal_code(city: str) -> str:
    """
    S148: the postal code only when the municipality has just one.
    ---
    El código postal solo si el municipio tiene uno único: en un
    municipio con varios (Málaga, Vélez-Málaga...) el más bajo sería
    adivinar. Cadena vacía si no hay uno único.
    """
    if not city:
        return ""
    codes = _load_lookup().get(_normalize(city)) or []
    return codes[0] if len(set(codes)) == 1 else ""


# S148 (Miguel Ángel: "consultarlo on fly o tener un diccionario [...]
# por lo menos con los códigos postales de aquí de Málaga"): geocoder
# oficial de CartoCiudad (IGN/CNIG), gratuito y sin clave, que devuelve
# el C.P. de una dirección concreta (calle y número).
CARTOCIUDAD_FIND_URL = (
    "https://www.cartociudad.es/geocoder/api/geocoder/find")
_STREET_TYPES = (
    (r"^(C/|C\.|CL\.?|CALLE)\s*", "CALLE "),
    (r"^(AVDA\.?|AV\.?|AVENIDA)\s*", "AVENIDA "),
    (r"^(PLZA\.?|PZA\.?|PL\.?|PLAZA)\s*", "PLAZA "),
    (r"^(CM\.?|CMNO\.?|CAMINO)\s*", "CAMINO "),
    (r"^(CRTA\.?|CTRA\.?|CARRETERA)\s*", "CARRETERA "),
    (r"^(PSO\.?|PASEO)\s*", "PASEO "),
    (r"^(ARYO\.?|ARROYO)\s*", "ARROYO "),
    (r"^(URB\.?|URBANIZACION)\s*", "URBANIZACION "),
)


def _street_query(street):
    """
    "C. CASTILLA 17 P03 D" -> "CALLE CASTILLA 17" (type spelled out, up
    to the number: floor and door confuse the geocoder).
    ---
    Tipo de vía completo y hasta el número (piso y puerta sobran).
    """
    import re

    text = " ".join(_normalize(street).split())
    for pattern, replacement in _STREET_TYPES:
        text = re.sub(pattern, replacement, text)
    # Catastro: "PINOS (LOS) 0008" -> "LOS PINOS 8".
    text = re.sub(r"^(\w+ )(.+?) \((\w+)\)", r"\1\3 \2", text)
    street_type = next(
        (r for _p, r in _STREET_TYPES if text.startswith(r)), "")
    words = text[len(street_type):].split()
    # El número es el primer número que va detrás del nombre (no el de
    # "28 DE FEBRERO").
    for index, word in enumerate(words):
        if index and word.isdigit() and not (
                index + 1 < len(words) and words[index + 1] == "DE"):
            return "%s%s %d" % (
                street_type, " ".join(words[:index]), int(word))
    return text.strip()


def address_postal_code(street: str, city: str) -> str:
    """
    S148: postal code of a street address (CartoCiudad), or "".

    Only accepted when the geocoder places it in the same municipality
    and finds the street (portal or street, never just the town).
    ---
    C.P. de una dirección (calle y número) con CartoCiudad, o "". Solo
    se acepta si la sitúa en el mismo municipio y encuentra la calle
    (portal o vía, nunca solo la población). Nunca lanza: sin red o sin
    respuesta, "".
    """
    import re

    import requests

    if not street or not city:
        return ""
    query = "%s, %s" % (_street_query(street), _normalize(city))
    try:
        response = requests.get(
            CARTOCIUDAD_FIND_URL, params={"q": query}, timeout=6)
        data = response.json() if response.ok and response.text else {}
    except Exception:  # noqa: BLE001 -- sin C.P., nunca un error
        return ""
    if not isinstance(data, dict):
        return ""
    postal_code = str(data.get("postalCode") or "").strip()
    same_town = _normalize(city) in (
        _normalize(data.get("muni") or ""),
        _normalize(data.get("poblacion") or ""),
    )
    if (not re.fullmatch(r"(0[1-9]|[1-4][0-9]|5[0-2])[0-9]{3}", postal_code)
            or not same_town
            or data.get("type") not in ("portal", "callejero")):
        return ""
    return postal_code
