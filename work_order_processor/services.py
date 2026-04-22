# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/services.py

"""
Business logic services for the work_order_processor application.
Contains two primary services:
  - extract_work_order_page(): sends a rasterized PDF page to Gemini Vision
    and returns structured extracted data as a Python dict.
  - generate_work_order_excel(): builds an Excel report from all WorkOrderEntry
    records linked to a WorkOrder and persists the file to WorkOrder.excel_file.

---

Servicios de lógica de negocio para la aplicación work_order_processor.
Contiene dos servicios principales:
  - extract_work_order_page(): envía una página del PDF rasterizada a Gemini
    Vision y devuelve los datos extraídos estructurados como dict de Python.
  - generate_work_order_excel(): construye un informe Excel a partir de todos
    los registros WorkOrderEntry vinculados a un WorkOrder y persiste el archivo
    en WorkOrder.excel_file.
"""

import io
import json
import logging
import os
import re
from datetime import date, time
from typing import Any

import fitz  # PyMuPDF
import openpyxl
from django.core.files.base import ContentFile
from django.utils import timezone
from google import genai
from google.genai.types import HttpOptions, Part

from .models import WorkOrder, WorkOrderEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini client initialisation (Vertex AI — Directriz 4.1)
# Inicialización del cliente Gemini (Vertex AI — Directriz 4.1)
# ---------------------------------------------------------------------------
_GEMINI_MODEL   = "gemini-2.5-flash"
_GEMINI_CLIENT  = None   # Lazy singleton — inicializado en primera llamada.


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
        # Vertex AI picks up credentials from the environment variable set by
        # the Django settings / dotenv loader.
        # Vertex AI recoge las credenciales de la variable de entorno cargada
        # por el settings / dotenv de Django.
        os.environ.setdefault(
            "GOOGLE_APPLICATION_CREDENTIALS",
            os.environ.get("GCP_CREDENTIALS_PATH", ""),
        )
        _GEMINI_CLIENT = genai.Client(
            http_options=HttpOptions(api_version="v1"),
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION"),
        )
        logger.info("# Cliente Gemini Vision inicializado correctamente (Vertex AI).")
    return _GEMINI_CLIENT


# ---------------------------------------------------------------------------
# Extraction prompt / Prompt de extracción
# ---------------------------------------------------------------------------
# The prompt requests a strict JSON response with the exact keys defined in
# section 2.3 of annex V06, incorporating the contextual directives D6, D7
# and D8 from the partes-trabajo skill.
# El prompt solicita una respuesta JSON estricta con las claves exactas
# definidas en la sección 2.3 del anexo V06, incorporando las directrices
# contextuales D6, D7 y D8 de la skill partes-trabajo.

_EXTRACTION_PROMPT = """\
Eres un asistente especializado en la extracción de datos de partes de trabajo
manuscritos de una empresa de grúas y maquinaria industrial (grúas móviles,
plataformas elevadoras, autocargantes, cabezas tractoras, semirremolques,
carretillas elevadoras). Las averías y reparaciones descritas en los partes
pertenecen siempre a este tipo de vehículos y maquinaria pesada industrial.

Analiza la imagen del parte de trabajo manuscrito y extrae los campos indicados.

REGLAS OBLIGATORIAS:
1. Responde ÚNICAMENTE con un objeto JSON válido. Sin texto adicional, sin
   bloques de código markdown, sin explicaciones.
2. Si un campo no es legible o no aparece en el parte, usa null.
3. Fechas en formato ISO 8601: "YYYY-MM-DD". Horas en formato "HH:MM".
4. Los horarios se ajustan SIEMPRE a fracciones de media hora (:00 o :30).
   Si lees 09:20, devuelve "09:30". Si lees 07:10, devuelve "07:00".
5. El campo vehicle_ref puede ser un código de máquina (ej: A36, T14, Z45),
   una matrícula o un alias coloquial. Si aparece la palabra "Larios" en el
   contexto de la referencia de vehículo o en la descripción, inclúyela en
   vehicle_ref tal como aparece — es un alias reconocido de empresa.
6. Para work_description y observations, interpreta abreviaturas técnicas en
   el contexto de vehículos pesados industriales (ej: "hid." → hidráulico,
   "trans." → transmisión, "dir." → dirección, "mto." → mantenimiento).
7. El campo extraction_confidence debe ser tu evaluación global de la calidad
   de la extracción: "HIGH" si todos los campos principales son legibles,
   "MEDIUM" si hay alguna duda menor, "LOW" si hay campos importantes ilegibles,
   "FAILED" si la imagen no corresponde a un parte de trabajo o es ilegible.

Formato de respuesta (claves exactas, sin modificar):
{
    "worker_name":           "<nombre completo del operario o null>",
    "work_date":             "<YYYY-MM-DD o null>",
    "start_time":            "<HH:MM o null>",
    "end_time":              "<HH:MM o null>",
    "vehicle_ref":           "<referencia de vehículo o null>",
    "work_description":      "<descripción de trabajos realizados o null>",
    "location":              "<lugar o dirección de la intervención o null>",
    "observations":          "<observaciones adicionales del operario o null>",
    "extraction_confidence": "<HIGH | MEDIUM | LOW | FAILED>"
}
"""

# ---------------------------------------------------------------------------
# Public service: page extraction
# Servicio público: extracción de página
# ---------------------------------------------------------------------------

def extract_work_order_page(image_bytes: bytes) -> dict[str, Any]:
    """
    Sends a rasterized PDF page (PNG bytes) to Gemini Vision and returns
    the structured extracted fields as a Python dict.

    The function applies tolerant JSON parsing: strips markdown fences if
    present and attempts to locate the JSON object within the response text
    in case the model includes any surrounding prose despite instructions.

    Returns a dict with the keys defined in _EXTRACTION_PROMPT. On total
    failure, returns a dict with all fields set to None and
    extraction_confidence = "FAILED".

    ---

    Envía una página del PDF rasterizada (bytes PNG) a Gemini Vision y
    devuelve los campos extraídos estructurados como dict de Python.

    La función aplica un parseo JSON tolerante: elimina bloques markdown si
    los hubiera e intenta localizar el objeto JSON dentro del texto de respuesta
    en caso de que el modelo incluya texto adicional a pesar de las instrucciones.

    Devuelve un dict con las claves definidas en _EXTRACTION_PROMPT. En caso de
    fallo total, devuelve un dict con todos los campos a None y
    extraction_confidence = "FAILED".
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

        # Tolerant JSON extraction / Extracción JSON tolerante.
        # Strip markdown fences if present.
        # Eliminar bloques markdown si están presentes.
        cleaned = re.sub(r"```(?:json)?|```", "", raw_text).strip()

        # Locate the outermost JSON object in case of surrounding prose.
        # Localizar el objeto JSON más externo en caso de prosa circundante.
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(
                f"No se encontró ningún objeto JSON en la respuesta de Gemini: {raw_text[:200]}"
            )

        extracted: dict[str, Any] = json.loads(match.group())
        logger.info(
            "# Gemini Vision: extracción completada. Confianza: %s",
            extracted.get("extraction_confidence", "DESCONOCIDA"),
        )
        return extracted

    except Exception as exc:
        logger.error(
            "# Error crítico en extract_work_order_page: %s", exc, exc_info=True
        )
        return {
            "worker_name":           None,
            "work_date":             None,
            "start_time":            None,
            "end_time":              None,
            "vehicle_ref":           None,
            "work_description":      None,
            "location":              None,
            "observations":          None,
            "extraction_confidence": "FAILED",
        }


# ---------------------------------------------------------------------------
# Helper: safe field coercion
# Helper: coerción segura de campos
# ---------------------------------------------------------------------------

def _parse_date(value: str | None) -> date | None:
    """
    Parses a date string in ISO 8601 format (YYYY-MM-DD) into a Python date.
    Returns None if value is None, empty or unparseable.

    ---

    Parsea una cadena de fecha en formato ISO 8601 (YYYY-MM-DD) a un objeto
    date de Python. Devuelve None si el valor es None, vacío o no parseable.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
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


# ---------------------------------------------------------------------------
# Public service: Excel generation
# Servicio público: generación de Excel
# ---------------------------------------------------------------------------

# Excel column headers in Spanish, one per WorkOrderEntry field.
# Cabeceras de columnas del Excel en castellano, una por campo de WorkOrderEntry.
_EXCEL_HEADERS = [
    "Nº Página",
    "Nombre Operario",
    "Fecha",
    "H. Inicio",
    "H. Fin",
    "Ref. Vehículo",
    "Descripción Trabajos",
    "Lugar",
    "Observaciones",
    "Confianza Extracción",
    "Fecha Extracción",
]

# Column widths (characters) aligned to header content.
# Anchuras de columna (caracteres) alineadas al contenido de la cabecera.
_EXCEL_COL_WIDTHS = [10, 30, 14, 10, 10, 18, 50, 30, 40, 20, 20]


def generate_work_order_excel(work_order_id: int) -> None:
    """
    Builds an Excel report from all WorkOrderEntry records associated with
    the given WorkOrder and saves the file to WorkOrder.excel_file.
    Updates WorkOrder.status to DONE on success or ERROR on failure.

    The report contains one row per WorkOrderEntry, with Spanish column
    headers. The extraction date column records the moment of report
    generation (timezone-aware, Europe/Madrid).

    ---

    Construye un informe Excel a partir de todos los registros WorkOrderEntry
    asociados al WorkOrder indicado y guarda el archivo en WorkOrder.excel_file.
    Actualiza WorkOrder.status a DONE en caso de éxito o ERROR en caso de fallo.

    El informe contiene una fila por WorkOrderEntry, con cabeceras de columna
    en castellano. La columna de fecha de extracción registra el momento de
    generación del informe (timezone-aware, Europe/Madrid).
    """
    work_order = WorkOrder.objects.get(pk=work_order_id)

    try:
        logger.info(
            "# Excel: iniciando generación para WorkOrder #%d.", work_order_id
        )
        entries = work_order.entries.order_by("page_number")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Partes de Trabajo"

        # --- Header row / Fila de cabecera ---
        header_font = openpyxl.styles.Font(bold=True)
        header_fill = openpyxl.styles.PatternFill(
            fill_type="solid", fgColor="1F4E79"
        )
        header_font_color = openpyxl.styles.Font(bold=True, color="FFFFFF")

        for col_idx, (header, width) in enumerate(
            zip(_EXCEL_HEADERS, _EXCEL_COL_WIDTHS), start=1
        ):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font           = header_font_color
            cell.fill           = header_fill
            cell.alignment      = openpyxl.styles.Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )
            ws.column_dimensions[
                openpyxl.utils.get_column_letter(col_idx)
            ].width = width

        ws.row_dimensions[1].height = 30

        # --- Data rows / Filas de datos ---
        extraction_ts = timezone.now().strftime("%d/%m/%Y %H:%M")

        for row_idx, entry in enumerate(entries, start=2):
            ws.cell(row=row_idx, column=1,  value=entry.page_number)
            ws.cell(row=row_idx, column=2,  value=entry.worker_name or "")
            ws.cell(
                row=row_idx, column=3,
                value=(
                    entry.work_date.strftime("%d/%m/%Y")
                    if entry.work_date else ""
                ),
            )
            ws.cell(
                row=row_idx, column=4,
                value=(
                    entry.start_time.strftime("%H:%M")
                    if entry.start_time else ""
                ),
            )
            ws.cell(
                row=row_idx, column=5,
                value=(
                    entry.end_time.strftime("%H:%M")
                    if entry.end_time else ""
                ),
            )
            ws.cell(row=row_idx, column=6,  value=entry.vehicle_ref or "")
            ws.cell(row=row_idx, column=7,  value=entry.work_description or "")
            ws.cell(row=row_idx, column=8,  value=entry.location or "")
            ws.cell(row=row_idx, column=9,  value=entry.observations or "")
            ws.cell(row=row_idx, column=10, value=entry.get_extraction_confidence_display())
            ws.cell(row=row_idx, column=11, value=extraction_ts)

            # Wrap text in long-content columns.
            # Ajuste de texto en columnas de contenido largo.
            for col in (7, 8, 9):
                ws.cell(row=row_idx, column=col).alignment = (
                    openpyxl.styles.Alignment(wrap_text=True, vertical="top")
                )

        # --- Freeze header row / Fijar fila de cabecera ---
        ws.freeze_panes = "A2"

        # --- Persist to WorkOrder.excel_file ---
        # --- Persistir en WorkOrder.excel_file ---
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        filename = f"partes_trabajo_{work_order_id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
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
