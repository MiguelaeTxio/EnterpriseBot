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
