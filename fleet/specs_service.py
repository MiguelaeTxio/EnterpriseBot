# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/specs_service.py
"""
H23 (S154, invasora) -- technical specifications of the vehicles.

Reads, with Gemini, the current ITV, vehicle permit, technical sheet
and load chart of each cost centre and fills its empty specification
fields (lifting capacity, maximum authorised mass, tare, dimensions,
axles, year). Never overwrites a value already in the record.

---

H23 (S154, invasora) -- especificaciones técnicas de los vehículos.

Carlos: "quiero saber cuáles son los camiones y grúas de 50T".
Miguel Ángel: "sabemos los modelos, sabemos qué máquina es, tenemos los
permisos de circulación, ITV, fichas técnicas, podemos ver
perfectamente las capacidades, pesos". Lee con Gemini la ITV, el
permiso de circulación, la ficha técnica y la tabla de carga vigentes
de cada centro de gasto y rellena solo los campos vacíos de la ficha.
La capacidad de elevación, si ningún documento la da, puede salir del
modelo conocido de la máquina; `specs_source` dice de dónde sale cada
dato.
"""
import json
import logging
import re
from decimal import Decimal, InvalidOperation

from django.utils import timezone

logger = logging.getLogger(__name__)

SPEC_TYPE_CODES = (
    "ITV", "PERMISO_CIRCULACION", "FICHA_TECNICA", "TABLA_DE_CARGA",
)
READABLE_TYPES = ("application/pdf", "image/png", "image/jpeg",
                  "image/webp")
MAX_FILE_BYTES = 7 * 1024 * 1024
MAX_REQUEST_BYTES = 18 * 1024 * 1024
MAX_PAGES_LARGE_PDF = 8
GEMINI_TIMEOUT_MS = 180_000

SOURCE_LABELS = {
    "ITV": "ITV",
    "PERMISO_CIRCULACION": "permiso de circulación",
    "FICHA_TECNICA": "ficha técnica",
    "TABLA_DE_CARGA": "tabla de carga",
    "MODEL": "modelo de la máquina (sin documento)",
    "LOGBOOK": "libro historial",
}

_VALUE = {
    "type": "object",
    "properties": {
        "value": {"type": "number", "nullable": True},
        "source": {
            "type": "string",
            # Gemini no admite un valor vacío en un enum: "NONE" es
            # "no aparece" (S154, 400 INVALID_ARGUMENT en la primera
            # pasada).
            "enum": list(SOURCE_LABELS) + ["NONE"],
        },
    },
    "required": ["value", "source"],
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {"type": "string"},
        "model": {"type": "string"},
        "lifting_capacity_tonnes": _VALUE,
        "lifting_capacity_text": {"type": "string"},
        "lifting_moment_tm": _VALUE,
        "max_authorized_mass_kg": _VALUE,
        "tare_kg": _VALUE,
        "length_mm": _VALUE,
        "width_mm": _VALUE,
        "height_mm": _VALUE,
        "axle_count": _VALUE,
        "manufacture_year": _VALUE,
    },
    "required": [
        "brand", "model", "lifting_capacity_tonnes",
        "lifting_capacity_text", "lifting_moment_tm",
        "max_authorized_mass_kg", "tare_kg",
        "length_mm", "width_mm", "height_mm", "axle_count",
        "manufacture_year",
    ],
}

_PROMPT = """Eres técnico de una empresa española de grúas y transportes.
Te paso los documentos vigentes del vehículo {code} ({family}; en la
ficha: "{brand_model}"), cada uno precedido de su tipo.

Devuelve sus especificaciones técnicas. Para cada dato indica en
"source" de qué documento lo sacas (ITV, PERMISO_CIRCULACION,
FICHA_TECNICA, TABLA_DE_CARGA) o "NONE" si no aparece:
- lifting_capacity_tonnes: capacidad máxima de elevación de la grúa en
  toneladas (la nominal del modelo: "50 t", "LTM 1050" son 50 t). Si el
  vehículo lleva grúa y ningún documento la da pero conoces con
  seguridad el modelo exacto de la grúa, dala con source "MODEL". Si
  la grúa se expresa en t·m (momento), deja value null y escríbelo en
  lifting_capacity_text. Sin grúa: null.
- lifting_capacity_text: la capacidad tal como figura ("50 t",
  "25 t·m"), o "". Nunca el modelo de la grúa ("PK 29002").
- lifting_moment_tm: momento de carga de la grúa en t·m (grúas de
  camión / autocargantes: "PK 44002" -> la cifra en t·m de su ficha).
  Si ningún documento lo da pero conoces con seguridad el modelo exacto
  de la grúa, dalo con source "MODEL". Sin grúa de este tipo: null.
- max_authorized_mass_kg: masa máxima técnicamente admisible / MMA
  (ITV campo F.1 o F.2), en kg.
- tare_kg: masa en orden de marcha / tara (ITV campo G), en kg.
- length_mm, width_mm, height_mm: dimensiones (ITV F.4, F.5, F.6 o
  ficha), en mm.
- axle_count: número de ejes.
- manufacture_year: año de fabricación (o de primera matriculación si
  no hay otro).
- brand, model: marca y modelo del vehículo base, o "".
Nunca inventes una cifra que no esté en un documento, salvo la
capacidad por el modelo con source "MODEL". Responde solo el JSON."""


class SpecsReadError(Exception):
    """
    Error reading a vehicle's specifications.

    ---

    Error al leer las especificaciones de un vehículo.
    """


def parse_capacity(text):
    """
    Tonnes from a capacity as written ("50 Tm", "120TNS.", "18.000 K").

    ---

    Toneladas de una capacidad escrita a mano: "50 Tm", "35TN",
    "120TNS.", "2'9 (t)", "60 t bei 2,5 m" -> 50, 35, 120, 2.9, 60;
    "18.000 K" (kg) -> 18. None si no hay cifra o es un momento (t·m).
    """
    text = (text or "").strip()
    if not text or re.search(r"t\s*[·.x*]\s*m\b", text, re.I):
        return None
    match = re.search(r"\d+(?:[.,']\d+)*", text)
    if not match:
        return None
    raw = match.group(0)
    rest = text[match.end():].strip().upper()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        number = raw.replace(".", "")
    else:
        number = raw.replace("'", ".").replace(",", ".")
    try:
        value = Decimal(number)
    except InvalidOperation:
        return None
    if rest.startswith("K") and value >= 1000:
        value = value / 1000
    if value <= 0 or value > 2000:
        return None
    return value.quantize(Decimal("0.01"))


def parse_moment(text):
    """
    t·m from a crane moment as written ("44 t·m", "35Tm", "25.8 t·m").

    ---

    Momento de carga en t·m de un texto escrito ("44 t·m", "35Tm",
    "25.8 t·m"); None si no hay cifra. Solo para la grúa de los
    autocargantes, donde "Tm" es t·m.
    """
    text = (text or "").strip()
    match = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*t\s*[·.x*]?\s*m\b", text,
                     re.I)
    if not match:
        return None
    value = Decimal(match.group(1).replace(",", "."))
    if value <= 0 or value > 2000:
        return None
    return value.quantize(Decimal("0.01"))


MOMENT_FAMILIES = ("AUTOCARGANTES",)


def source_documents(machine):
    """
    Current ITV, permit, technical sheet and load chart of the machine.

    ---

    ITV, permiso de circulación, ficha técnica y tabla de carga
    vigentes del centro de gasto, en ese orden.
    """
    from django.contrib.contenttypes.models import ContentType

    from document_explorer.models import DocumentIndexEntry
    from fleet.models import MachineAsset

    entries = DocumentIndexEntry.objects.filter(
        domain_content_type=ContentType.objects.get_for_model(MachineAsset),
        domain_object_id=machine.pk,
        deleted_at__isnull=True,
        is_obsolete=False,
        document_type__code__in=SPEC_TYPE_CODES,
    ).select_related("document_type")
    return sorted(
        entries,
        key=lambda entry: (
            SPEC_TYPE_CODES.index(entry.document_type.code), -entry.pk,
        ),
    )


def _pdf_opens(data):
    import fitz

    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            return document.page_count > 0 and bool(
                document[0].get_text("text") is not None)
    except Exception:  # noqa: BLE001 -- PDF dañado
        return False


def _first_pages(data, count):
    import fitz

    source = fitz.open(stream=data, filetype="pdf")
    target = fitz.open()
    target.insert_pdf(source, from_page=0,
                      to_page=min(count, source.page_count) - 1)
    return target.tobytes()


def _parts(entries):
    """
    Gemini parts for the documents, within the size limits.

    ---

    Las partes para Gemini: cada documento precedido de su tipo. Un PDF
    de más de 7 MB va con sus primeras páginas; lo que no cabe en la
    petición se queda fuera. Devuelve (partes, nombres usados).
    """
    from google.genai.types import Part

    from document_explorer.subject_upload_service import content_type_of
    from spare_parts.gcs_service import download_bytes

    parts, used, total = [], [], 0
    for entry in entries:
        data = download_bytes(entry.bucket, entry.blob_name)
        mime = content_type_of(data, entry.name)
        if mime not in READABLE_TYPES:
            continue
        if mime == "application/pdf" and not _pdf_opens(data):
            # S154: un PDF dañado tumbaba la petición entera (A57,
            # 400 "malformed or corrupted"); se deja fuera y se leen
            # los demás.
            logger.warning("# [specs] %s: PDF dañado, se omite.",
                           entry.name)
            continue
        if len(data) > MAX_FILE_BYTES and mime == "application/pdf":
            data = _first_pages(data, MAX_PAGES_LARGE_PDF)
        if len(data) > MAX_FILE_BYTES or total + len(data) > \
                MAX_REQUEST_BYTES:
            continue
        total += len(data)
        parts.append("Documento: %s (%s)" % (
            entry.document_type.code, entry.name))
        parts.append(Part.from_bytes(data=data, mime_type=mime))
        used.append(entry)
    return parts, used


def _ask_gemini(machine, parts):
    from google.genai.types import (
        GenerateContentConfig, HttpOptions, ThinkingConfig,
    )

    from ai_services.document_vision_service import (
        _generate_content_with_retry,
    )
    from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client

    prompt = _PROMPT.format(
        code=machine.code, family=machine.family or "sin familia",
        brand_model=machine.brand_model or "",
    )
    response = _generate_content_with_retry(
        get_gemini_client(),
        model=DEFAULT_MODEL,
        contents=parts + [prompt],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=GEMINI_TIMEOUT_MS),
            response_mime_type="application/json",
            response_schema=_SCHEMA,
            thinking_config=ThinkingConfig(thinking_level="low"),
            temperature=0.0,
        ),
    )
    try:
        return json.loads(response.text.strip())
    except (ValueError, AttributeError) as exc:
        raise SpecsReadError("Respuesta de Gemini no válida.") from exc


def _ask_with_retry(machine, parts, used):
    """
    Ask Gemini; if a file is undecodable, drop it and ask again.

    ---

    Pregunta a Gemini; si rechaza un archivo por dañado (A57: 400
    "malformed or corrupted" con un PDF que PyMuPDF sí abre), prueba
    cada documento por separado, deja fuera los que rechaza y vuelve a
    preguntar con los demás. `used` queda solo con los leídos.
    """
    try:
        return _ask_gemini(machine, parts)
    except Exception as exc:  # noqa: BLE001
        if "malformed" not in str(exc) and "corrupted" not in str(exc):
            raise
    good_parts, good_used = [], []
    for index, entry in enumerate(list(used)):
        pair = parts[index * 2:index * 2 + 2]
        try:
            _ask_gemini(machine, pair)
        except Exception as exc:  # noqa: BLE001
            if "malformed" not in str(exc) and "corrupted" not in str(exc):
                raise
            logger.warning("# [specs] %s: %s dañado para Gemini, se omite.",
                           machine.code, entry.name)
            continue
        good_parts.extend(pair)
        good_used.append(entry)
    used[:] = good_used
    if not good_parts:
        return {}
    return _ask_gemini(machine, good_parts)


def _number(item, low, high):
    value = (item or {}).get("value")
    if value is None:
        return None
    try:
        value = Decimal(str(value))
    except InvalidOperation:
        return None
    if value < low or value > high:
        return None
    return value


def _source(item):
    source = (item or {}).get("source") or ""
    return "" if source == "NONE" else source


def apply_specs(machine, data):
    """
    Fill the empty specification fields from a reading.

    ---

    Rellena solo los campos VACÍOS de la ficha con lo leído (nunca pisa
    un dato escrito a mano o sacado del libro). Devuelve
    {campo: origen} de lo rellenado.
    """
    candidates = {
        "capacity_tonnes": ("lifting_capacity_tonnes", 0.5, 2000, False),
        "capacity_tm": ("lifting_moment_tm", 0.5, 2000, False),
        "max_authorized_mass_kg": ("max_authorized_mass_kg", 500,
                                   200_000, True),
        "mass_kg": ("tare_kg", 300, 200_000, True),
        "length_mm": ("length_mm", 1000, 40_000, True),
        "width_mm": ("width_mm", 1000, 6_000, True),
        "height_mm": ("height_mm", 1000, 6_000, True),
        "axle_count": ("axle_count", 1, 12, True),
        "manufacture_year": ("manufacture_year", 1950, 2100, True),
    }
    filled = {}
    for field, (key, low, high, integer) in candidates.items():
        item = data.get(key) or {}
        value = _number(item, low, high)
        if value is None or getattr(machine, field) not in (None, ""):
            continue
        setattr(machine, field,
                int(value) if integer else value.quantize(Decimal("0.01")))
        filled[field] = _source(item)
    text = (data.get("lifting_capacity_text") or "").strip()[:60]
    if text and not machine.max_capacity:
        machine.max_capacity = text
        filled["max_capacity"] = _source(
            data.get("lifting_capacity_tonnes"))
    if not machine.brand_model:
        brand_model = " ".join(
            part for part in (
                (data.get("brand") or "").strip(),
                (data.get("model") or "").strip(),
            ) if part
        )[:100]
        if brand_model:
            machine.brand_model = brand_model
            filled["brand_model"] = ""
    return filled


def _source_text(filled, used):
    from fleet.models import MachineAsset

    lines = []
    for field, source in filled.items():
        label = MachineAsset._meta.get_field(field).verbose_name
        lines.append("%s: %s" % (
            label,
            "quitada (era el modelo de la grúa)" if source == "CLEARED"
            else SOURCE_LABELS.get(source, "documentos"),
        ))
    if used:
        lines.append("Leído de: %s" % ", ".join(e.name for e in used))
    return "\n".join(lines)


def read_specs(machine) -> dict:
    """
    Read and store the specifications of one machine.

    ---

    Lee las especificaciones de un centro de gasto y las guarda: primero
    la capacidad escrita del libro historial (sin Gemini); después,
    con Gemini, sus documentos vigentes. Devuelve
    {"filled": {campo: origen}, "documents": n}.
    """
    filled = {}
    is_moment = (machine.family or "").upper() in MOMENT_FAMILIES
    if (is_moment and machine.max_capacity
            and parse_moment(machine.max_capacity) is None
            and "Capacidad máxima:" in machine.specs_source):
        # S154: en la primera pasada Gemini dejó en algunos
        # autocargantes el modelo de la grúa ("PK 29002 G") como
        # capacidad; ese texto lo puso esta lectura, así que se quita.
        machine.max_capacity = ""
        filled["max_capacity"] = "CLEARED"
    if is_moment and machine.capacity_tm is None and machine.max_capacity:
        value = parse_moment(machine.max_capacity)
        if value is not None:
            machine.capacity_tm = value
            filled["capacity_tm"] = "LOGBOOK"
    if (not is_moment and machine.capacity_tonnes is None
            and machine.max_capacity):
        value = parse_capacity(machine.max_capacity)
        if value is not None:
            machine.capacity_tonnes = value
            filled["capacity_tonnes"] = "LOGBOOK"
    entries = source_documents(machine)
    parts, used = _parts(entries) if entries else ([], [])
    if parts:
        filled.update(apply_specs(machine, _ask_with_retry(
            machine, parts, used)))
    if not used and not filled:
        # Sin documentos que leer: no se marca, para leerlo cuando los
        # tenga.
        return {"filled": {}, "documents": 0}
    note = _source_text(filled, used)
    if note:
        machine.specs_source = (
            (machine.specs_source + "\n" if machine.specs_source else "")
            + note
        )
    machine.specs_read_at = timezone.now()
    machine.save(update_fields=sorted(
        set(filled) | {"specs_source", "specs_read_at"}
    ))
    return {"filled": filled, "documents": len(used)}
