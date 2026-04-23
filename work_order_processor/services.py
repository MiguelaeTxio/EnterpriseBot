# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/services.py

"""
Business logic services for the work_order_processor application.
Contains two primary services:
  - extract_work_order_page(): sends a rasterized PDF page to Gemini Vision
    and returns a structured multi-block dict (up to 4 work blocks per page).
  - generate_work_order_excel(): builds an Excel report conforming to the
    partes-trabajo skill v1.2 specification: 17 columns, configuration area
    (rows 1-3), colour-coded REVISION HORARIO, LEYENDA sheet and MANIFIESTO
    DE INCIDENCIAS block at the foot of the data sheet.

---

Servicios de lógica de negocio para la aplicación work_order_processor.
Contiene dos servicios principales:
  - extract_work_order_page(): envía una página del PDF rasterizada a Gemini
    Vision y devuelve un dict multi-bloque estructurado (hasta 4 bloques de
    trabajo por página).
  - generate_work_order_excel(): construye un informe Excel conforme a la
    especificación de la skill partes-trabajo v1.2: 17 columnas, área de
    configuración (filas 1-3), REVISIÓN HORARIO con código de colores, hoja
    LEYENDA y bloque MANIFIESTO DE INCIDENCIAS al pie de la hoja de datos.
"""

import io
import json
import logging
import os
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from django.core.files.base import ContentFile
from django.utils import timezone
from google import genai
from google.genai.types import HttpOptions, Part

from fleet.models import MachineAsset
from .models import WorkOrder, WorkOrderEntry, WorkOrderEntryLine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini client initialisation (Vertex AI — Directriz 4.1)
# Inicialización del cliente Gemini (Vertex AI — Directriz 4.1)
# ---------------------------------------------------------------------------
_GEMINI_MODEL  = "gemini-2.5-flash"
_GEMINI_CLIENT = None   # Lazy singleton — inicializado en primera llamada.


def _get_gemini_client() -> genai.Client:
    """
    Returns a lazily-initialised Gemini client configured for Vertex AI.
    Uses the service account credentials defined by GCP_CREDENTIALS_PATH,
    GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION environment variables,
    consistent with the rest of the EnterpriseBot platform (Directriz 4.1).

    ---

    Devuelve un cliente Gemini inicializado de forma lazy para Vertex AI.
    Utiliza las credenciales de cuenta de servicio definidas por las variables
    de entorno GCP_CREDENTIALS_PATH, GOOGLE_CLOUD_PROJECT y
    GOOGLE_CLOUD_LOCATION, en coherencia con el resto de la plataforma
    EnterpriseBot (Directriz 4.1).
    """
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is None:
        os.environ.setdefault(
            "GOOGLE_APPLICATION_CREDENTIALS",
            os.environ.get("GCP_CREDENTIALS_PATH", ""),
        )
        # HttpOptions.timeout is specified in MILLISECONDS per the google-genai SDK.
        # 360000 ms = 6 minutes — sufficient margin for complex handwritten pages.
        # The SDK passes this value directly to httpx per-request, overriding any
        # client-level timeout. This is the only reliable way to extend the timeout.
        # HttpOptions.timeout se especifica en MILISEGUNDOS según el SDK google-genai.
        # 360000 ms = 6 minutos — margen suficiente para páginas manuscritas complejas.
        _GEMINI_CLIENT = genai.Client(
            http_options=HttpOptions(api_version="v1", timeout=360000),
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION"),
        )
        logger.info("# Cliente Gemini Vision inicializado correctamente (Vertex AI).")
    return _GEMINI_CLIENT


# ---------------------------------------------------------------------------
# Extraction prompt — multi-block / Prompt de extracción — multi-bloque
# ---------------------------------------------------------------------------
# Conforms to the partes-trabajo skill v1.2 JSON output specification.
# The operario field is intentionally left null — it is derived from the
# PDF filename in tasks.py, not from the handwritten text (D6 / annex V06).
#
# Conforme a la especificación JSON de salida de la skill partes-trabajo v1.2.
# El campo operario se deja intencionadamente null — se deriva del nombre del
# fichero PDF en tasks.py, no del texto manuscrito (D6 / anexo V06).

_EXTRACTION_PROMPT = """\
Eres un asistente especializado en la extracción de datos de partes de trabajo
manuscritos de una empresa de grúas y maquinaria industrial (grúas móviles,
plataformas elevadoras, autocargantes, cabezas tractoras, semirremolques,
carretillas elevadoras). Las averías y reparaciones pertenecen siempre a este
tipo de vehículos y maquinaria pesada industrial.

Analiza la imagen del parte de trabajo manuscrito. Cada página es un parte
DIARIO con una única fecha en la cabecera y hasta 4 bloques de trabajo.

REGLAS OBLIGATORIAS:
1. Responde ÚNICAMENTE con un objeto JSON válido. Sin texto adicional, sin
   bloques de código markdown, sin explicaciones.
2. Si un campo no es legible o no aparece, usa null.
3. Fechas en formato "DD/MM/YYYY". Horas en formato "HH:MM".
4. Horarios SIEMPRE redondeados a fracciones de media hora (:00 o :30).
   Ejemplos: 09:20 → "09:30", 07:10 → "07:00", 17:45 → "18:00".
5. El campo "fecha_incierta" es true solo si la fecha es genuinamente ilegible
   tras intentar deducirla por contexto. No lo uses si puedes leerla.
6. En "maquina_raw" copia exactamente lo que lees. Si aparece "Larios" en
   cualquier contexto de máquina, inclúyelo — es un alias reconocido de empresa.
   "Salida polígonos" NO es una máquina: deja maquina_raw null en ese caso.
7. Interpreta abreviaturas técnicas en contexto de vehículos pesados:
   "hid." → hidráulico, "trans." → transmisión, "dir." → dirección,
   "mto." → mantenimiento, "ace." → aceite, "fil." → filtro.
8. Si un campo es de lectura incierta (no imposible, sino dudosa), inclúyelo
   con el valor más probable y añade el nombre del campo a "flags".
   Campos que pueden ir en flags: "FECHA", "H.C.", "H.F.", "DESCRIPCION",
   "MAQUINA".
9. Procesa SOLO los bloques que tengan al menos un campo relleno. Ignora
   bloques completamente vacíos.
10. "extraction_confidence" evalúa la calidad global de la página:
    "HIGH" = todos los campos principales legibles,
    "MEDIUM" = alguna duda menor,
    "LOW" = campos importantes ilegibles,
    "FAILED" = imagen ilegible o no es un parte de trabajo.

Formato de respuesta (claves exactas):
{
  "fecha": "<DD/MM/YYYY o null>",
  "fecha_incierta": <true | false>,
  "extraction_confidence": "<HIGH | MEDIUM | LOW | FAILED>",
  "entradas": [
    {
      "maquina_raw": "<código o alias tal como aparece, o null>",
      "descripcion_averia": "<descripción de la avería o tarea, o null>",
      "reparacion": "<descripción de la reparación realizada, o null>",
      "hc": "<HH:MM o null>",
      "hf": "<HH:MM o null>",
      "or_val": "<referencia O.R. o null>",
      "flags": ["CAMPO1", "CAMPO2"]
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# Public service: page extraction
# Servicio público: extracción de página
# ---------------------------------------------------------------------------

def extract_work_order_page(image_bytes: bytes) -> dict[str, Any]:
    """
    Sends a rasterized PDF page (PNG bytes) to Gemini Vision and returns
    a structured multi-block dict conforming to the partes-trabajo skill
    v1.2 JSON specification.

    Applies tolerant JSON parsing: strips markdown fences and locates the
    outermost JSON object within the response text. On total failure returns
    a safe fallback dict with an empty entradas list and confidence FAILED.

    ---

    Envía una página del PDF rasterizada (bytes PNG) a Gemini Vision y
    devuelve un dict multi-bloque estructurado conforme a la especificación
    JSON de la skill partes-trabajo v1.2.

    Aplica parseo JSON tolerante: elimina bloques markdown y localiza el
    objeto JSON más externo dentro del texto de respuesta. En caso de fallo
    total devuelve un dict de reserva seguro con lista entradas vacía y
    confianza FAILED.
    """
    client = _get_gemini_client()

    try:
        logger.info("# Gemini Vision: iniciando extracción de página.")
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[
                Part.from_bytes(data=image_bytes, mime_type="image/png"),
                _EXTRACTION_PROMPT,
            ],
        )
        raw_text = response.text.strip()
        logger.info("# Gemini Vision: respuesta recibida. Parseando JSON.")

        # Strip markdown fences / Eliminar bloques markdown.
        cleaned = re.sub(r"```(?:json)?|```", "", raw_text).strip()

        # Locate outermost JSON object / Localizar objeto JSON más externo.
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(
                f"No se encontró ningún objeto JSON en la respuesta de Gemini: "
                f"{raw_text[:200]}"
            )

        extracted: dict[str, Any] = json.loads(match.group())

        # Ensure entradas is always a list / Garantizar que entradas es siempre lista.
        if not isinstance(extracted.get("entradas"), list):
            extracted["entradas"] = []

        logger.info(
            "# Gemini Vision: extracción completada. Confianza: %s | Entradas: %d",
            extracted.get("extraction_confidence", "DESCONOCIDA"),
            len(extracted.get("entradas", [])),
        )
        return extracted

    except Exception as exc:
        logger.error(
            "# Error crítico en extract_work_order_page: %s", exc, exc_info=True
        )
        return {
            "fecha":                None,
            "fecha_incierta":       False,
            "extraction_confidence": "FAILED",
            "entradas":             [],
        }


# ---------------------------------------------------------------------------
# Helper functions / Funciones auxiliares
# ---------------------------------------------------------------------------

def _parse_date(value: str | None) -> date | None:
    """
    Parses a date string in DD/MM/YYYY format into a Python date.
    Returns None if value is None, empty or unparseable.

    ---

    Parsea una cadena de fecha en formato DD/MM/YYYY a un objeto date.
    Devuelve None si el valor es None, vacío o no parseable.
    """
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    logger.warning("# _parse_date: valor no parseable ignorado: %r", value)
    return None


def _parse_time(value: str | None) -> time | None:
    """
    Parses a time string in HH:MM format into a Python time.
    Returns None if value is None, empty or unparseable.

    ---

    Parsea una cadena de hora en formato HH:MM a un objeto time de Python.
    Devuelve None si el valor es None, vacío o no parseable.
    """
    if not value:
        return None
    try:
        parts = value.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, TypeError, IndexError):
        logger.warning("# _parse_time: valor no parseable ignorado: %r", value)
        return None


def _coerce_confidence(value: str | None) -> str:
    """
    Validates the confidence value returned by Gemini against the allowed
    choices. Falls back to 'LOW' if the value is unrecognised.

    ---

    Valida el valor de confianza devuelto por Gemini contra las opciones
    permitidas. Devuelve 'LOW' si el valor no es reconocido.
    """
    allowed = {c.value for c in WorkOrderEntry.Confidence}
    if value and value.upper() in allowed:
        return value.upper()
    return WorkOrderEntry.Confidence.LOW


def _normalise_machine_code(raw: str | None) -> str:
    """
    Normalises a raw machine code string according to partes-trabajo skill
    directive D4:
      1. Strip and uppercase.
      2. Remove internal spaces.
      3. Insert a hyphen between the leading letter(s) and the numeric block
         if not already present.
      4. Return empty string if raw is None or blank.

    ---

    Normaliza un código de máquina bruto según la directriz D4 de la skill
    partes-trabajo:
      1. Strip y mayúsculas.
      2. Eliminar espacios internos.
      3. Insertar guion entre la(s) letra(s) inicial(es) y el bloque numérico
         si no está ya presente.
      4. Devolver cadena vacía si raw es None o en blanco.
    """
    if not raw:
        return ""
    code = raw.strip().upper().replace(" ", "")
    # Insert hyphen between leading letters and digits if absent.
    # Insertar guion entre letras iniciales y dígitos si no está presente.
    code = re.sub(r"^([A-Z]+)(\d)", r"\1-\2", code)
    return code


def _resolve_machine_asset(maquina_norm: str) -> MachineAsset | None:
    """
    Attempts to resolve a normalised machine code to a MachineAsset record.
    Tries exact match first, then zero-padded variants (G-8 → G-08, G-08 → G-8).
    Returns None if no match is found.

    ---

    Intenta resolver un código de máquina normalizado a un registro MachineAsset.
    Prueba primero coincidencia exacta, luego variantes con ceros (G-8 → G-08,
    G-08 → G-8). Devuelve None si no se encuentra coincidencia.
    """
    if not maquina_norm:
        return None

    # Exact match / Coincidencia exacta.
    try:
        return MachineAsset.objects.get(codigo=maquina_norm)
    except MachineAsset.DoesNotExist:
        pass
    except MachineAsset.MultipleObjectsReturned:
        logger.warning(
            "# _resolve_machine_asset: múltiples coincidencias para '%s'.", maquina_norm
        )
        return None

    # Zero-padding variants / Variantes con relleno de ceros.
    # Try adding/removing a leading zero in the numeric part.
    # Probar añadiendo/eliminando un cero inicial en la parte numérica.
    m = re.match(r"^([A-Z]+-?)(\d+)$", maquina_norm)
    if m:
        prefix, digits = m.group(1), m.group(2)
        candidates = set()
        if len(digits) == 1:
            candidates.add(f"{prefix}0{digits}")
            candidates.add(f"{prefix}00{digits}")
        elif len(digits) == 2 and digits.startswith("0"):
            candidates.add(f"{prefix}{digits[1:]}")
        elif len(digits) == 3 and digits.startswith("0"):
            candidates.add(f"{prefix}{digits[1:]}")
            candidates.add(f"{prefix}{digits[2:]}")

        for candidate in candidates:
            try:
                return MachineAsset.objects.get(codigo=candidate)
            except (MachineAsset.DoesNotExist, MachineAsset.MultipleObjectsReturned):
                continue

    return None


def _compute_delta_horas(hc: time | None, hf: time | None) -> Decimal | None:
    """
    Computes the net hours for a work block by subtracting the lunch break
    (13:30–15:00, 90 minutes) if the block covers that interval, as defined
    in the partes-trabajo skill.

    Returns a Decimal rounded to 2 decimal places, or None if either time
    is missing or hf <= hc.

    ---

    Calcula las horas netas de un bloque de trabajo descontando la pausa de
    comida (13:30–15:00, 90 minutos) si el bloque cubre ese intervalo, según
    la definición de la skill partes-trabajo.

    Devuelve un Decimal redondeado a 2 decimales, o None si alguna hora falta
    o hf <= hc.
    """
    if not hc or not hf:
        return None

    # Convert to minutes since midnight / Convertir a minutos desde medianoche.
    hc_min = hc.hour * 60 + hc.minute
    hf_min = hf.hour * 60 + hf.minute

    if hf_min <= hc_min:
        return None

    total_min = hf_min - hc_min

    # Lunch break deduction: 13:30–15:00 = 90 minutes.
    # Descuento pausa comida: 13:30–15:00 = 90 minutos.
    lunch_start = 13 * 60 + 30   # 810
    lunch_end   = 15 * 60        # 900

    overlap_start = max(hc_min, lunch_start)
    overlap_end   = min(hf_min, lunch_end)
    deduction     = max(0, overlap_end - overlap_start)

    net_min = total_min - deduction
    net_h   = Decimal(net_min) / Decimal(60)
    return net_h.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _worker_name_from_pdf_path(pdf_name: str) -> str:
    """
    Derives the worker's full name from the PDF filename.
    Expected format: NOMBRE_APELLIDO1_APELLIDO2_DD-MM_AL_DD-MM.pdf
    or any variant where the name occupies the leading underscore-separated
    tokens before a token matching DD-MM or AL.

    Returns the name in uppercase with spaces, e.g. "ALEJANDRO GARCIA LUQUE".
    Falls back to the raw filename stem if the format is unrecognised.

    ---

    Deriva el nombre completo del operario del nombre del fichero PDF.
    Formato esperado: NOMBRE_APELLIDO1_APELLIDO2_DD-MM_AL_DD-MM.pdf
    o cualquier variante donde el nombre ocupa los tokens iniciales separados
    por guion bajo antes de un token con formato DD-MM o AL.

    Devuelve el nombre en mayúsculas con espacios, ej: "ALEJANDRO GARCIA LUQUE".
    Devuelve el stem del nombre de fichero bruto si el formato no se reconoce.
    """
    import os
    stem   = os.path.splitext(os.path.basename(pdf_name))[0]
    tokens = stem.split("_")

    name_tokens: list[str] = []
    for tok in tokens:
        # Stop at a date token (DD-MM or DD-MM-YYYY) or the literal "AL".
        # Parar en un token de fecha (DD-MM o DD-MM-YYYY) o el literal "AL".
        if re.match(r"^\d{2}-\d{2}(-\d{4})?$", tok) or tok.upper() == "AL":
            break
        name_tokens.append(tok.upper())

    return " ".join(name_tokens) if name_tokens else stem.upper()


# ---------------------------------------------------------------------------
# Excel generation constants / Constantes de generación Excel
# ---------------------------------------------------------------------------

# Colour palette / Paleta de colores
_CLR_HEADER_BG    = "1F4E79"   # Azul oscuro — cabecera de columnas
_CLR_HEADER_FG    = "FFFFFF"   # Blanco — texto cabecera
_CLR_CONFIG_LABEL = "D6E4F0"   # Azul muy claro — etiquetas área config
_CLR_CONFIG_INPUT = "FFFF99"   # Amarillo — celdas de entrada C2 y C3
_CLR_DATE_FIRST   = "BDD7EE"   # Azul claro — primera entrada del día (col FECHA)
_CLR_DATE_UNCERT  = "FFD700"   # Dorado — fecha incierta
_CLR_MACHINE_UNKN = "FFD700"   # Dorado — máquina no identificada
_CLR_MACHINE_EMPT = "D9D9D9"   # Gris — máquina vacía
_CLR_REV_GREEN    = "70AD47"   # Verde — jornada estándar (= 8h)
_CLR_REV_BLUE     = "9DC3E6"   # Azul claro — horas extra (8–12h)
_CLR_REV_YELLOW   = "FFFF00"   # Amarillo — por debajo mínimo (7–8h)
_CLR_REV_ORANGE   = "F4B942"   # Naranja — jornada excesiva (12–16h)
_CLR_REV_RED      = "FF0000"   # Rojo — fuera de rango (< 7h ó > 16h)
_CLR_MANIFEST_BG  = "1F4E79"   # Azul oscuro — cabecera manifiesto
_CLR_MANIFEST_FG  = "FFFFFF"   # Blanco — texto cabecera manifiesto

# Column definitions: (header, width)
# Definición de columnas: (cabecera, ancho)
_COLS = [
    ("FECHA",             14),   # A  1
    ("OPERARIO",          28),   # B  2
    ("CÓDIGO / VEH.",     14),   # C  3
    ("MARCA / MODELO",    28),   # D  4
    ("KM",                10),   # E  5
    ("HORAS VEH.",        10),   # F  6
    ("DESCRIPCIÓN AVERÍA",40),   # G  7
    ("REPARACIÓN",        40),   # H  8
    ("H.C.",               8),   # I  9
    ("H.F.",               8),   # J 10
    ("O.R.",              12),   # K 11
    ("Δ HORAS (neta)",    12),   # L 12
    ("HORAS NETAS DÍA",  14),   # M 13
    ("HORAS EXTRAS",     12),   # N 14
    ("SALARIO EXTRAS",   14),   # O 15
    ("REVISIÓN HORARIO", 16),   # P 16
    ("COSTE M.O.",        14),   # Q 17  — delta_horas × C3 (coste hora ordinaria)
]

_DATA_ROW_START = 5   # Datos comienzan en fila 5 (filas 1-3 config, 4 cabecera)


def _make_fill(hex_color: str) -> PatternFill:
    """Returns a solid PatternFill for the given hex colour string.
    --- Devuelve un PatternFill sólido para el color hex indicado."""
    return PatternFill(fill_type="solid", fgColor=hex_color)


def _make_border_thin() -> Border:
    """Returns a thin border on all four sides.
    --- Devuelve un borde fino en los cuatro lados."""
    s = Side(style="thin")
    return Border(left=s, right=s, top=s, bottom=s)


def _revision_color(horas_netas_dia: Decimal | None) -> str:
    """
    Returns the hex colour code for the REVISION HORARIO cell based on the
    daily net hours total, according to the partes-trabajo skill colour table.

    ---

    Devuelve el código de color hex para la celda REVISIÓN HORARIO basándose
    en el total de horas netas del día, según la tabla de colores de la skill.
    """
    if horas_netas_dia is None:
        return _CLR_MACHINE_EMPT  # Gris si no hay dato.
    h = float(horas_netas_dia)
    if h == 8.0:
        return _CLR_REV_GREEN
    if 8.0 < h <= 12.0:
        return _CLR_REV_BLUE
    if 7.0 <= h < 8.0:
        return _CLR_REV_YELLOW
    if 12.0 < h <= 16.0:
        return _CLR_REV_ORANGE
    return _CLR_REV_RED   # < 7h ó > 16h


def _revision_text(horas_netas_dia: Decimal | None) -> str:
    """
    Returns the display text for the REVISION HORARIO cell.
    --- Devuelve el texto de visualización para la celda REVISIÓN HORARIO.
    """
    if horas_netas_dia is None:
        return ""
    h = float(horas_netas_dia)
    if h == 8.0:
        return "Jornada estándar"
    if 8.0 < h <= 12.0:
        return "Horas extra"
    if 7.0 <= h < 8.0:
        return "Por debajo mínimo"
    if 12.0 < h <= 16.0:
        return "Jornada excesiva"
    return "Fuera de rango"


# ---------------------------------------------------------------------------
# Public service: Excel generation (skill partes-trabajo v1.2 + col Q)
# Servicio público: generación Excel (skill partes-trabajo v1.2 + col Q)
# ---------------------------------------------------------------------------

def generate_work_order_excel(work_order_id: int) -> None:
    """
    Builds an Excel report conforming to the partes-trabajo skill v1.2
    specification, extended with column Q (COSTE M.O.) for labour cost
    imputation per work block.

    Structure:
      Row 1 — Title: PARTES DE TRABAJO — [OPERARIO] — [PERIOD]
      Row 2 — PRECIO HORA EXTRA (C2, yellow input cell)
      Row 3 — COSTE HORA ORDINARIA (C3, yellow input cell)
      Row 4 — Column headers (dark blue)
      Row 5+ — Data rows (one per WorkOrderEntryLine)
      Footer — MANIFIESTO DE INCIDENCIAS block (2 rows gap + header + rows)
    Second sheet: LEYENDA

    Saves the file to WorkOrder.excel_file and sets status to DONE.
    On failure sets status to ERROR and re-raises.

    ---

    Construye un informe Excel conforme a la especificación de la skill
    partes-trabajo v1.2, extendido con la columna Q (COSTE M.O.) para
    imputación de coste de mano de obra por bloque de trabajo.

    Estructura:
      Fila 1 — Título: PARTES DE TRABAJO — [OPERARIO] — [PERIODO]
      Fila 2 — PRECIO HORA EXTRA (C2, celda amarilla de entrada)
      Fila 3 — COSTE HORA ORDINARIA (C3, celda amarilla de entrada)
      Fila 4 — Cabeceras de columna (azul oscuro)
      Fila 5+ — Filas de datos (una por WorkOrderEntryLine)
      Pie    — Bloque MANIFIESTO DE INCIDENCIAS (2 filas separación + cabecera + filas)
    Segunda hoja: LEYENDA
    """
    work_order = WorkOrder.objects.get(pk=work_order_id)

    try:
        logger.info(
            "# Excel: iniciando generación (skill v1.2) para WorkOrder #%d.",
            work_order_id,
        )

        # ------------------------------------------------------------------
        # Gather data / Recopilar datos
        # ------------------------------------------------------------------
        entries = (
            work_order.entries
            .prefetch_related("lines__machine_asset")
            .order_by("page_number")
        )

        worker_name = ""
        if work_order.source_pdf:
            worker_name = _worker_name_from_pdf_path(work_order.source_pdf.name)

        # Build a flat list of row data grouped by day for HORAS NETAS DÍA.
        # Construir una lista plana de datos de fila agrupados por día para
        # HORAS NETAS DÍA.
        #
        # Structure: list of dicts, one per WorkOrderEntryLine, enriched with:
        #   - date_key      : date object (for day grouping)
        #   - is_first_day  : True for the first line of a new day
        #   - is_last_day   : True for the last line of a day (set in post-pass)
        #   - day_net_hours : Decimal total net hours for the day (set in post-pass)
        #   - fecha_incierta: bool from parent WorkOrderEntry

        flat_rows: list[dict] = []

        for entry in entries:
            lines = list(entry.lines.order_by("line_number"))
            if not lines:
                continue

            date_key = entry.work_date

            for line in lines:
                flat_rows.append({
                    "date_key":       date_key,
                    "fecha_incierta": entry.fecha_incierta,
                    "worker_name":    entry.worker_name or worker_name,
                    "line":           line,
                    "is_first_day":   False,
                    "is_last_day":    False,
                    "day_net_hours":  None,
                })

        # Post-pass: compute day groups, is_first_day, is_last_day,
        # day_net_hours.
        # Post-pasada: calcular grupos de día, is_first_day, is_last_day,
        # day_net_hours.
        if flat_rows:
            # Group indices by date_key.
            # Agrupar índices por date_key.
            from collections import defaultdict
            day_indices: dict = defaultdict(list)
            for idx, row in enumerate(flat_rows):
                day_indices[row["date_key"]].append(idx)

            for day_key, indices in day_indices.items():
                flat_rows[indices[0]]["is_first_day"] = True
                flat_rows[indices[-1]]["is_last_day"]  = True

                # Sum delta_horas for the day.
                # Sumar delta_horas del día.
                day_total = Decimal("0.00")
                all_valid = True
                for idx in indices:
                    dh = flat_rows[idx]["line"].delta_horas
                    if dh is not None:
                        day_total += dh
                    else:
                        all_valid = False

                day_net = day_total if all_valid or day_total > 0 else None
                for idx in indices:
                    flat_rows[idx]["day_net_hours"] = day_net

        # ------------------------------------------------------------------
        # Build workbook / Construir libro
        # ------------------------------------------------------------------
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Partes de Trabajo"

        num_data_cols = len(_COLS)

        # --- Row 1: Title / Fila 1: Título ---
        period = ""
        if flat_rows:
            dates = [r["date_key"] for r in flat_rows if r["date_key"]]
            if dates:
                d_min = min(dates).strftime("%d/%m/%Y")
                d_max = max(dates).strftime("%d/%m/%Y")
                period = f"{d_min} — {d_max}"

        title_val = f"PARTES DE TRABAJO — {worker_name} — {period}".strip(" —")
        ws.merge_cells(start_row=1, start_column=1,
                       end_row=1,   end_column=num_data_cols)
        title_cell       = ws.cell(row=1, column=1, value=title_val)
        title_cell.font  = Font(bold=True, size=13, color=_CLR_HEADER_BG)
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 22

        # --- Row 2: Precio hora extra / Fila 2: Precio hora extra ---
        ws.cell(row=2, column=1, value="PRECIO HORA EXTRA (euros/h):").fill = (
            _make_fill(_CLR_CONFIG_LABEL)
        )
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=2)
        c2_cell       = ws.cell(row=2, column=3)
        c2_cell.fill  = _make_fill(_CLR_CONFIG_INPUT)
        c2_cell.number_format = '#,##0.00 "€"'
        c2_cell.alignment = Alignment(horizontal="center")

        # --- Row 3: Coste hora ordinaria / Fila 3: Coste hora ordinaria ---
        ws.cell(row=3, column=1, value="COSTE HORA ORDINARIA (euros/h):").fill = (
            _make_fill(_CLR_CONFIG_LABEL)
        )
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=2)
        c3_cell       = ws.cell(row=3, column=3)
        c3_cell.fill  = _make_fill(_CLR_CONFIG_INPUT)
        c3_cell.number_format = '#,##0.00 "€"'
        c3_cell.alignment = Alignment(horizontal="center")

        # --- Row 4: Column headers / Fila 4: Cabeceras de columna ---
        hdr_font = Font(bold=True, color=_CLR_HEADER_FG)
        hdr_fill = _make_fill(_CLR_HEADER_BG)
        hdr_aln  = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for col_idx, (hdr, width) in enumerate(_COLS, start=1):
            cell           = ws.cell(row=4, column=col_idx, value=hdr)
            cell.font      = hdr_font
            cell.fill      = hdr_fill
            cell.alignment = hdr_aln
            cell.border    = _make_border_thin()
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        ws.row_dimensions[4].height = 30

        # --- Data rows / Filas de datos ---
        incidences: list[dict] = []   # Accumulated for the manifest.

        for row_offset, row_data in enumerate(flat_rows):
            r          = _DATA_ROW_START + row_offset
            line: WorkOrderEntryLine = row_data["line"]
            date_key   = row_data["date_key"]
            is_first   = row_data["is_first_day"]
            is_last    = row_data["is_last_day"]
            day_net    = row_data["day_net_hours"]
            fecha_inc  = row_data["fecha_incierta"]

            # Col A — FECHA (first entry of day only)
            # Col A — FECHA (solo primera entrada del día)
            if is_first:
                date_str = (
                    date_key.strftime("%d/%m/%Y") if date_key else "SIN FECHA"
                )
                a_cell        = ws.cell(row=r, column=1, value=date_str)
                a_cell.fill   = _make_fill(
                    _CLR_DATE_UNCERT if fecha_inc else _CLR_DATE_FIRST
                )
                a_cell.alignment = Alignment(horizontal="center", vertical="center")
                a_cell.border = _make_border_thin()

                # Incidencia de fecha — solo una vez por día (D1).
                # Date incidence — only once per day (D1).
                if fecha_inc and date_key:
                    incidences.append({
                        "fecha": date_str,
                        "tramo": f"{line.hc.strftime('%H:%M') if line.hc else '?'}–"
                                 f"{line.hf.strftime('%H:%M') if line.hf else '?'}",
                        "campo": "FECHA",
                        "descripcion": "Fecha incierta — verificar manuscrito original.",
                    })
            else:
                ws.cell(row=r, column=1).border = _make_border_thin()

            # Col B — OPERARIO
            ws.cell(row=r, column=2,
                    value=row_data["worker_name"]).border = _make_border_thin()

            # Col C — CÓDIGO / VEH.
            codigo_val  = line.maquina_norm or line.maquina_raw or ""
            c_cell      = ws.cell(row=r, column=3, value=codigo_val)
            c_cell.border = _make_border_thin()
            if not codigo_val:
                c_cell.fill = _make_fill(_CLR_MACHINE_EMPT)
            elif not line.machine_asset:
                c_cell.fill = _make_fill(_CLR_MACHINE_UNKN)
                incidences.append({
                    "fecha": date_key.strftime("%d/%m/%Y") if date_key else "SIN FECHA",
                    "tramo": f"{line.hc.strftime('%H:%M') if line.hc else '?'}–"
                             f"{line.hf.strftime('%H:%M') if line.hf else '?'}",
                    "campo": "MAQUINA",
                    "descripcion": (
                        f"Código '{codigo_val}' no encontrado en catálogo "
                        "tras normalización D4."
                    ),
                })

            # Col D — MARCA / MODELO
            marca_val = (
                line.machine_asset.marca_modelo if line.machine_asset else ""
            )
            ws.cell(row=r, column=4,
                    value=marca_val).border = _make_border_thin()

            # Col E — KM (from MachineAsset catalogue snapshot)
            # Col E — KM (del snapshot del catálogo MachineAsset)
            kms_val = line.machine_asset.kms if line.machine_asset else ""
            ws.cell(row=r, column=5,
                    value=kms_val).border = _make_border_thin()

            # Col F — HORAS VEH.
            horas_val = line.machine_asset.horas if line.machine_asset else ""
            ws.cell(row=r, column=6,
                    value=horas_val).border = _make_border_thin()

            # Col G — DESCRIPCIÓN AVERÍA
            g_cell = ws.cell(row=r, column=7,
                             value=line.descripcion_averia or "")
            g_cell.alignment = Alignment(wrap_text=True, vertical="top")
            g_cell.border    = _make_border_thin()
            if "DESCRIPCION" in (line.flags or []):
                incidences.append({
                    "fecha": date_key.strftime("%d/%m/%Y") if date_key else "SIN FECHA",
                    "tramo": f"{line.hc.strftime('%H:%M') if line.hc else '?'}–"
                             f"{line.hf.strftime('%H:%M') if line.hf else '?'}",
                    "campo": "DESCRIPCIÓN",
                    "descripcion": "Descripción de difícil lectura — verificar manuscrito.",
                })

            # Col H — REPARACIÓN
            h_cell = ws.cell(row=r, column=8, value=line.reparacion or "")
            h_cell.alignment = Alignment(wrap_text=True, vertical="top")
            h_cell.border    = _make_border_thin()

            # Col I — H.C.
            hc_str  = line.hc.strftime("%H:%M") if line.hc else ""
            i_cell  = ws.cell(row=r, column=9, value=hc_str)
            i_cell.alignment = Alignment(horizontal="center")
            i_cell.border    = _make_border_thin()
            if "H.C." in (line.flags or []):
                incidences.append({
                    "fecha": date_key.strftime("%d/%m/%Y") if date_key else "SIN FECHA",
                    "tramo": f"{hc_str or '?'}–{line.hf.strftime('%H:%M') if line.hf else '?'}",
                    "campo": "H.C.",
                    "descripcion": "H.C. de difícil lectura — verificar manuscrito.",
                })

            # Col J — H.F.
            hf_str  = line.hf.strftime("%H:%M") if line.hf else ""
            j_cell  = ws.cell(row=r, column=10, value=hf_str)
            j_cell.alignment = Alignment(horizontal="center")
            j_cell.border    = _make_border_thin()
            if "H.F." in (line.flags or []):
                incidences.append({
                    "fecha": date_key.strftime("%d/%m/%Y") if date_key else "SIN FECHA",
                    "tramo": f"{hc_str or '?'}–{hf_str or '?'}",
                    "campo": "H.F.",
                    "descripcion": "H.F. de difícil lectura — verificar manuscrito.",
                })

            # Horario inválido: HF <= HC / Invalid schedule: HF <= HC
            if line.hc and line.hf and line.hf <= line.hc:
                incidences.append({
                    "fecha": date_key.strftime("%d/%m/%Y") if date_key else "SIN FECHA",
                    "tramo": f"{hc_str}–{hf_str}",
                    "campo": "HORARIO",
                    "descripcion": "H.F. igual o anterior a H.C. — horario inválido.",
                })

            # Col K — O.R.
            ws.cell(row=r, column=11,
                    value=line.or_val or "").border = _make_border_thin()

            # Col L — Δ HORAS (neta)
            l_cell = ws.cell(
                row=r, column=12,
                value=float(line.delta_horas) if line.delta_horas is not None else "",
            )
            l_cell.number_format = '0.00" h"'
            l_cell.alignment     = Alignment(horizontal="center")
            l_cell.border        = _make_border_thin()

            # Col M — HORAS NETAS DÍA (last entry of day only)
            # Col M — HORAS NETAS DÍA (solo última entrada del día)
            if is_last and day_net is not None:
                m_cell = ws.cell(row=r, column=13, value=float(day_net))
                m_cell.number_format = '0.00" h"'
                m_cell.alignment     = Alignment(horizontal="center")
                m_cell.border        = _make_border_thin()
                m_cell.font          = Font(bold=True)

                # Incidencia D5: jornada < 8h / D5 incidence: shift < 8h
                if day_net < Decimal("8.00") and date_key:
                    incidences.append({
                        "fecha": date_key.strftime("%d/%m/%Y"),
                        "tramo": f"{hc_str or '?'}–{hf_str or '?'}",
                        "campo": "JORNADA",
                        "descripcion": (
                            f"Jornada diaria neta ({float(day_net):.2f} h) inferior "
                            "a 8 h — verificar con el operario."
                        ),
                    })
            else:
                ws.cell(row=r, column=13).border = _make_border_thin()

            # Col N — HORAS EXTRAS (formula, last entry only)
            # Col N — HORAS EXTRAS (fórmula, solo última entrada)
            if is_last and day_net is not None:
                n_cell = ws.cell(
                    row=r, column=14,
                    value=f"=IF(M{r}=\"\",\"\",M{r}-8)",
                )
                n_cell.number_format = '0.00" h"'
                n_cell.alignment     = Alignment(horizontal="center")
                n_cell.border        = _make_border_thin()
                # Red font if negative / Fuente roja si negativo (lo gestiona
                # el usuario vía formato condicional manual — aquí dejamos base).
            else:
                ws.cell(row=r, column=14).border = _make_border_thin()

            # Col O — SALARIO EXTRAS (formula, last entry only)
            # Col O — SALARIO EXTRAS (fórmula, solo última entrada)
            if is_last and day_net is not None:
                o_cell = ws.cell(
                    row=r, column=15,
                    value=f"=IF(N{r}=\"\",\"\",N{r}*$C$2)",
                )
                o_cell.number_format = '#,##0.00 "€"'
                o_cell.alignment     = Alignment(horizontal="center")
                o_cell.border        = _make_border_thin()
            else:
                ws.cell(row=r, column=15).border = _make_border_thin()

            # Col P — REVISIÓN HORARIO (last entry only)
            # Col P — REVISIÓN HORARIO (solo última entrada)
            if is_last:
                p_cell = ws.cell(
                    row=r, column=16,
                    value=_revision_text(day_net),
                )
                p_cell.fill      = _make_fill(_revision_color(day_net))
                p_cell.alignment = Alignment(horizontal="center", vertical="center")
                p_cell.border    = _make_border_thin()
                p_cell.font      = Font(bold=True)
            else:
                ws.cell(row=r, column=16).border = _make_border_thin()

            # Col Q — COSTE M.O. (formula: delta_horas * $C$3)
            # Col Q — COSTE M.O. (fórmula: delta_horas * $C$3)
            if line.delta_horas is not None:
                q_cell = ws.cell(
                    row=r, column=17,
                    value=f"=IF($C$3=\"\",\"\",L{r}*$C$3)",
                )
                q_cell.number_format = '#,##0.00 "€"'
                q_cell.alignment     = Alignment(horizontal="center")
                q_cell.border        = _make_border_thin()
            else:
                ws.cell(row=r, column=17).border = _make_border_thin()

        # --- Freeze panes / Fijar paneles ---
        ws.freeze_panes = f"A{_DATA_ROW_START}"

        # ------------------------------------------------------------------
        # MANIFIESTO DE INCIDENCIAS / INCIDENCE MANIFEST
        # ------------------------------------------------------------------
        last_data_row  = _DATA_ROW_START + len(flat_rows) - 1
        manifest_start = last_data_row + 3   # 2 blank rows gap + header

        # Manifest header / Cabecera del manifiesto
        ws.merge_cells(
            start_row=manifest_start, start_column=1,
            end_row=manifest_start,   end_column=5,
        )
        mhdr = ws.cell(row=manifest_start, column=1,
                       value="MANIFIESTO DE INCIDENCIAS")
        mhdr.font      = Font(bold=True, color=_CLR_MANIFEST_FG, size=11)
        mhdr.fill      = _make_fill(_CLR_MANIFEST_BG)
        mhdr.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[manifest_start].height = 20

        manifest_col_headers = ["#", "FECHA", "TRAMO", "CAMPO",
                                 "DESCRIPCIÓN DE LA INCIDENCIA"]
        manifest_col_widths  = [5, 14, 16, 16, 60]
        for ci, (ch, cw) in enumerate(
            zip(manifest_col_headers, manifest_col_widths), start=1
        ):
            cell           = ws.cell(row=manifest_start + 1, column=ci, value=ch)
            cell.font      = Font(bold=True, color=_CLR_MANIFEST_FG)
            cell.fill      = _make_fill(_CLR_MANIFEST_BG)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border    = _make_border_thin()

        for inc_idx, inc in enumerate(incidences, start=1):
            inc_row = manifest_start + 1 + inc_idx
            ws.cell(row=inc_row, column=1, value=inc_idx).border = _make_border_thin()
            ws.cell(row=inc_row, column=2,
                    value=inc["fecha"]).border   = _make_border_thin()
            ws.cell(row=inc_row, column=3,
                    value=inc["tramo"]).border   = _make_border_thin()
            ws.cell(row=inc_row, column=4,
                    value=inc["campo"]).border   = _make_border_thin()
            desc_cell = ws.cell(row=inc_row, column=5, value=inc["descripcion"])
            desc_cell.alignment = Alignment(wrap_text=True, vertical="top")
            desc_cell.border    = _make_border_thin()

        if not incidences:
            no_inc = ws.cell(
                row=manifest_start + 2, column=1,
                value="Sin incidencias registradas.",
            )
            no_inc.font = Font(italic=True)

        # ------------------------------------------------------------------
        # LEYENDA sheet / Hoja LEYENDA
        # ------------------------------------------------------------------
        ws_ley        = wb.create_sheet(title="LEYENDA")
        ley_title     = ws_ley.cell(row=1, column=1, value="LEYENDA — REVISIÓN HORARIO")
        ley_title.font = Font(bold=True, size=12, color=_CLR_HEADER_BG)
        ws_ley.merge_cells("A1:C1")
        ws_ley.row_dimensions[1].height = 20

        leyenda_rows = [
            (_CLR_REV_GREEN,  "= 8 h",      "Jornada estándar"),
            (_CLR_REV_BLUE,   "8 h – 12 h", "Horas extraordinarias"),
            (_CLR_REV_YELLOW, "7 h – 8 h",  "Por debajo del mínimo"),
            (_CLR_REV_ORANGE, "12 h – 16 h","Jornada excesiva — revisar"),
            (_CLR_REV_RED,    "< 7 h ó > 16 h", "Fuera de rango — error probable"),
        ]
        for ley_idx, (color, rango, significado) in enumerate(leyenda_rows, start=2):
            color_cell           = ws_ley.cell(row=ley_idx, column=1, value="")
            color_cell.fill      = _make_fill(color)
            color_cell.border    = _make_border_thin()
            ws_ley.cell(row=ley_idx, column=2,
                        value=rango).border      = _make_border_thin()
            ws_ley.cell(row=ley_idx, column=3,
                        value=significado).border = _make_border_thin()

        ws_ley.column_dimensions["A"].width = 6
        ws_ley.column_dimensions["B"].width = 16
        ws_ley.column_dimensions["C"].width = 40

        # ------------------------------------------------------------------
        # Persist / Persistir
        # ------------------------------------------------------------------
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        filename = (
            f"partes_{worker_name.replace(' ', '_').lower()}_"
            f"{work_order_id}_"
            f"{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        work_order.excel_file.save(filename, ContentFile(buffer.read()), save=False)
        work_order.status = WorkOrder.Status.DONE
        work_order.save(update_fields=["excel_file", "status"])

        logger.info(
            "# Excel: informe generado correctamente para WorkOrder #%d → %s.",
            work_order_id,
            filename,
        )

    except Exception as exc:
        logger.error(
            "# Error crítico en generate_work_order_excel para WorkOrder #%d: %s",
            work_order_id,
            exc,
            exc_info=True,
        )
        work_order.status    = WorkOrder.Status.ERROR
        work_order.error_log = f"Error en generación de Excel: {exc}"
        work_order.save(update_fields=["status", "error_log"])
        raise
