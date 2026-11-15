# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/insurance/readings.py
"""
Which insurance documents of the bucket a report needs, and their
reading with Gemini (cached in InsuranceDocumentReading).

---

Qué documentos de seguro del cubo necesita un informe y su lectura con
Gemini, guardada en InsuranceDocumentReading para no volver a leer lo
mismo en cada informe (la primera vez son varios cientos de documentos;
después, solo los nuevos o cambiados). Misma lectura que el comando
insurance_renewal_report de S152 (el OCR del panel falta en la mayoría
de los documentos de seguro, así que se lee el PDF o la imagen), con el
tipo de seguro que decide la propia IA (nunca listas de palabras).
"""
import datetime
import json
import logging

from django.db.models import Q
from django.utils import timezone

from document_explorer.models import DocumentIndexEntry
from insurance.models import InsuranceDocumentReading

logger = logging.getLogger(__name__)

INSURANCE_TYPES = (
    "SEGURO", "POLIZA_SEGURO", "CERTIFICADO_SEGURO",
    "POLIZA_SEGURO_EMPRESA", "RECIBO_SEGURO_EMPRESA",
)
# Carpetas que no son seguros en vigor.
EXCLUDED_PATH_WORDS = ("OBSOLET", "SINIESTRO", "PROPUESTA", "OFERTA")
MAX_PAGES = 8
MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
}
CATEGORIES = (
    ("responsabilidad_civil", "Responsabilidad civil"),
    ("circulacion", "Circulación"),
    ("averia_maquinaria", "Avería de maquinaria"),
    ("accidentes_convenio", "Accidentes de convenio"),
    ("asistencia_defensa", "Asistencia en carretera y defensa jurídica"),
    ("locales", "Locales: multirriesgo, pyme y hogar"),
    ("transporte_mercancias", "Transporte de mercancías"),
    ("vida", "Vida"),
    ("salud", "Salud"),
    ("credito", "Crédito"),
    ("otros", "Otros"),
)
CATEGORY_LABELS = dict(CATEGORIES)

_STRING = {"type": "string", "nullable": True}
_NUMBER = {"type": "number", "nullable": True}
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "document_kind": {
            "type": "string",
            "enum": ["recibo", "poliza", "certificado", "carta_verde",
                     "condiciones_generales", "listado", "no_es_seguro",
                     "otro"],
        },
        "category": {"type": "string",
                     "enum": [key for key, _label in CATEGORIES]},
        "insurer": _STRING,
        "broker": _STRING,
        "policy_number": _STRING,
        "receipt_number": _STRING,
        "policyholder": _STRING,
        "insured_plates": {"type": "array", "items": {"type": "string"}},
        "insured_object": _STRING,
        "cover": _STRING,
        "total_premium": _NUMBER,
        "net_premium": _NUMBER,
        "payment_frequency": _STRING,
        "period_start": _STRING,
        "period_end": _STRING,
        "renewal_date": _STRING,
        "notes": _STRING,
    },
    "required": [
        "document_kind", "category", "insurer", "broker",
        "policy_number", "receipt_number", "policyholder",
        "insured_plates", "insured_object", "cover", "total_premium",
        "net_premium", "payment_frequency", "period_start", "period_end",
        "renewal_date", "notes",
    ],
}

PROMPT = """Este documento es un seguro (o un recibo de un seguro) de un
vehículo, de una máquina o de una empresa del Grupo Álvarez (grúas). Lee
el documento completo y devuelve solo lo que conste en él, sin inventar
nada. Si un dato no consta, null.

- document_kind: recibo (cobro de la prima de un periodo), poliza
  (condiciones particulares o póliza completa), certificado (certificado
  de seguro o de cobertura), carta_verde, condiciones_generales,
  listado (lista de varios vehículos o pólizas), no_es_seguro (no es un
  seguro aunque esté archivado como tal: contrato de leasing, renting o
  préstamo, factura, presupuesto u oferta de seguro sin contratar) u
  otro.
- category: el tipo de seguro según lo que cubre:
  responsabilidad_civil (RC general, de explotación, patronal, de
  plataformas, de directivos...), circulacion (seguro obligatorio o de
  automóvil de un vehículo, remolque, grúa o flota de vehículos),
  averia_maquinaria (avería, daños o rotura de maquinaria, daños
  externos de grúas y equipos), accidentes_convenio (accidentes de los
  trabajadores por convenio colectivo), asistencia_defensa (asistencia
  en viaje o en carretera, defensa jurídica), locales (multirriesgo,
  pyme, comercio, oficina, nave u hogar), transporte_mercancias,
  vida, salud, credito (seguro de crédito o caución) u otros.
- insurer: compañía aseguradora (Allianz, AXA, Mapfre, Generali...).
- broker: mediador, corredor o agente (correduría, agencia o agente con
  su nombre). No la aseguradora.
- policy_number: número de póliza tal cual figura. Nunca el número del
  recibo; si solo hay número de recibo, null.
- receipt_number: número del recibo, si lo es.
- policyholder: tomador del seguro (empresa o persona) con su CIF si
  consta.
- insured_plates: matrículas o números de bastidor de los vehículos o
  máquinas asegurados que aparezcan.
- insured_object: qué se asegura (vehículo con marca y modelo, flota,
  responsabilidad civil de la empresa, nave, vivienda...).
- cover: modalidad y coberturas principales, en una frase corta.
- total_premium: importe total a pagar del recibo o prima total anual de
  la póliza, en euros, como número (1234.56).
- net_premium: prima neta, si consta.
- payment_frequency: anual, semestral, trimestral, mensual...
- period_start / period_end: periodo de cobertura del documento, en
  formato AAAA-MM-DD.
- renewal_date: fecha de vencimiento o renovación de la póliza, en
  formato AAAA-MM-DD.
- notes: dato útil para renegociar el precio (bonificaciones,
  franquicias, siniestros, capital asegurado), en una frase. Sin datos
  personales de nadie. null si no hay nada.

Responde únicamente con el JSON solicitado."""


def mime_type(entry):
    """
    MIME type Gemini can read for this file, or None.
    ---
    Tipo MIME que Gemini puede leer para este archivo, o None.
    """
    if "." not in entry.name:
        return None
    return MIME_BY_EXTENSION.get(entry.name.rsplit(".", 1)[-1].lower())


def _months_before(day, months):
    year, month = day.year, day.month - months
    while month <= 0:
        month += 12
        year -= 1
    return datetime.date(year, month, 1)


def candidates(month_from):
    """
    The insurance documents a report from `month_from` needs.
    ---
    Los documentos de seguro que necesita un informe desde `month_from`:
    vivos, no obsoletos, fuera de carpetas de obsoletos, siniestros u
    ofertas, legibles, y recientes (caducan desde 13 meses antes del
    mes de vencimiento, o sin caducidad emitidos en los 25 meses
    anteriores, o sin ninguna fecha). Además, el último de cada tipo de
    cada máquina aunque sea más antiguo, para que ningún vehículo se
    quede fuera por no tener fechas en el panel.
    """
    expiry_floor = _months_before(month_from, 13)
    issue_floor = _months_before(month_from, 25)
    alive = DocumentIndexEntry.objects.filter(
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        is_obsolete=False, document_type__code__in=INSURANCE_TYPES,
    ).select_related("document_type", "domain_content_type")
    recent = alive.filter(
        Q(expiry_date__gte=expiry_floor)
        | Q(expiry_date__isnull=True, issue_date__gte=issue_floor)
        | Q(expiry_date__isnull=True, issue_date__isnull=True))
    chosen = {entry.pk: entry for entry in recent}
    latest = {}
    for entry in alive.filter(domain_object_id__isnull=False):
        key = (entry.domain_content_type_id, entry.domain_object_id,
               entry.document_type_id)
        current = latest.get(key)
        if current is None or _recency(entry) > _recency(current):
            latest[key] = entry
    for entry in latest.values():
        chosen.setdefault(entry.pk, entry)
    result = []
    for entry in chosen.values():
        path = (entry.parent_path + "/" + entry.name).upper()
        if any(word in path for word in EXCLUDED_PATH_WORDS):
            continue
        if mime_type(entry) is None:
            continue
        result.append(entry)
    result.sort(key=lambda e: e.pk)
    return result


def _recency(entry):
    return (entry.expiry_date or datetime.date.min,
            entry.issue_date or datetime.date.min, entry.pk)


def pending(entries):
    """
    The entries without a valid reading (new, changed or failed).
    ---
    Los documentos sin lectura buena: nuevos, cambiados (otro md5) o
    cuya lectura falló.
    """
    done = {
        reading.entry_id: reading for reading in
        InsuranceDocumentReading.objects.filter(
            entry_id__in=[e.pk for e in entries])
    }
    result = []
    for entry in entries:
        reading = done.get(entry.pk)
        if (reading is None or reading.error or reading.data is None
                or (entry.md5_hash or "") != reading.md5_hash):
            result.append(entry)
    return result


def read(entry, storage=None, client=None):
    """
    Read one document with Gemini and store the reading.
    ---
    Lee un documento con Gemini y guarda la lectura (o el error, para
    reintentarlo en el siguiente informe).
    """
    from google.genai.types import GenerateContentConfig
    from google.genai.types import HttpOptions
    from google.genai.types import Part
    from google.genai.types import ThinkingConfig

    from ai_services.document_vision_service import (
        _generate_content_with_retry)
    from ai_services.gemini_client import DEFAULT_MODEL
    from ai_services.gemini_client import get_gemini_client
    from spare_parts.gcs_service import get_storage_client

    storage = storage or get_storage_client()
    client = client or get_gemini_client()
    data, error = None, ""
    try:
        blob = storage.bucket(entry.bucket).get_blob(entry.blob_name)
        if blob is None:
            raise ValueError("no está en el cubo")
        content = blob.download_as_bytes()
        mime = mime_type(entry)
        if mime == "application/pdf":
            content = _first_pages(content)
        response = _generate_content_with_retry(
            client,
            model=DEFAULT_MODEL,
            contents=[Part.from_bytes(data=content, mime_type=mime),
                      PROMPT],
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=120_000),
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
                thinking_config=ThinkingConfig(thinking_level="low"),
                temperature=0.0,
            ),
        )
        data = json.loads(response.text.strip())
    except Exception as exc:  # noqa: BLE001 -- se guarda y se sigue
        error = str(exc)[:500] or exc.__class__.__name__
        logger.warning("# [insurance.read] %s: %s", entry.pk, error)
    InsuranceDocumentReading.objects.update_or_create(
        entry=entry,
        defaults={"md5_hash": entry.md5_hash or "", "data": data,
                  "error": error, "read_at": timezone.now()},
    )
    return data, error


def _first_pages(pdf_bytes):
    """
    The first MAX_PAGES pages of a PDF (whole PDF if shorter/unreadable).
    ---
    Las MAX_PAGES primeras páginas de un PDF (entero si es más corto o
    no se puede abrir).
    """
    import fitz  # PyMuPDF

    from ai_services.document_vision_service import extract_pages

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            pages = pdf.page_count
    except Exception:  # noqa: BLE001 -- se manda tal cual
        return pdf_bytes
    if pages <= MAX_PAGES:
        return pdf_bytes
    return extract_pages(pdf_bytes, list(range(1, MAX_PAGES + 1)))


LEDGER_PROMPT = """Cada línea es un seguro que aparece en la contabilidad
(cuenta 625, primas de seguros) de una empresa de grúas: aseguradora,
proyecto de gasto y concepto del apunte. Di de qué tipo es cada seguro
según lo que suele cubrir: responsabilidad_civil, circulacion (vehículo,
remolque, grúa, moto o flota), averia_maquinaria, accidentes_convenio,
asistencia_defensa, locales (pyme, nave, oficina, hogar), transporte_
mercancias, vida, salud, credito u otros. Devuelve una lista JSON con un
objeto {"id": <id de la línea>, "category": <tipo>} por línea."""


def classify_ledger_groups(lines):
    """
    Insurance category of ledger-only insurances, decided by Gemini.
    ---
    Tipo de seguro de los seguros que solo están en el mayor (sin
    documento), decidido por Gemini en una sola llamada. `lines` es una
    lista de (id, texto). Devuelve {id: categoría}; los que falten,
    «otros».
    """
    if not lines:
        return {}
    from google.genai.types import GenerateContentConfig
    from google.genai.types import ThinkingConfig

    from ai_services.document_vision_service import (
        _generate_content_with_retry)
    from ai_services.gemini_client import DEFAULT_MODEL
    from ai_services.gemini_client import get_gemini_client

    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "category": {"type": "string",
                             "enum": [key for key, _l in CATEGORIES]},
            },
            "required": ["id", "category"],
        },
    }
    text = "\n".join("%s | %s" % (key, value) for key, value in lines)
    try:
        response = _generate_content_with_retry(
            get_gemini_client(),
            model=DEFAULT_MODEL,
            contents=[LEDGER_PROMPT + "\n\n" + text],
            config=GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                thinking_config=ThinkingConfig(thinking_level="low"),
                temperature=0.0,
            ),
        )
        items = json.loads(response.text.strip())
    except Exception as exc:  # noqa: BLE001 -- sin tipo, «otros»
        logger.warning("# [insurance.classify_ledger] %s", exc)
        return {}
    return {str(item.get("id")): item.get("category") or "otros"
            for item in items if isinstance(item, dict)}
