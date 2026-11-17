# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/logbook_service.py
"""
H23 (S154, invasora) -- libro historial de las grúas móviles (A y H).

Miguel Ángel (S154): el libro se saca "de los escaneos que ya hay junto
con las partes digitales que tenemos, tanto los que llegaron por el
histórico en PDF como los realizados a través del formulario"; las
reparaciones, "el mismo criterio que se siga en los propios libros de
historial"; los datos de la grúa, "campos nuevos en la ficha de la
máquina"; y "cada libro generado se guarda como documento el libro
historial de esa máquina".

Modelo de libro: el impreso que ya usa la empresa (libro de grúa móvil
autopropulsada adaptado al RD 837/2003, ITC MIE-AEM 4), con sus
secciones: 1.1 identificación, 1.2 pesos y dimensiones, 1.3
titularidad, 2.1/2.2 inspecciones oficiales de la base y de la
estructura, 3 revisiones técnicas periódicas, 4 piezas sustituidas o
reparaciones realizadas, 5 accidentes y 6 notas.

- Escaneos: cada documento LIBRO_HISTORIAL de una grúa A/H se lee una
  sola vez con Gemini (`read_scan`/`store_scan`); sus filas quedan en
  `MachineLogbookEntry` y sus datos de identificación rellenan los
  campos vacíos de la ficha (nunca pisan uno ya escrito).
- Partes digitales: la sección 4 añade en vivo las tareas de los partes
  (`WorkOrderEntryLine`, tanto las del histórico en PDF como las del
  formulario) que cumplen el criterio del propio libro: "Motores ·
  Mecanismos o componentes hidráulicos · Elementos estructurales".
- El libro generado (`generate_logbook`) se guarda en el cubo como
  documento LIBRO_HISTORIAL de la máquina por la subida de siempre
  (`subject_upload_service`) y se marca GENERATED para no leerlo nunca
  como escaneo.

---

H23 (S154) -- crane logbook of mobile cranes (A and H codes): scanned
logbooks read once with Gemini, plus live repairs from the digital
work orders, rendered to PDF and stored as the machine's LIBRO_HISTORIAL
document.
"""
import json
import logging
import re
import unicodedata

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from fleet.models import (
    MachineAsset, MachineLogbookEntry, MachineLogbookSource,
)

logger = logging.getLogger(__name__)

LOGBOOK_TYPE_CODE = "LIBRO_HISTORIAL"

# Criterio del propio libro (sección 4, "Piezas sustituidas o
# reparaciones realizadas": motores, mecanismos o componentes
# hidráulicos, elementos estructurales), traducido a la clasificación
# de averías de los partes (work_order_processor.FaultCategory).
REPAIR_FAULT_CATEGORIES = ("HYDRAULIC", "LIFTING_STRUCTURE")
REPAIR_FAULT_SUBCATEGORIES = ("ET_ENGINE", "BC_CHASSIS")
REPAIR_TASK_TYPES = ("AVERIA", "")

# Revisiones técnicas periódicas: cada seis meses (lo que se ve en los
# libros escaneados); un hueco se avisa pasado un mes de margen.
REVIEW_INTERVAL_DAYS = 183
REVIEW_GRACE_DAYS = 31
# Quién firma revisiones como responsable (S154, Miguel Ángel: "firmadas
# por Alberto Álvarez Díaz", jefe de taller): jefe de taller y
# administrador.
SIGN_ROLES = {"WORKSHOPBOSS", "ADMIN"}

# Gemini 3.5 Flash (ficha del modelo en Vertex AI, consultada en S154):
# 7 MB por archivo en línea y 65.536 tokens de salida como máximo. Un
# PDF mayor, o cuya respuesta no sale entera, se lee página a página.
MAX_INLINE_BYTES = 7 * 1024 * 1024
MAX_OUTPUT_TOKENS = 65_536
READABLE_TYPES = ("application/pdf", "image/png", "image/jpeg",
                  "image/webp")
GEMINI_TIMEOUT_MS = 180_000

SECTION_CODES = [code for code, _label in MachineLogbookEntry.SECTION_CHOICES]

_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "identification": {
            "type": "object",
            "properties": {
                "brand": {"type": "string"},
                "model": {"type": "string"},
                "serial_number": {"type": "string"},
                "manufacture_year": {"type": "string"},
                "plate": {"type": "string"},
                "chassis_number": {"type": "string"},
                "max_capacity": {"type": "string"},
                "length_mm": {"type": "string"},
                "width_mm": {"type": "string"},
                "height_mm": {"type": "string"},
                "mass_kg": {"type": "string"},
                "axle_count": {"type": "string"},
                "axle_mass": {"type": "string"},
                "first_owner_name": {"type": "string"},
                "first_owner_tax_id": {"type": "string"},
                "first_owner_address": {"type": "string"},
                "first_owner_city": {"type": "string"},
            },
            "required": [
                "brand", "model", "serial_number", "manufacture_year",
                "plate", "chassis_number", "max_capacity", "length_mm",
                "width_mm", "height_mm", "mass_kg", "axle_count",
                "axle_mass", "first_owner_name", "first_owner_tax_id",
                "first_owner_address", "first_owner_city",
            ],
        },
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "enum": SECTION_CODES},
                    "date": {"type": "string"},
                    "type": {"type": "string"},
                    "concept": {"type": "string"},
                    "entity": {"type": "string"},
                    "result": {"type": "string"},
                    "next_date": {"type": "string"},
                },
                "required": [
                    "section", "date", "type", "concept", "entity",
                    "result", "next_date",
                ],
            },
        },
    },
    "required": ["identification", "rows"],
}

_READ_PROMPT = """Eres un lector de libros historiales de grúas móviles \
autopropulsadas (impreso adaptado al Real Decreto 837/2003, ITC MIE-AEM 4).
Te paso páginas escaneadas del libro de la grúa {code}, rellenadas a mano,
con sellos y firmas. Transcribe SOLO lo que esté escrito; nunca inventes.

1. "identification": datos de las páginas "Identificación de la grúa",
   "Pesos y dimensiones" y "Titularidad inicial". Cadena vacía si la página
   no aparece o el campo está en blanco. Longitud, anchura y altura en
   milímetros como número entero (un "10.789" o "10,789" de longitud es
   10789 mm); masa en kilogramos como número entero; año de fabricación
   con 4 cifras; número de ejes como número entero. Capacidad máxima y masa
   por eje, tal como estén escritas.
2. "rows": una fila por cada fila RELLENA de las tablas (las filas en
   blanco no se devuelven), con "section":
   - INSPECTION_BASE: "Inspecciones oficiales de la base".
   - INSPECTION_STRUCTURE: "Inspecciones oficiales de la estructura".
   - PERIODIC_REVIEW: "Revisiones técnicas periódicas".
   - REPAIR: "Piezas sustituidas o reparaciones realizadas".
   - ACCIDENT: "Accidentes".
   - NOTE: "Notas".
   - OWNERSHIP: "Cambios de titularidad" (entity = nuevo propietario,
     concept = NIF, domicilio y población).
   Campos: "date" fecha de la fila (AAAA-MM-DD); "type" tipo de
   inspección (p. ej. "Periódica tipo II"); "concept" concepto o
   descripción (p. ej. "Próxima revisión 22/10/2024"); "entity" entidad
   inspectora (OCA) o empresa mantenedora tal como figure en el sello o la
   letra; "result" resultado (p. ej. "Favorable según normas del
   fabricante"); "next_date" próxima revisión (AAAA-MM-DD) si figura, en
   las revisiones técnicas también la del concepto "Próxima revisión".
   Fechas escritas a mano en día/mes/año (formato español); año de dos
   cifras = 20AA. Si una fecha no se lee con seguridad, cadena vacía.
Si el documento no es un libro historial de grúa, devuelve identification
con cadenas vacías y rows vacío."""


class LogbookReadError(Exception):
    pass


def is_logbook_machine(machine) -> bool:
    """
    Whether this cost centre carries the crane logbook (A and H codes).

    ---

    Si este centro de gasto lleva libro historial de grúa: de momento
    solo las grúas móviles A y H (Miguel Ángel, S154).
    """
    return machine.is_logbook_crane


def _machine_content_type():
    return ContentType.objects.get_for_model(MachineAsset)


def scan_documents(machine=None):
    """
    Live LIBRO_HISTORIAL documents of A/H cranes that are scans.

    ---

    Documentos LIBRO_HISTORIAL vivos de grúas A/H que son escaneos (los
    generados por la plataforma quedan fuera), con su máquina.
    Devuelve una lista de (entry, machine).
    """
    from document_explorer.models import DocumentIndexEntry

    entries = DocumentIndexEntry.objects.filter(
        document_type__code=LOGBOOK_TYPE_CODE,
        domain_content_type=_machine_content_type(),
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True,
        purged_at__isnull=True,
        is_confidential=False,
    ).exclude(
        logbook_source__kind=MachineLogbookSource.KIND_GENERATED,
    ).order_by("domain_object_id", "id")
    if machine is not None:
        entries = entries.filter(domain_object_id=machine.pk)
    machines = MachineAsset.objects.in_bulk(
        {entry.domain_object_id for entry in entries}
    )
    result = []
    for entry in entries:
        found = machines.get(entry.domain_object_id)
        if found is not None and is_logbook_machine(found):
            result.append((entry, found))
    return result


def _ask_gemini(data, mime, machine) -> dict:
    """
    One Gemini call over one file or page; raises on invalid JSON.

    ---

    Una llamada a Gemini sobre un archivo o una página. Lanza
    LogbookReadError si la respuesta no es JSON válido, con el motivo
    de fin de Gemini (p. ej. MAX_TOKENS) para saber por qué.
    """
    from google.genai.types import (
        GenerateContentConfig, HttpOptions, Part, ThinkingConfig,
    )

    from ai_services.document_vision_service import (
        _generate_content_with_retry,
    )
    from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client

    response = _generate_content_with_retry(
        get_gemini_client(),
        model=DEFAULT_MODEL,
        contents=[
            Part.from_bytes(data=data, mime_type=mime),
            _READ_PROMPT.format(code=machine.code),
        ],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=GEMINI_TIMEOUT_MS),
            response_mime_type="application/json",
            response_schema=_READ_SCHEMA,
            thinking_config=ThinkingConfig(thinking_level="low"),
            temperature=0.0,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    try:
        return json.loads(response.text.strip())
    except (ValueError, AttributeError) as exc:
        reason = ""
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            reason = str(getattr(candidates[0], "finish_reason", "") or "")
        raise LogbookReadError(
            "Respuesta de Gemini no válida%s." % (
                " (fin: %s)" % reason if reason else ""
            )
        ) from exc


def _pdf_pages(data):
    """
    Splits a PDF into single-page PDFs (PyMuPDF).

    ---

    Parte un PDF en PDF de una página (PyMuPDF), para leerlo página a
    página cuando el documento entero no sale.
    """
    import fitz

    pages = []
    with fitz.open(stream=data, filetype="pdf") as source:
        for number in range(source.page_count):
            single = fitz.open()
            single.insert_pdf(source, from_page=number, to_page=number)
            pages.append(single.tobytes(garbage=3, deflate=True))
            single.close()
    return pages


def _merge_reads(parts) -> dict:
    """
    Joins page reads: first non-empty identification value, all rows.

    ---

    Junta las lecturas por página: de la identificación, el primer
    valor no vacío de cada campo; las filas, todas.
    """
    identification = {}
    rows = []
    for part in parts:
        for key, value in (part.get("identification") or {}).items():
            if value and not identification.get(key):
                identification[key] = value
        rows.extend(part.get("rows") or [])
    return {"identification": identification, "rows": rows}


def read_scan(entry, machine) -> dict:
    """
    Reads one scanned logbook with Gemini.

    ---

    Lee un libro escaneado con Gemini (PDF o imagen, nunca OCR local) y
    devuelve el JSON del esquema `_READ_SCHEMA`. Un PDF que no sale
    entero (respuesta no válida, o por encima del límite de datos en
    línea) se lee página a página y se juntan las lecturas. Lanza
    LogbookReadError si el archivo no se puede leer.
    """
    from document_explorer.subject_upload_service import content_type_of
    from spare_parts.gcs_service import download_bytes

    data = download_bytes(entry.bucket, entry.blob_name)
    mime = content_type_of(data, entry.name)
    if mime not in READABLE_TYPES:
        raise LogbookReadError("Formato no legible: %s" % mime)
    if mime != "application/pdf":
        if len(data) > MAX_INLINE_BYTES:
            raise LogbookReadError(
                "Imagen de %d MB, por encima del límite de Gemini."
                % (len(data) // (1024 * 1024))
            )
        return _ask_gemini(data, mime, machine)
    if len(data) <= MAX_INLINE_BYTES:
        try:
            return _ask_gemini(data, mime, machine)
        except LogbookReadError as exc:
            logger.warning(
                "# [read_scan] %s (id %s): %s -- se lee página a página",
                machine.code, entry.pk, exc,
            )
    parts = []
    for page in _pdf_pages(data):
        if len(page) > MAX_INLINE_BYTES:
            raise LogbookReadError(
                "Página de %d MB, por encima del límite de Gemini."
                % (len(page) // (1024 * 1024))
            )
        parts.append(_ask_gemini(page, mime, machine))
    return _merge_reads(parts)


def _parse_date(value):
    from ai_services.document_vision_service import parse_iso_date

    return parse_iso_date(str(value or ""))


def _to_int(value, low=0, high=10_000_000):
    """
    Integer from a hand-written figure ("10.789", "26000 kg").

    ---

    Entero de una cifra escrita a mano ("10.789", "26000 kg"); None si
    no hay cifras o se sale del rango.
    """
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return None
    number = int(digits)
    return number if low <= number <= high else None


def _clip(value, length):
    return str(value or "").strip()[:length]


def _fill_identification(machine, data) -> list:
    """
    Fills the empty logbook fields of the machine.

    ---

    Rellena solo los campos VACÍOS de la ficha con lo leído (nunca pisa
    un dato ya escrito a mano o leído de otro escaneo). Devuelve los
    nombres de los campos rellenados.
    """
    data = data or {}
    values = {
        "crane_serial_number": _clip(data.get("serial_number"), 100),
        "manufacture_year": _to_int(data.get("manufacture_year"),
                                    1900, 2100),
        "max_capacity": _clip(data.get("max_capacity"), 60),
        "length_mm": _to_int(data.get("length_mm"), 1000, 40_000),
        "width_mm": _to_int(data.get("width_mm"), 1000, 6_000),
        "height_mm": _to_int(data.get("height_mm"), 1000, 6_000),
        "mass_kg": _to_int(data.get("mass_kg"), 1000, 200_000),
        "axle_count": _to_int(data.get("axle_count"), 1, 12),
        "axle_mass": _clip(data.get("axle_mass"), 120),
        "first_owner_name": _clip(data.get("first_owner_name"), 200),
        "first_owner_tax_id": _clip(data.get("first_owner_tax_id"), 20),
        "first_owner_address": _clip(data.get("first_owner_address"), 255),
        "first_owner_city": _clip(data.get("first_owner_city"), 255),
        "plate": _clip(data.get("plate"), 20),
        "chassis_number": _clip(data.get("chassis_number"), 50),
    }
    brand_model = " ".join(
        part for part in (
            _clip(data.get("brand"), 60), _clip(data.get("model"), 80),
        ) if part
    )
    if brand_model:
        values["brand_model"] = brand_model
    filled = []
    for field, value in values.items():
        if value in (None, ""):
            continue
        if getattr(machine, field) in (None, ""):
            max_length = getattr(
                MachineAsset._meta.get_field(field), "max_length", None,
            )
            if max_length and isinstance(value, str):
                value = value[:max_length]
            setattr(machine, field, value)
            filled.append(field)
    if filled:
        machine.save(update_fields=filled + ["updated_at"])
    return filled


def store_scan(entry, machine, parsed=None, error="") -> dict:
    """
    Saves the rows read from one scan (replacing earlier ones).

    ---

    Guarda las filas leídas de un escaneo (sustituye las de una lectura
    anterior del mismo documento) y rellena la ficha. Con `error`, deja
    el documento marcado como leído con error y sin filas.
    Devuelve {"rows": n, "filled": [campos]}.
    """
    parsed = parsed or {}
    rows = []
    for row in parsed.get("rows") or []:
        section = row.get("section")
        if section not in SECTION_CODES:
            continue
        values = {
            "entry_date": _parse_date(row.get("date")),
            "entry_type": _clip(row.get("type"), 120),
            "concept": str(row.get("concept") or "").strip(),
            "entity": _clip(row.get("entity"), 200),
            "result": _clip(row.get("result"), 200),
            "next_date": _parse_date(row.get("next_date")),
        }
        if not any(values.values()):
            continue
        rows.append((section, values))
    with transaction.atomic():
        source, _created = MachineLogbookSource.objects.update_or_create(
            document=entry,
            defaults={
                "machine": machine,
                "kind": MachineLogbookSource.KIND_SCAN,
                "rows_found": len(rows),
                "error": error,
            },
        )
        source.entries.all().delete()
        MachineLogbookEntry.objects.bulk_create([
            MachineLogbookEntry(
                source=source, machine=machine, section=section, **values
            )
            for section, values in rows
        ])
        filled = (
            [] if error
            else _fill_identification(machine, parsed.get("identification"))
        )
    return {"rows": len(rows), "filled": filled}


def _norm(text) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").upper())
    return re.sub(r"[^A-Z0-9]", "", text.encode("ascii", "ignore").decode())


def _filled_count(row) -> int:
    return sum(
        1 for value in (
            row.entry_date, row.entry_type, row.concept, row.entity,
            row.result, row.next_date,
        ) if value
    )


def _deduplicated(rows):
    """
    One row per section and date across overlapping scans.

    ---

    Cada escaneo vuelve a fotografiar páginas ya escaneadas antes (la
    misma hoja con una fila más), así que la misma fila llega varias
    veces: se deja una por sección y fecha (o, sin fecha, por texto),
    la más completa.
    """
    best = {}
    for row in rows:
        if row.entry_date:
            key = (row.section, row.entry_date)
        else:
            key = (row.section, _norm(row.concept), _norm(row.entity))
        current = best.get(key)
        if current is None or _filled_count(row) > _filled_count(current):
            best[key] = row
    return sorted(
        best.values(),
        key=lambda row: (row.entry_date is None, row.entry_date, row.pk),
    )


def repair_lines(machine):
    """
    Work order tasks that belong in section 4 of the logbook.

    ---

    Tareas de los partes digitales (histórico en PDF y formulario) que
    entran en la sección 4 del libro con su mismo criterio: motores,
    mecanismos o componentes hidráulicos y elementos estructurales.
    """
    from work_order_processor.models import WorkOrderEntryLine

    return list(
        WorkOrderEntryLine.objects.filter(
            machine_asset=machine,
            entry__work_date__isnull=False,
            tipo_tarea__in=REPAIR_TASK_TYPES,
        ).filter(
            Q(fault_category__in=REPAIR_FAULT_CATEGORIES)
            | Q(fault_subcategory__in=REPAIR_FAULT_SUBCATEGORIES)
        ).select_related("entry").order_by("entry__work_date", "id")
    )


def _signature_note(row) -> str:
    """
    Note printed under a review annotated and signed in the platform.

    ---

    Nota que el libro imprime bajo una revisión anotada y firmada en la
    plataforma: quién la firmó y cuándo y, si reconstruye un registro
    extraviado, que lo dice tal cual.
    """
    if row.signed_by_id is None:
        return ""
    signer = _signer_name(row.signed_by)
    when = (
        timezone.localtime(row.signed_at).strftime("%d/%m/%Y")
        if row.signed_at else ""
    )
    if row.is_reconstructed:
        return (
            "Revisión realizada por la empresa mantenedora; registro "
            "original extraviado. Reconstruida y firmada por %s el %s."
            % (signer, when)
        )
    return "Anotada y firmada por %s el %s." % (signer, when)


def _signer_name(company_user) -> str:
    if company_user is None or company_user.user_id is None:
        return ""
    user = company_user.user
    return user.get_full_name() or user.username


def annotated_rows(machine):
    """
    Rows annotated and signed in the platform (no source document).

    ---

    Filas anotadas y firmadas en la plataforma (sin documento de
    origen), con su firmante.
    """
    return list(
        MachineLogbookEntry.objects.filter(
            machine=machine, source__isnull=True,
        ).select_related("signed_by__user")
    )


def review_rows(machine):
    """
    Periodic reviews of the crane: scans (deduplicated) plus signed ones.

    ---

    Revisiones técnicas periódicas de la grúa: las de los escaneos, sin
    repetidos, más las anotadas y firmadas en la plataforma, por fecha.
    Cada fila lleva `signature_note`.
    """
    scanned = _deduplicated(
        MachineLogbookEntry.objects.filter(
            machine=machine, source__isnull=False,
            section=MachineLogbookEntry.SECTION_PERIODIC_REVIEW,
        )
    )
    signed = [
        row for row in annotated_rows(machine)
        if row.section == MachineLogbookEntry.SECTION_PERIODIC_REVIEW
    ]
    rows = scanned + signed
    for row in rows:
        row.signature_note = _signature_note(row)
    rows.sort(
        key=lambda row: (row.entry_date is None, row.entry_date, row.pk),
    )
    return rows


def review_gaps(reviews, today=None):
    """
    Periods longer than the review interval without any review.

    ---

    Periodos sin ninguna revisión anotada más largos que el intervalo
    semestral (más REVIEW_GRACE_DAYS de margen): entre dos revisiones
    seguidas y desde la última hasta hoy. Solo informa de los huecos;
    la plataforma nunca los rellena (S154).
    Devuelve [{"start", "end", "days"}].
    """
    today = today or timezone.localdate()
    dates = sorted({row.entry_date for row in reviews if row.entry_date})
    gaps = []
    limit = REVIEW_INTERVAL_DAYS + REVIEW_GRACE_DAYS
    for previous, following in zip(dates, dates[1:] + [today]):
        days = (following - previous).days
        if days > limit:
            gaps.append({"start": previous, "end": following, "days": days})
    return gaps


def _external_repair_concept(line) -> str:
    parts = [
        line.get_fault_category_display() if line.fault_category else "",
        (
            line.get_fault_subcategory_display()
            if line.fault_subcategory else ""
        ),
    ]
    return " · ".join(part for part in parts if part) or "Reparación"


def logbook_context(machine, external=False) -> dict:
    """
    Everything the logbook PDF shows, by section.

    ---

    Todo lo que muestra el libro, por sección: ficha de la máquina,
    filas de los escaneos sin repetidos, revisiones anotadas y firmadas
    y reparaciones de los partes. Con `external` (libro para compartir
    con empresas de fuera, S154): sin nombres de mecánicos y, en vez de
    la descripción de la reparación, la familia y la subfamilia de la
    avería.
    """
    rows = _deduplicated(
        MachineLogbookEntry.objects.filter(
            machine=machine, source__isnull=False,
        )
    )
    by_section = {code: [] for code in SECTION_CODES}
    for row in rows:
        by_section[row.section].append(row)
    repairs = [
        {
            "date": row.entry_date,
            "concept": row.concept,
            "entity": row.entity,
            "source": "Libro escaneado",
        }
        for row in by_section[MachineLogbookEntry.SECTION_REPAIR]
    ]
    for line in repair_lines(machine):
        if external:
            concept = _external_repair_concept(line)
            entity = "Taller propio"
        else:
            concept = " -- ".join(
                part for part in (
                    (line.fault_description or "").strip(),
                    (line.repair_notes or "").strip(),
                ) if part
            ) or line.get_fault_subcategory_display()
            entity = "Taller propio (%s)" % (
                line.entry.worker_name or "parte de trabajo"
            )
        repairs.append({
            "date": line.entry.work_date,
            "concept": concept,
            "entity": entity,
            "source": line.get_fault_category_display(),
        })
    repairs.sort(key=lambda item: (item["date"] is None, item["date"]))
    scans = MachineLogbookSource.objects.filter(
        machine=machine, kind=MachineLogbookSource.KIND_SCAN,
    )
    return {
        "machine": machine,
        "external": external,
        "generated_at": timezone.localtime(),
        "inspections_base": by_section[
            MachineLogbookEntry.SECTION_INSPECTION_BASE],
        "inspections_structure": by_section[
            MachineLogbookEntry.SECTION_INSPECTION_STRUCTURE],
        "reviews": review_rows(machine),
        "repairs": repairs,
        "accidents": by_section[MachineLogbookEntry.SECTION_ACCIDENT],
        "notes": by_section[MachineLogbookEntry.SECTION_NOTE],
        "ownership_changes": by_section[
            MachineLogbookEntry.SECTION_OWNERSHIP],
        "scans_read": scans.count(),
        "scans_with_error": scans.exclude(error="").count(),
    }


def render_logbook_pdf(machine, external=False) -> bytes:
    """
    The logbook as PDF bytes (weasyprint).

    ---

    El libro en PDF (weasyprint, como el resto de PDF del panel); con
    `external`, el libro para compartir con empresas de fuera.
    """
    from weasyprint import HTML

    html = render_to_string(
        "fleet/logbook_pdf.html", logbook_context(machine, external),
    )
    return HTML(string=html).write_pdf()


def annotate_review(machine, user, entry_date, result, entity,
                    next_date=None, concept="", is_reconstructed=False):
    """
    Records one periodic review signed by the user.

    ---

    Anota una revisión técnica periódica firmada por el usuario que la
    graba (su usuario y la hora de la firma quedan guardados). La fecha
    es la que escribe el responsable: la plataforma nunca la calcula.
    """
    if not is_logbook_machine(machine):
        raise LogbookReadError(
            "Solo las grúas móviles A y H llevan libro historial."
        )
    if user is None or user.role not in SIGN_ROLES:
        raise LogbookReadError(
            "Solo el responsable del taller puede firmar revisiones."
        )
    if entry_date is None or entry_date > timezone.localdate():
        raise LogbookReadError(
            "La fecha de la revisión es obligatoria y no puede ser futura."
        )
    return MachineLogbookEntry.objects.create(
        machine=machine,
        section=MachineLogbookEntry.SECTION_PERIODIC_REVIEW,
        entry_date=entry_date,
        concept=(concept or "").strip(),
        entity=(entity or "").strip()[:200],
        result=(result or "").strip()[:200],
        next_date=next_date,
        signed_by=user,
        signed_at=timezone.now(),
        is_reconstructed=is_reconstructed,
    )


def default_maintainer(machine) -> str:
    """
    Maintainer of the latest scanned review, to prefill the form.

    ---

    Empresa mantenedora de la última revisión escaneada, para proponerla
    en el formulario (se puede cambiar).
    """
    row = MachineLogbookEntry.objects.filter(
        machine=machine, source__isnull=False,
        section=MachineLogbookEntry.SECTION_PERIODIC_REVIEW,
    ).exclude(entity="").order_by("-entry_date", "-id").first()
    return row.entity if row else ""


def _trash_same_day_books(machine, new_entry, user):
    """
    Sends earlier books generated today for this crane to the trash.

    ---

    Manda a la papelera del cubo los libros generados ese mismo día
    para esta grúa, salvo el nuevo (Miguel Ángel, S154: el del mismo
    día se sustituye, no se acumula como histórico con "_1"). Escritura
    de índice pura (deleted_at/deleted_by), el blob no se toca, igual
    que `trash_dossier_entry`.
    """
    from document_explorer.classification_service import (
        trash_dossier_entry,
    )
    from document_explorer.models import DocumentIndexEntry

    earlier = DocumentIndexEntry.objects.filter(
        logbook_source__machine=machine,
        logbook_source__kind=MachineLogbookSource.KIND_GENERATED,
        deleted_at__isnull=True,
        issue_date=new_entry.issue_date,
    ).exclude(pk=new_entry.pk)
    for old in earlier:
        if user is not None:
            old.deleted_at = timezone.now()
            old.deleted_by = user
            old.save(update_fields=["deleted_at", "deleted_by"])
        elif not trash_dossier_entry(old):
            continue
        logger.info(
            "# [generate_logbook] %s -> libro del mismo día %s a la "
            "papelera", machine.code, old.name,
        )


def generate_logbook(machine, user=None):
    """
    Generates the logbook and stores it as the machine's document.

    ---

    Genera el libro y lo guarda en el cubo como documento
    LIBRO_HISTORIAL de la máquina (subida de siempre: nombre canónico,
    sin pisar nunca un blob, sustitución de vigencia). Un libro ya
    generado ese mismo día para la grúa va a la papelera (S154).
    Devuelve la entrada del índice creada.
    """
    from document_explorer.models import DocumentTypeCatalog
    from document_explorer.subject_upload_service import (
        upload_subject_document,
    )

    if not is_logbook_machine(machine):
        raise LogbookReadError(
            "Solo las grúas móviles A y H llevan libro historial."
        )
    document_type = DocumentTypeCatalog.objects.get(code=LOGBOOK_TYPE_CODE)
    data = render_logbook_pdf(machine)
    result = upload_subject_document(
        subject=machine,
        domain_content_type=_machine_content_type(),
        document_type=document_type,
        data=data,
        original_filename="%s_LIBRO_HISTORIAL.pdf" % machine.code,
        typed_date=None,
        subject_label=machine.code,
        uploaded_by=user,
        typed_issue_date=timezone.localdate(),
    )
    entry = result["entry"]
    MachineLogbookSource.objects.create(
        machine=machine, document=entry,
        kind=MachineLogbookSource.KIND_GENERATED, created_by=user,
    )
    _trash_same_day_books(machine, entry, user)
    logger.info(
        "# [generate_logbook] %s -> libro generado, documento %s",
        machine.code, entry.pk,
    )
    return entry
