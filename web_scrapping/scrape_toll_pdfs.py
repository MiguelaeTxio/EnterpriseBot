#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# scrape_toll_pdfs.py  v4
#
# Parser v4 — handles all MITMA PDF layouts confirmed by diagnostics:
#
#   Layout A: OD joined by hyphen, UPPERCASE, 3 or 5 price cols.
#             e.g. "MALAGA-CALAHONDA 3,55 5,75 7,05 7,05 7,05"
#             Roads: AP-7 (all sections)
#
#   Layout B: OD separated by spaces, UPPERCASE, 3 price cols.
#             Origin is first word(s), dest is last word(s).
#             e.g. "BILBAO ARRIGORRIAGA 1,05 1,90 2,15"
#             Roads: AP-6, AP-68
#
#   Layout C: OD joined by hyphen, mixed case, 3 price cols.
#             e.g. "Santiago-Ribadulla 2,00 1,65 2,00"
#             Roads: AP-53, AP-9
#
#   Layout D: Single barrier name, UPPERCASE, 3 price cols.
#             No hyphen separator — single location (barrier toll).
#             e.g. "TRONCAL DE CASABERMEJA 4,35 6,00 8,70"
#             Roads: AP-46
#
#   Layout E: OD joined by hyphen, mixed case, 6 price cols
#             (nocturnal + diurnal fares).
#             e.g. "Leon-Villadangos 0,70 1,15 1,40 1,75 2,35 2,85"
#             Roads: AP-71
#             Strategy: store cols 0,1,2 as night fares (lower),
#             cols 3,4,5 as day fares — we store day fares as the
#             canonical price since budget calcs handle night separately.
#
# ---
# Parser v4 — gestiona todos los layouts de PDF MITMA confirmados
# por el diagnostico.
#
# EXECUTION: run locally on PC, never on PythonAnywhere.
# EJECUCION: ejecutar en local en PC, nunca en PythonAnywhere.
# DEPENDENCIES: pip install pdfplumber requests

import sys
import json
import re
import time
import io
from datetime import date

try:
    import requests
except ImportError:
    print("[ERROR] Ejecuta: pip install requests")
    sys.exit(1)

try:
    import pdfplumber
except ImportError:
    print("[ERROR] Ejecuta: pip install pdfplumber")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Catalogue / Catalogo
# ---------------------------------------------------------------------------

MITMA_BASE = (
    "https://cdnfomento.blob.core.windows.net"
    "/portal-web-transportes/carreteras/nuestrared"
    "/autopistaspeaje/peajes-actuales"
)

# layout field:
#   "hyphen_upper"  — Layout A: ORIGIN-DEST uppercase hyphen-joined
#   "space_upper"   — Layout B: ORIGIN DEST uppercase space-separated
#   "hyphen_mixed"  — Layout C/E: Origin-Dest mixed case hyphen-joined
#   "barrier"       — Layout D: single barrier name (dest = origin)
TOLL_ROADS = [
    {
        "road_code": "AP-7",
        "section_name": "Malaga - Estepona",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-7,-malaga---estepona-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "00:00",
        "free_night_end": "06:00",
        "has_tariff_levels": True,
        "layout": "hyphen_upper",
    },
    {
        "road_code": "AP-7",
        "section_name": "Estepona - Guadiaro",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-7,-estepona---guadiaro-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "00:00",
        "free_night_end": "06:00",
        "has_tariff_levels": True,
        "layout": "hyphen_upper",
    },
    {
        "road_code": "AP-7",
        "section_name": "Alicante - Cartagena",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-7,-alicante---cartagena-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "00:00",
        "free_night_end": "06:00",
        "has_tariff_levels": False,
        "layout": "hyphen_upper",
    },
    {
        "road_code": "AP-46",
        "section_name": "Alto de las Pedrizas - Malaga",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-46,-alto-de-las-pedrizas---malaga-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "00:00",
        "free_night_end": "06:00",
        "has_tariff_levels": True,
        "tariff_keywords": {
            "NORMAL": "BAJA",
            "SPECIAL": "ALTA",
        },
        "layout": "barrier",
    },
    {
        "road_code": "AP-51",
        "section_name": "Conexion AP-6 - Avila",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-51,-conexion-ap-6---avila-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "00:00",
        "free_night_end": "06:00",
        "has_tariff_levels": False,
        "layout": "hyphen_upper",
    },
    {
        "road_code": "AP-53",
        "section_name": "Santiago - Alto de Santo Domingo",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-53,-santiago---alto-de-santo-domingo-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "00:00",
        "free_night_end": "06:00",
        "has_tariff_levels": False,
        "layout": "hyphen_mixed",
    },
    {
        "road_code": "AP-6",
        "section_name": "Villalba - Adanero",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-6,-villalba---adanero-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "00:00",
        "free_night_end": "06:00",
        "has_tariff_levels": False,
        "layout": "space_upper",
        "od_split": {
            "VILLALBA SAN RAFAEL": ("VILLALBA", "SAN RAFAEL"),
            "VILLALBA VILLACASTIN": ("VILLALBA", "VILLACASTIN"),
            "VILLALBA ADANERO": ("VILLALBA", "ADANERO"),
            "SAN RAFAEL VILLASCASTIN": ("SAN RAFAEL", "VILLASCASTIN"),
            "SAN RAFAEL ADANERO": ("SAN RAFAEL", "ADANERO"),
            "VILLACASTIN ADANERO": ("VILLACASTIN", "ADANERO"),
        },
    },
    {
        "road_code": "AP-61",
        "section_name": "Conexion AP-6 - Segovia",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-61,-conexion-ap-6---segovia-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "00:00",
        "free_night_end": "06:00",
        "has_tariff_levels": False,
        "layout": "hyphen_upper",
    },
    {
        "road_code": "AP-66",
        "section_name": "Campomanes - Leon",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-66,-campomanes---leon-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "00:00",
        "free_night_end": "06:00",
        "has_tariff_levels": False,
        "layout": "hyphen_upper",
    },
    {
        "road_code": "AP-68",
        "section_name": "Bilbao - Zaragoza",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-68,-bilbao---zaragoza-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "00:00",
        "free_night_end": "06:00",
        "has_tariff_levels": False,
        "layout": "space_upper",
    },
    {
        "road_code": "AP-71",
        "section_name": "Leon - Astorga",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-71,-leon---astorga-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "23:00",
        "free_night_end": "07:00",
        "has_tariff_levels": False,
        "layout": "hyphen_mixed",
        "six_cols": True,
    },
    {
        "road_code": "AP-9",
        "section_name": "Ferrol - Frontera portuguesa",
        "url": (
            f"{MITMA_BASE}"
            "/autopista-ap-9,-ferrol---frontera-portuguesa-2026.pdf"
        ),
        "has_free_night": True,
        "free_night_start": "00:00",
        "free_night_end": "06:00",
        "has_tariff_levels": False,
        "layout": "space_upper",
    },
]

VALID_FROM = "2026-01-01"
REQUEST_DELAY = 1.5

PRICE_RE = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}$")

SKIP_RE = re.compile(
    r"^(MINISTERIO|DE TRANSPORTES|Y MOVILIDAD|PEAJES VIGENTES|EN LA AUTOPISTA"
    r"|NIVEL TARIFARIO|BARRERAS DE PEAJE|RECORRIDOS DIRECTOS|TARIFA GENERAL"
    r"|CON APLICACI|BONIFICACIONES|LIGEROS\s*$|PESADOS\s*[12]?\s*$"
    r"|1\.0\s|2\.1\s|CON TARIFA|RECORRIDOS DIRECTOS E INVERSOS$"
    r"|Descripci|Ligeros$|Pesados|Motocicletas|Vehículos de turismo"
    r"|Furgones|Camiones|Autocares|Turismos|Clase|Tramo\s|Recorrido\s"
    r"|Según|De acuerdo|Los vehículos|Se entiende|Temporada|Habitualidad"
    r"|Nivel tarifario|Tarifa nocturna|Tarifa diurna|Durante todos)",
    re.IGNORECASE,
)


def parse_price(raw):
    """
    Convert Spanish-locale price string to float.
    ---
    Convierte cadena de precio en locale espanol a float.
    """
    return float(raw.strip().replace(".", "").replace(",", "."))


def extract_prices_from_tokens(tokens):
    """
    Collect contiguous price tokens from the right end of a token list.
    Returns (price_list, remaining_tokens).
    ---
    Recoge tokens de precio contiguos desde el extremo derecho.
    Devuelve (lista_precios, tokens_restantes).
    """
    prices = []
    remaining = list(tokens)
    while remaining and PRICE_RE.match(remaining[-1]):
        prices.insert(0, remaining.pop())
    return prices, remaining


def split_od_hyphen(od_string):
    """
    Split "ORIGIN-DEST" or "Origin-Dest" on the OD hyphen.
    The OD hyphen is the last hyphen flanked by word characters
    where both sides have at least one letter.
    Handles multi-word names like "SAN PEDRO DE ALCANTARA-ESTEPONA"
    and mixed-case "Santiago-Ribadulla".
    ---
    Divide "ORIGIN-DEST" o "Origin-Dest" en el guion OD.
    El guion OD es el ultimo guion flanqueado por caracteres de palabra
    donde ambos lados tienen al menos una letra.
    """
    candidates = [
        m.start()
        for m in re.finditer(r"(?<=[A-Za-z0-9])-(?=[A-Za-z])", od_string)
    ]
    if not candidates:
        return None, None
    split_pos = candidates[-1]
    origin = od_string[:split_pos].strip().upper()
    dest = od_string[split_pos + 1:].strip().upper()
    return origin, dest


def split_od_space_upper(od_string, road_meta):
    """
    Split an all-uppercase space-separated OD string.
    Strategy: use explicit od_split dict if provided, otherwise
    split at the last uppercase single-word token boundary using
    the heuristic that most destination names are single words.
    For AP-9 the separator is " - " (space-hyphen-space).
    ---
    Divide una cadena OD en mayusculas separada por espacios.
    Estrategia: usar el diccionario od_split explicito si se proporciona,
    de lo contrario dividir en el ultimo token de palabra unica usando
    la heuristica de que la mayoria de destinos son palabras simples.
    Para AP-9 el separador es " - " (espacio-guion-espacio).
    """
    # AP-9 uses " - " as OD separator.
    # AP-9 usa " - " como separador OD.
    if " - " in od_string:
        parts = od_string.split(" - ", 1)
        return parts[0].strip().upper(), parts[1].strip().upper()

    # Explicit mapping provided in road_meta.
    # Mapeo explicito proporcionado en road_meta.
    od_split = road_meta.get("od_split", {})
    key = od_string.strip().upper()
    if key in od_split:
        return od_split[key]

    # Heuristic: split after the first word (origin) for short names,
    # or find the natural break by trying all split points and picking
    # the one where the destination looks like a single known word.
    # For AP-68 all origins/destinations are single words.
    # Heuristica: para AP-68 origen y destino son siempre palabras simples.
    tokens = od_string.strip().upper().split()
    if len(tokens) == 2:
        return tokens[0], tokens[1]
    if len(tokens) >= 3:
        # Try split at position 1 (first word = origin).
        # Intentar division en posicion 1 (primera palabra = origen).
        return tokens[0], " ".join(tokens[1:])
    return od_string.strip().upper(), ""


def detect_tariff_level(page_text, road_meta):
    """
    Detect tariff level from page text using road-specific keywords
    or the default ESPECIAL/NORMAL detection.
    ---
    Detecta el nivel tarifario del texto de pagina usando palabras clave
    especificas de la via o la deteccion por defecto ESPECIAL/NORMAL.
    """
    keywords = road_meta.get("tariff_keywords", {})
    if keywords:
        # Check SPECIAL keyword first.
        # Comprobar palabra clave SPECIAL primero.
        special_kw = keywords.get("SPECIAL", "ALTA")
        normal_kw = keywords.get("NORMAL", "BAJA")
        if re.search(special_kw, page_text, re.IGNORECASE):
            return "SPECIAL"
        if re.search(normal_kw, page_text, re.IGNORECASE):
            return "NORMAL"
        return "NORMAL"
    if re.search(r"ESPECIAL", page_text, re.IGNORECASE):
        return "SPECIAL"
    return "NORMAL"


def parse_pdf_rows(pdf_bytes, road_meta):
    """
    Extract fare rows from a MITMA toll PDF.
    Dispatches to the appropriate parsing strategy based on road layout.
    ---
    Extrae filas tarifarias de un PDF de peajes MITMA.
    Delega a la estrategia de parseo apropiada segun el layout de la via.
    """
    segments = []
    has_levels = road_meta.get("has_tariff_levels", False)
    layout = road_meta.get("layout", "hyphen_upper")
    six_cols = road_meta.get("six_cols", False)
    seen = set()

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            raw = page.extract_text(
                x_tolerance=3,
                y_tolerance=3,
            ) or ""

            tariff_level = (
                detect_tariff_level(raw, road_meta)
                if has_levels
                else "NORMAL"
            )

            for line in raw.splitlines():
                line = line.strip()
                if not line or SKIP_RE.match(line):
                    continue

                tokens = line.split()
                if len(tokens) < 2:
                    continue

                prices, remaining = extract_prices_from_tokens(tokens)

                min_prices = 6 if six_cols else 3
                if len(prices) < min_prices or not remaining:
                    continue

                od_string = " ".join(remaining)

                # Skip lines that are clearly headers.
                # Omitir lineas que son claramente cabeceras.
                if SKIP_RE.match(od_string):
                    continue

                # Parse OD according to layout.
                # Parsear OD segun el layout.
                if layout == "hyphen_upper" or layout == "hyphen_mixed":
                    origin, dest = split_od_hyphen(od_string)
                    if not origin or not dest:
                        # Fallback: barrier-style single name.
                        # Fallback: nombre de barrera simple.
                        origin = od_string.strip().upper()
                        dest = origin
                elif layout == "barrier":
                    origin = od_string.strip().upper()
                    dest = origin
                elif layout == "space_upper":
                    origin, dest = split_od_space_upper(
                        od_string, road_meta
                    )
                    if not origin or not dest:
                        continue
                else:
                    origin = od_string.strip().upper()
                    dest = origin

                if not origin:
                    continue

                # Extract prices.
                # For 6-col layout: cols 3,4,5 = day fares (canonical).
                # For 5-col layout: cols 0,1,4 = light, heavy1, heavy2.
                # For 3-col layout: cols 0,1,2.
                # Extraer precios.
                # Para 6 cols: cols 3,4,5 = tarifas diurnas (canonicas).
                # Para 5 cols: cols 0,1,4 = ligero, pesado1, pesado2.
                # Para 3 cols: cols 0,1,2.
                try:
                    if six_cols:
                        p_light = parse_price(prices[3])
                        p_heavy1 = parse_price(prices[4])
                        p_heavy2 = parse_price(prices[5])
                    elif len(prices) >= 5:
                        p_light = parse_price(prices[0])
                        p_heavy1 = parse_price(prices[1])
                        p_heavy2 = parse_price(prices[4])
                    else:
                        p_light = parse_price(prices[0])
                        p_heavy1 = parse_price(prices[1])
                        p_heavy2 = parse_price(prices[2])
                except (ValueError, IndexError):
                    continue

                dedup_key = (
                    road_meta["road_code"],
                    origin,
                    dest,
                    tariff_level,
                )
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                segments.append({
                    "road_code": road_meta["road_code"],
                    "section_name": road_meta["section_name"],
                    "origin_name": origin,
                    "dest_name": dest,
                    "price_light": p_light,
                    "price_heavy_1": p_heavy1,
                    "price_heavy_2": p_heavy2,
                    "tariff_level": tariff_level,
                    "has_free_night": road_meta["has_free_night"],
                    "free_night_start": road_meta.get(
                        "free_night_start"
                    ),
                    "free_night_end": road_meta.get("free_night_end"),
                    "valid_from": VALID_FROM,
                    "is_active": True,
                })

    return segments


def main():
    """
    Entry point: download PDFs, parse, write toll_segments.json.
    ---
    Punto de entrada: descargar PDFs, parsear, escribir toll_segments.json.
    """
    all_segments = []
    errors = []

    print(
        f"[INFO] Iniciando scraping de {len(TOLL_ROADS)} "
        f"autopistas MITMA."
    )
    print(f"[INFO] Fecha de vigencia: {VALID_FROM}")
    print()

    for idx, road in enumerate(TOLL_ROADS, start=1):
        label = f"{road['road_code']} - {road['section_name']}"
        print(f"[{idx:02d}/{len(TOLL_ROADS):02d}] {label}")

        try:
            resp = requests.get(
                road["url"],
                timeout=30,
                headers={
                    "User-Agent": "EnterpriseBot-TollScraper/4.0"
                },
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"  [ERROR] Descarga: {exc}")
            errors.append({"road": label, "error": str(exc)})
            time.sleep(REQUEST_DELAY)
            continue

        print(f"  [OK] {len(resp.content):,} bytes")

        try:
            segments = parse_pdf_rows(resp.content, road)
        except Exception as exc:
            print(f"  [ERROR] Parseo: {exc}")
            errors.append({"road": label, "error": str(exc)})
            time.sleep(REQUEST_DELAY)
            continue

        print(f"  [OK] {len(segments)} tramos extraidos")
        all_segments.extend(segments)
        time.sleep(REQUEST_DELAY)

    output = {
        "generated_at": str(date.today()),
        "total_segments": len(all_segments),
        "errors": errors,
        "segments": all_segments,
    }

    out_path = "toll_segments.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    print()
    print(f"[DONE] {len(all_segments)} tramos en: {out_path}")
    if errors:
        print(f"[WARN] {len(errors)} autopistas con errores:")
        for err in errors:
            print(f"  - {err['road']}: {err['error']}")


if __name__ == "__main__":
    main()
