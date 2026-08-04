# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/classification_service.py
"""
First real Gemini call for H29 classification (S040, testing phase --
Miguel Angel: "generar ya el prompt para empezar a hacer las pruebas
de clasificación de la carpeta de cuarentena").

Reuses the shared, already-validated Gemini plumbing from `ai_services`
(client construction, rate limiting, 429 retry, JSON response_schema
pattern) instead of duplicating it -- same client used by the voice
bridge, WhatsApp, and spare_parts vision (transversal infra, DRY
principle per doc-master-enterprisebot section 4.1.1). Does NOT import
anything from `document_ingestion`/`entity_matching_service`/
`machine_documents`/`personal_documents` -- H29 stays isolated from
H17-H25 per Miguel Angel's explicit S040 decision (H29 annex, 3.15,
"Regla derivada").

Gemini's job stops at *suggesting* a `DocumentTypeCatalog.code` and a
handful of hint fields -- see `naming_service` for why the actual
filename is never built from Gemini's own wording.

**Testing phase, not yet wired to any batch/production classification
flow.** Callers get the raw suggestion back and decide what to do with
it (this session: a "Clasificar" button on the explorer that shows the
suggestion via Django messages, nothing auto-applied).

---

Primera llamada real a Gemini para la clasificación de H29 (S040, fase
de pruebas -- Miguel Ángel: "generar ya el prompt para empezar a hacer
las pruebas de clasificación de la carpeta de cuarentena").

Reutiliza el mecanismo de Gemini ya compartido y validado de
`ai_services` (construcción de cliente, límite de tasa, reintento ante
429, patrón de `response_schema` JSON) en vez de duplicarlo -- el mismo
cliente que usan el puente de voz, WhatsApp y la visión de
`spare_parts` (infraestructura transversal, principio DRY, ver
doc-master-enterprisebot sección 4.1.1). No importa nada de
`document_ingestion`/`entity_matching_service`/`machine_documents`/
`personal_documents` -- H29 queda aislado de H17-H25 según la decisión
explícita de Miguel Ángel en S040 (anexo H29, 3.15, "Regla derivada").

El trabajo de Gemini termina en *sugerir* un `DocumentTypeCatalog.code`
y un puñado de campos de pista -- ver `naming_service` para el porqué
de que el nombre de archivo final nunca se construya con la redacción
propia de Gemini.

**Fase de pruebas, todavía sin conectar a ningún flujo de
clasificación por lote/producción.** Quien llama recibe la sugerencia
en crudo y decide qué hacer con ella (en esta sesión: un botón
"Clasificar" en el explorador que muestra la sugerencia vía mensajes
de Django, sin aplicar nada automáticamente).
**Extended S040 (misma sesión): ya aplica de verdad, pero 100%
virtual.** Miguel Ángel, verbatim: *"En realidad no vamos a tocar
CGS, lo vamos a hacer todo a nivel de datos (...) Al clasificarla le
damos el nombre nuevo en base de datos."* Aplicar una clasificación
escribe únicamente `DocumentIndexEntry.name` (el nombre VIRTUAL) --
`blob_name` (la ruta real en el cubo) nunca se toca, exactamente el
mismo principio que `move_service` (v2, puntero puro, S039). Ver
`apply_classification()`.
"""
import datetime
import logging
import os
import re
import subprocess
import tempfile
import time

import fitz  # PyMuPDF -- ya en requirements (ver cabecera del módulo)

from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from ai_services.gemini_rate_limiter import acquire_gemini_slot
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes

from . import naming_service
from .buckets import QUARANTINE_PREFIX
from .move_service import _virtual_location_taken, move_entry

from .models import DocumentTypeCatalog, PersonIdentity

logger = logging.getLogger(__name__)

_MAX_GEMINI_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 60

# Verificado online el 2026-07-31 contra la documentación real de
# Document understanding de Gemini (ai.google.dev/gemini-api/docs/
# document-processing): "You can also pass non-PDF documents in the
# same way but Gemini will see them as normal text" -- es decir, un
# .docx con su mimeType real de Office (OpenXML) NO se acepta
# directamente; requeriría convertirlo a PDF/texto plano antes.
# Confirmado también con el error real de producción de esta misma
# sesión (S040): 400 INVALID_ARGUMENT sobre
# application/vnd.openxmlformats-officedocument.wordprocessingml.document.
_SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/heic",
    "image/heif",
    "text/plain",
}

# Extensiones que LibreOffice headless sabe convertir a PDF -- S040,
# tras el hallazgo real de un .docx rechazado por Gemini. Solo Office
# clásico de documento/hoja/presentación; deliberadamente no incluye
# nada que ya esté en _SUPPORTED_MIME_TYPES (PDF, imágenes, texto
# plano ya se aceptan directamente, sin pasar por LibreOffice).
_LIBREOFFICE_CONVERTIBLE_EXTENSIONS = {
    "docx", "doc", "odt", "rtf",
    "xlsx", "xls", "ods",
    "pptx", "ppt", "odp",
}
_SOFFICE_TIMEOUT_SECONDS = 90

# Límite real confirmado por la propia API de Vertex AI en producción
# (S040, no documentado con este detalle en la guía general de
# tamaños en línea): un PDF no puede superar 52428800 bytes (50 MiB)
# aunque se referencie por gs:// -- distinto del límite genérico de
# 100 MB de datos en línea. Umbral propio con margen de seguridad
# (45 MB) para decidir cuándo hace falta recortar antes de llamar.
_PDF_SIZE_LIMIT_BYTES = 45 * 1024 * 1024
_PDF_CLASSIFICATION_MAX_PAGES = 3


_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {"type": "string", "enum": ["MACHINE", "PERSONAL", "DESCONOCIDO"]},
        "document_type_code": {"type": "string"},
        "confidence": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
        "reasoning": {"type": "string"},
        "machine_code_hint": {"type": "string"},
        "brand_model_hint": {"type": "string"},
        "first_surname_hint": {"type": "string"},
        "second_surname_hint": {"type": "string"},
        "given_name_hint": {"type": "string"},
        "dni_hint": {"type": "string"},
        "date_hint": {"type": "string"},
    },
    "required": [
        "domain", "document_type_code", "confidence", "reasoning",
        "machine_code_hint", "brand_model_hint",
        "first_surname_hint", "second_surname_hint",
        "given_name_hint", "dni_hint", "date_hint",
    ],
}

_PROMPT_TEMPLATE = """Eres un clasificador de documentación administrativa de una empresa \
española de grúas y maquinaria pesada. Se te da UN documento (PDF), y debes \
identificar su tipo dentro de una lista CERRADA de tipos posibles -- nunca \
inventes un tipo fuera de esta lista, ni renombres uno existente con tus \
propias palabras.

{domain_instruction}

TIPOS DE DOCUMENTO POSIBLES (código -- descripción):
{catalog_lines}

Si el documento no encaja claramente en ninguno de los tipos anteriores, \
usa el código "DESCONOCIDO" y explica por qué en "reasoning".

Además del tipo, extrae estas pistas SI aparecen de forma clara en el propio \
documento (deja la cadena vacía "" si no aparecen -- nunca inventes un valor):
- machine_code_hint: el código interno de flota o la matrícula de la \
máquina/vehículo (solo si el dominio es de máquina) -- casi siempre con \
forma "LETRA-NÚMERO" (p. ej. "A-29") y/o una matrícula española \
("E-0356-BBZ", "1532-DVF"). NUNCA el "Tipo"/modelo/denominación \
comercial que dé el FABRICANTE (p. ej. "AT-35/32" en una Declaración \
CE es el modelo del fabricante, no el código de flota -- ignóralo para \
este campo aunque sea el dato más visible del documento). Si el \
documento no deja claro cuál es el código de flota/matrícula real, \
deja el campo vacío en vez de usar el modelo del fabricante.
- brand_model_hint: la MARCA y el MODELO del fabricante que diga el propio \
documento (solo si el dominio es de máquina) -- p. ej. "LUNA AT-35/32", \
"LIEBHERR LTM 1055". Aquí SÍ interesa exactamente el dato que se ignora \
para machine_code_hint -- sirve para comprobar después, por otra vía, que \
el documento corresponde de verdad a la máquina de la carpeta donde está \
archivado.
- first_surname_hint, second_surname_hint, given_name_hint, dni_hint: \
primer apellido, segundo apellido, nombre de pila y DNI/NIE de la persona a \
la que se refiere el documento (solo si el dominio es de personal). Si el \
documento es un DNI o un informe de la Seguridad Social, estos son \
exactamente los campos que aparecen impresos en él. El DNI es el dato más \
fiable de los cuatro para identificar a la persona sin ambigüedad -- \
extráelo siempre que aparezca, aunque también extraigas el nombre. Si el \
documento menciona a VARIAS personas distintas por igual (un listado, una \
declaración con varios trabajadores...), extrae los datos de la persona más \
prominente y dilo explícitamente en "reasoning" -- eso indica que el \
archivo podría contener a más de una persona.
- date_hint: la fecha más relevante del documento para decidir cuándo se \
emitió o cuándo caduca (formato AAAA-MM-DD), si se puede leer con claridad.

Responde ÚNICAMENTE el JSON solicitado, sin texto adicional."""

_DOMAIN_LABELS = {
    "MACHINE": "MÁQUINA / VEHÍCULO",
    "PERSONAL": "PERSONAL / TRABAJADOR",
}


def _build_prompt(domain: str | None) -> str:
    """
    Builds the classification prompt. If the domain is already known
    (file living under DOC. MAQUINAS or DOC. PERSONAL), the catalog is
    narrowed to that domain's own codes plus BOTH, and "domain" is
    given as a fact. If the domain is unknown (a quarantine file,
    which is exactly the real use case -- nobody has sorted it yet),
    the full active catalog is listed and Gemini is asked to decide
    the domain too.

    ---

    Construye el prompt de clasificación. Si el dominio ya se conoce
    (archivo que vive bajo DOC. MAQUINAS o DOC. PERSONAL), el catálogo
    se acota a los códigos propios de ese dominio más BOTH, y "domain"
    se da como un hecho. Si el dominio se desconoce (un archivo de
    cuarentena, que es exactamente el caso de uso real -- todavía
    nadie lo ha clasificado), se lista el catálogo activo completo y
    se le pide a Gemini que decida también el dominio.
    """
    if domain:
        catalog_entries = (
            DocumentTypeCatalog.objects
            .filter(is_active=True)
            .filter(domain__in=[domain, DocumentTypeCatalog.DOMAIN_BOTH])
            .order_by("code")
        )
        domain_instruction = (
            "DOMINIO (ya conocido, no lo cambies): %s"
            % _DOMAIN_LABELS.get(domain, domain)
        )
    else:
        catalog_entries = (
            DocumentTypeCatalog.objects.filter(is_active=True).order_by("code")
        )
        domain_instruction = (
            "DOMINIO: desconocido -- decide tú si el documento es de "
            "MÁQUINA/VEHÍCULO o de PERSONAL/TRABAJADOR y ponlo en el campo "
            "\"domain\" (\"MACHINE\" o \"PERSONAL\"; \"DESCONOCIDO\" solo si "
            "de verdad no se puede determinar)."
        )
    catalog_lines = "\n".join(
        "- %s -- %s" % (entry.code, entry.label) for entry in catalog_entries
    )
    return _PROMPT_TEMPLATE.format(
        domain_instruction=domain_instruction, catalog_lines=catalog_lines,
    )


def _generate_content_with_retry(client, **kwargs):
    """
    Same retry pattern already validated in
    `ai_services.document_vision_service._generate_content_with_retry`
    (proactive rate-limit slot + up to 3 attempts on a Vertex AI 429),
    kept local to this app instead of importing that module's private
    helper across app boundaries.

    ---

    Mismo patrón de reintento ya validado en
    `ai_services.document_vision_service._generate_content_with_retry`
    (slot de límite de tasa proactivo + hasta 3 intentos ante un 429 de
    Vertex AI), mantenido local a esta app en vez de importar el
    auxiliar privado de ese módulo cruzando el límite entre apps.
    """
    last_exc = None
    for attempt in range(1, _MAX_GEMINI_ATTEMPTS + 1):
        acquire_gemini_slot()
        try:
            return client.models.generate_content(**kwargs)
        except Exception as exc:
            last_exc = exc
            exc_str = str(exc)
            is_quota_error = (
                "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str
            )
            if not is_quota_error or attempt == _MAX_GEMINI_ATTEMPTS:
                raise
            logger.warning(
                "# [classification_service] 429 de Vertex AI "
                "(intento %d/%d). Reintentando en %ds.",
                attempt, _MAX_GEMINI_ATTEMPTS, _RETRY_DELAY_SECONDS,
            )
            time.sleep(_RETRY_DELAY_SECONDS)
    raise last_exc  # pragma: no cover -- inalcanzable


def domain_for_entry(entry) -> str | None:
    """
    Best-effort domain guess from the entry's own folder, for files
    that already live under a known root (DOC. MAQUINAS/DOC.
    PERSONAL). Returns None for anything else (quarantine, other
    buckets) -- callers pass that straight through to `classify_entry`,
    which then asks Gemini to determine the domain too.

    ---

    Estimación del dominio a partir de la propia carpeta de la
    entrada, para archivos que ya viven bajo una raíz conocida (DOC.
    MAQUINAS/DOC. PERSONAL). Devuelve None para cualquier otro caso
    (cuarentena, otros cubos) -- quien llama lo pasa tal cual a
    `classify_entry`, que entonces le pide a Gemini que determine
    también el dominio.
    """
    if entry.blob_name.startswith("DOC. MAQUINAS/"):
        return DocumentTypeCatalog.DOMAIN_MACHINE
    if entry.blob_name.startswith("DOC. PERSONAL/"):
        return DocumentTypeCatalog.DOMAIN_PERSONAL
    return None


# Un segmento de carpeta empieza por el código de flota si arranca con
# letra(s) + guion opcional + dígitos, tal como usa fleet.MachineAsset.code
# (S040: "A54, Z45, B27") y como se ve en las rutas reales del explorador
# ("A-29 E-0356-BBZ (GR)/A-29").
_FOLDER_MACHINE_CODE_RE = re.compile(r"^([A-Z]+-?\d+)")


def resolve_machine_asset(entry) -> MachineAsset | None:
    """
    Best-effort lookup of the real `fleet.MachineAsset` a MACHINE-domain
    file's folder belongs to, by scanning `parent_path` segments for
    something matching a fleet code and querying `MachineAsset.code`
    (dashes stripped, case-insensitive -- folders write "A-29", the
    fleet catalogue writes "A29"). Read-only, `fleet` (H12) is live
    production infrastructure, not H17-H25 -- safe to query per the
    H29 annex 3.15 isolation rule, which only excludes
    document_ingestion/entity_matching_service/machine_documents/
    personal_documents.

    Returns None if nothing in the path matches any real machine --
    callers must treat that as "can't check", never as "no mismatch".

    ---

    Búsqueda de mejor esfuerzo del `fleet.MachineAsset` real al que
    pertenece la carpeta de un archivo de dominio MÁQUINA, recorriendo
    los segmentos de `parent_path` en busca de algo con forma de código
    de flota y consultando `MachineAsset.code` (sin guiones, sin
    distinguir mayúsculas -- las carpetas escriben "A-29", el catálogo
    de flota escribe "A29"). Solo lectura, `fleet` (H12) es
    infraestructura viva en producción, no H17-H25 -- consultarlo es
    seguro según la regla de aislamiento 3.15 del anexo H29, que solo
    excluye document_ingestion/entity_matching_service/
    machine_documents/personal_documents.

    Devuelve None si nada en la ruta coincide con ninguna máquina real
    -- quien llama debe tratarlo como "no se puede comprobar", nunca
    como "no hay discrepancia".
    """
    for segment in entry.parent_path.split("/"):
        match = _FOLDER_MACHINE_CODE_RE.match(segment.strip())
        if not match:
            continue
        candidate_code = match.group(1).replace("-", "")
        asset = MachineAsset.objects.filter(code__iexact=candidate_code).first()
        if asset:
            return asset
    return None


_DNI_NORMALIZE_RE = re.compile(r"[^A-Z0-9]")

# Letra de control real del DNI/NIE español -- algoritmo público y
# determinista (los 8 dígitos, en NIE con la letra inicial sustituida
# por 0/1/2, módulo 23, indexan esta tabla). Confirmado con datos
# reales, S040: Gemini leyó "25902678A" para un documento cuyo DNI
# real (verificado con 5 documentos distintos de la misma persona,
# más el propio DNI escaneado) es "24902678A" -- "25902678A" no pasa
# esta comprobación (letra esperada "D", no "A"), así que ni siquiera
# hacía falta abrir el documento para descartarlo.
_DNI_CHECK_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_NIE_PREFIX_DIGIT = {"X": "0", "Y": "1", "Z": "2"}


def _normalize_dni(raw_dni: str) -> str:
    return _DNI_NORMALIZE_RE.sub("", raw_dni.upper())


def is_valid_spanish_dni(raw_dni: str) -> bool:
    """
    Validates a Spanish DNI/NIE by its real, public check-letter
    algorithm -- purely arithmetic, no network call, no Gemini,
    catches a misread digit for free. A `dni_hint` that fails this
    can never be a real DNI, so it is rejected before ever reaching
    `PersonIdentity` -- see module-level note above for the real case
    that motivated this (S040).

    ---

    Valida un DNI/NIE español con su algoritmo real y público de letra
    de control -- puramente aritmético, sin llamada de red, sin
    Gemini, detecta gratis un dígito mal leído. Un `dni_hint` que no
    pasa esto nunca puede ser un DNI real, así que se rechaza antes de
    llegar siquiera a `PersonIdentity` -- ver la nota a nivel de
    módulo más arriba para el caso real que motivó esto (S040).
    """
    value = _normalize_dni(raw_dni)
    if len(value) != 9:
        return False
    digits_part, letter = value[:8], value[8]
    if not letter.isalpha():
        return False
    first_char = digits_part[0]
    if first_char in _NIE_PREFIX_DIGIT:
        digits_part = _NIE_PREFIX_DIGIT[first_char] + digits_part[1:]
    if not digits_part.isdigit():
        return False
    return letter == _DNI_CHECK_LETTERS[int(digits_part) % 23]


def resolve_person_identity(dni_hint: str) -> PersonIdentity | None:
    """
    Looks up `PersonIdentity` by a normalized `dni_hint`. A DNI is a
    hard identifier (unlike a name -- H28 annex, Hallazgo 5: the same
    operator's name spelled eight different ways) so an exact match
    here is trustworthy enough to override whatever Gemini read off
    one particular document, same principle already applied to
    machine code (`resolve_machine_asset`, H29 3.27).

    Rejects a `dni_hint` that fails `is_valid_spanish_dni()` before
    ever querying -- a real Gemini misread (S040) is caught for free,
    arithmetically, without needing the document open.

    Returns None both when `dni_hint` is empty/invalid/unreadable and
    when no `PersonIdentity` has been seeded for it yet
    (`seed_person_identities` hasn't classified that person's DNI, or
    never will if their DNI was never uploaded) -- callers must treat
    all these cases the same way: "cannot resolve", never guess a
    folder from the name alone.

    ---

    Busca `PersonIdentity` por un `dni_hint` normalizado. Un DNI es un
    identificador duro (a diferencia de un nombre -- anexo H28,
    Hallazgo 5: el nombre del mismo operario escrito de ocho formas
    distintas), así que una coincidencia exacta aquí es suficientemente
    fiable para prevalecer sobre lo que Gemini haya leído en un
    documento concreto -- mismo principio ya aplicado al código de
    máquina (`resolve_machine_asset`, H29 3.27).

    Rechaza un `dni_hint` que no pase `is_valid_spanish_dni()` antes
    siquiera de consultar -- una lectura errónea real de Gemini (S040)
    se detecta gratis, aritméticamente, sin necesitar el documento
    abierto.

    Devuelve None tanto cuando `dni_hint` está vacío/inválido/ilegible
    como cuando todavía no se ha sembrado ningún `PersonIdentity` para
    él (`seed_person_identities` no ha clasificado el DNI de esa
    persona todavía, o nunca lo hará si su DNI nunca se subió) -- quien
    llama debe tratar todos estos casos igual: "no se puede resolver",
    nunca adivinar una carpeta solo por el nombre.
    """
    dni_hint = (dni_hint or "").strip()
    if not dni_hint or not is_valid_spanish_dni(dni_hint):
        return None
    return PersonIdentity.objects.filter(dni=_normalize_dni(dni_hint)).first()


def check_machine_mismatch(entry, result: dict) -> str | None:
    """
    Compares Gemini's `brand_model_hint` against the REAL brand/model
    of the machine whose folder this file lives in (via
    `resolve_machine_asset`) -- Miguel Ángel, S040: "cuando ese
    documento (...) se encuentra en (...) resulta que es una Liebherr.
    Y ahora nos encontramos que es una Liebherr y nos encontramos un
    documento que dice que es la Luna modelo tal. Error. Tiene que
    avisar." Deliberately NOT the same check as `machine_code_hint`
    (that one is about which fleet code the document names, already
    fixed to ignore the manufacturer's own model -- this one is about
    whether the manufacturer's own model, which the document DOES
    genuinely carry, matches the folder it's filed under).

    Compares only the first word (the brand) case-insensitively --
    deliberately coarse. A mismatched model within the same brand
    ("LUNA GT-60/42" filed under a "LUNA AT-35/32" machine) is far more
    likely to be a real variant/typo than a genuinely wrong machine;
    a mismatched BRAND ("LUNA" vs "LIEBHERR") is the case Miguel Ángel
    described and is safe to flag automatically without false
    positives from minor model-string differences.

    Returns a warning string when brands clearly differ, or None when
    there's nothing to flag (hint missing, asset not resolved, or
    brands match) -- callers must never escalate None into a warning.

    ---

    Compara el `brand_model_hint` de Gemini contra la marca/modelo REAL
    de la máquina de la carpeta donde vive el archivo (vía
    `resolve_machine_asset`) -- Miguel Ángel, S040: "cuando ese
    documento (...) se encuentra en (...) resulta que es una Liebherr.
    Y ahora nos encontramos que es una Liebherr y nos encontramos un
    documento que dice que es la Luna modelo tal. Error. Tiene que
    avisar." Deliberadamente NO es la misma comprobación que
    `machine_code_hint` (esa es sobre qué código de flota nombra el
    documento, ya corregida para ignorar el modelo propio del
    fabricante -- esta es sobre si el modelo propio del fabricante, que
    el documento SÍ lleva de verdad, coincide con la carpeta donde está
    archivado).

    Compara solo la primera palabra (la marca) sin distinguir
    mayúsculas -- deliberadamente basto. Un modelo distinto dentro de
    la misma marca ("LUNA GT-60/42" archivado bajo una máquina "LUNA
    AT-35/32") es mucho más probable que sea una variante/errata real
    que una máquina genuinamente equivocada; una MARCA distinta ("LUNA"
    frente a "LIEBHERR") es el caso que describió Miguel Ángel y es
    seguro avisar automáticamente sin falsos positivos por pequeñas
    diferencias en la cadena del modelo.

    Devuelve una cadena de aviso cuando las marcas difieren claramente,
    o None cuando no hay nada que señalar (falta la pista, no se pudo
    resolver la máquina, o las marcas coinciden) -- quien llama nunca
    debe convertir None en un aviso.
    """
    brand_model_hint = (result.get("brand_model_hint") or "").strip()
    if not brand_model_hint:
        return None
    asset = resolve_machine_asset(entry)
    if not asset or not asset.brand_model:
        return None

    hint_brand = brand_model_hint.split()[0].upper()
    real_brand = asset.brand_model.split()[0].upper()
    if hint_brand == real_brand:
        return None

    return (
        "⚠️ Posible documento archivado en la máquina equivocada -- el "
        "documento dice ser de «%s», pero la máquina de esta carpeta "
        "(%s) es «%s»." % (brand_model_hint, asset.code, asset.brand_model)
    )


def _extract_first_pages_pdf(
    content_bytes: bytes, max_pages: int = _PDF_CLASSIFICATION_MAX_PAGES,
) -> bytes | None:
    """
    Extracts the first `max_pages` of a PDF into a new, small,
    in-memory PDF -- for classification purposes only, never
    persisted anywhere. Real incident, S040: several genuine catalogs
    of spare parts (150-270 MB) hit Vertex AI's real, documented PDF
    limit (`52428800` bytes, 50 MiB) even referenced by `gs://` URI
    (`Part.from_uri`) -- confirmed directly by the API's own error
    message, not assumed. Since classification only needs to
    recognise WHAT KIND of document this is (cover page, title,
    header), not transcribe the whole thing, the first few pages are
    enough -- almost always dramatically smaller than the full file.

    Uses PyMuPDF (`fitz`), already a project dependency -- no new
    package needed, no `pip-compile`/`pip-sync` coordination required.

    Returns None on any failure (corrupt PDF, etc.) -- callers must
    fall back to the "unsupported"/error path, never guess.

    ---

    Extrae las primeras `max_pages` de un PDF a un PDF nuevo, pequeño,
    en memoria -- solo para clasificar, nunca se persiste en ningún
    sitio. Incidente real, S040: varios catálogos de piezas reales
    (150-270 MB) chocaban con el límite real y documentado de Vertex
    AI para PDF (`52428800` bytes, 50 MiB) incluso referenciados por
    URI `gs://` (`Part.from_uri`) -- confirmado directamente por el
    propio mensaje de error de la API, no supuesto. Como clasificar
    solo necesita reconocer DE QUÉ TIPO es el documento (portada,
    título, cabecera), no transcribirlo entero, las primeras páginas
    bastan -- casi siempre mucho más pequeñas que el archivo completo.

    Usa PyMuPDF (`fitz`), ya dependencia del proyecto -- ningún
    paquete nuevo, ninguna coordinación de `pip-compile`/`pip-sync`
    necesaria.

    Devuelve None ante cualquier fallo (PDF corrupto, etc.) -- quien
    llama debe caer al camino de "no soportado"/error, nunca adivinar.
    """
    try:
        source = fitz.open(stream=content_bytes, filetype="pdf")
        try:
            excerpt = fitz.open()
            page_count = min(max_pages, source.page_count)
            excerpt.insert_pdf(source, from_page=0, to_page=page_count - 1)
            return excerpt.tobytes()
        finally:
            source.close()
    except Exception as exc:
        logger.warning(
            "# [_extract_first_pages_pdf] Fallo extrayendo páginas: %s",
            exc, exc_info=True,
        )
        return None


def _convert_to_pdf(content_bytes: bytes, extension: str) -> bytes | None:
    """
    Converts an Office document to PDF using LibreOffice headless
    (`soffice`), confirmed installed on the server (`/usr/bin/soffice`,
    6.4.7.2) before writing this function -- never assumed. Purely
    in-memory from the caller's point of view: writes to a throwaway
    temp directory, reads the resulting PDF bytes back, and deletes
    everything before returning. **Never touches GCS** -- the
    converted PDF exists only long enough to hand to Gemini, per the
    same "clasificar nunca toca GCS" rule as the rest of this module
    (H29 annex 3.19); it is not a new document, just a disposable
    intermediate for reading content Gemini can't read natively.

    Runs with `-env:UserInstallation=file://<tmp>` pointing at its own
    throwaway LibreOffice profile directory -- avoids the well-known
    "user installation is locked" failure if two conversions ever ran
    at once (today's Celery worker has concurrency=1, so this is
    precautionary, not currently load-bearing).

    Returns None on any failure (timeout, `soffice` missing, corrupt
    input, unexpected output) -- callers must fall back to the
    "unsupported" error path, never guess or retry silently.

    ---

    Convierte un documento de Office a PDF con LibreOffice headless
    (`soffice`), confirmado instalado en el servidor
    (`/usr/bin/soffice`, 6.4.7.2) antes de escribir esta función --
    nunca asumido. Puramente en memoria desde el punto de vista de
    quien llama: escribe en un directorio temporal desechable, lee de
    vuelta los bytes del PDF resultante, y borra todo antes de
    devolver. **Nunca toca GCS** -- el PDF convertido existe solo el
    tiempo necesario para dárselo a Gemini, según la misma regla de
    "clasificar nunca toca GCS" que el resto de este módulo (anexo H29
    3.19); no es un documento nuevo, solo un intermedio desechable
    para leer contenido que Gemini no sabe leer de forma nativa.

    Corre con `-env:UserInstallation=file://<tmp>` apuntando a su
    propio perfil desechable de LibreOffice -- evita el fallo conocido
    de "user installation is locked" si alguna vez corrieran dos
    conversiones a la vez (el worker Celery de hoy tiene
    concurrency=1, así que esto es precautorio, no necesario todavía).

    Devuelve None ante cualquier fallo (timeout, falta `soffice`,
    entrada corrupta, salida inesperada) -- quien llama debe caer al
    camino de "no soportado", nunca adivinar ni reintentar en
    silencio.
    """
    with tempfile.TemporaryDirectory() as workdir:
        input_path = os.path.join(workdir, "input." + extension)
        profile_dir = os.path.join(workdir, "profile")
        with open(input_path, "wb") as f:
            f.write(content_bytes)
        try:
            subprocess.run(
                [
                    "soffice", "--headless", "--norestore",
                    "-env:UserInstallation=file://%s" % profile_dir,
                    "--convert-to", "pdf", "--outdir", workdir, input_path,
                ],
                check=True, timeout=_SOFFICE_TIMEOUT_SECONDS,
                capture_output=True,
            )
        except Exception as exc:
            logger.warning(
                "# [_convert_to_pdf] Fallo convirtiendo .%s a PDF: %s",
                extension, exc, exc_info=True,
            )
            return None

        output_path = os.path.join(workdir, "input.pdf")
        if not os.path.exists(output_path):
            logger.warning(
                "# [_convert_to_pdf] soffice terminó sin error pero no "
                "generó input.pdf para .%s", extension,
            )
            return None
        with open(output_path, "rb") as f:
            return f.read()


def classify_entry(entry, domain: str | None = None) -> dict:
    """
    Downloads the real object content from GCS and asks Gemini to
    suggest a `DocumentTypeCatalog.code` plus a handful of hint
    fields. Never raises to the caller -- any failure comes back as a
    dict with `error` set, since this is meant to run over a batch
    where one bad file must not abort the rest.

    `domain` is optional -- pass it when already known (narrows the
    catalog, more accurate); leave it out for quarantine files, where
    Gemini determines the domain itself as part of the same call.

    Office documents (`.docx`/`.xlsx`/`.pptx`/...) are converted to
    PDF first via `_convert_to_pdf()` -- Gemini's own mimeType
    allow-list doesn't cover Office formats directly (see
    `_SUPPORTED_MIME_TYPES`'s docstring). Only the converted PDF bytes
    are sent to Gemini; nothing about the conversion is persisted
    anywhere.

    For file types Gemini already accepts natively (PDF, images...),
    this never downloads the object at all -- it hands Gemini a
    direct `gs://` reference (`Part.from_uri`, confirmed supported on
    Vertex AI with no inline-payload size ceiling) instead of
    `Part.from_bytes`. Real incident, S040: several genuine spare-parts
    catalog PDFs (150-270 MB) failed with a raw 400 INVALID_ARGUMENT
    from Vertex AI -- verified online against current Gemini docs
    (2026-08-04) that the inline payload limit is 100 MB, well under
    these files' real size. Office documents still need a real
    download (LibreOffice can't convert a `gs://` URI), so that path
    is unchanged.

    ---

    Descarga el contenido real del objeto desde GCS y pide a Gemini
    que sugiera un `DocumentTypeCatalog.code` más un puñado de campos
    de pista. Nunca lanza excepción a quien llama -- cualquier fallo
    vuelve como un dict con `error` puesto, porque esto está pensado
    para correr sobre un lote donde un archivo malo no debe abortar el
    resto.

    `domain` es opcional -- se pasa cuando ya se conoce (acota el
    catálogo, más preciso); se omite para archivos de cuarentena,
    donde Gemini determina el propio dominio como parte de la misma
    llamada.

    Los documentos de Office (`.docx`/`.xlsx`/`.pptx`/...) se
    convierten primero a PDF vía `_convert_to_pdf()` -- la lista de
    mimeTypes que acepta Gemini no cubre Office directamente (ver el
    docstring de `_SUPPORTED_MIME_TYPES`). Solo los bytes del PDF
    convertido se envían a Gemini; nada de la conversión se persiste
    en ningún sitio.

    Para los tipos que Gemini ya acepta de forma nativa (PDF,
    imágenes...), esto nunca descarga el objeto -- le pasa a Gemini
    una referencia `gs://` directa (`Part.from_uri`, confirmado
    soportado en Vertex AI sin techo de tamaño de payload en línea) en
    vez de `Part.from_bytes`. Incidente real, S040: varios catálogos
    de piezas reales (150-270 MB) fallaban con un 400 INVALID_ARGUMENT
    en crudo de Vertex AI -- verificado online contra la documentación
    real de Gemini (2026-08-04) que el límite de payload en línea es
    100 MB, muy por debajo del tamaño real de estos archivos. Los
    documentos de Office siguen necesitando descarga real (LibreOffice
    no puede convertir una URI `gs://`), así que ese camino no cambia.
    """
    import json

    mime_type = entry.content_type or "application/pdf"
    extension = entry.name.rsplit(".", 1)[-1].lower() if "." in entry.name else ""

    try:
        if mime_type in _SUPPORTED_MIME_TYPES:
            if (
                mime_type == "application/pdf"
                and entry.size_bytes
                and entry.size_bytes > _PDF_SIZE_LIMIT_BYTES
            ):
                # Incidente real S040: Vertex AI rechaza cualquier PDF
                # de más de 52428800 bytes (50 MiB) para clasificar,
                # aunque se referencie por gs:// -- confirmado por el
                # propio mensaje de error de la API. entry.size_bytes
                # ya está en el índice, así que se decide sin
                # descargar nada de más.
                content_bytes = download_bytes(entry.bucket, entry.blob_name)
                excerpt = _extract_first_pages_pdf(content_bytes)
                if excerpt is None:
                    return {
                        "error": (
                            "El PDF supera el límite de 50 MB de "
                            "Vertex AI y no se pudieron extraer las "
                            "primeras páginas para clasificarlo "
                            "igualmente (ver logs del servidor)."
                        ),
                    }
                file_part = Part.from_bytes(
                    data=excerpt, mime_type="application/pdf",
                )
            else:
                file_part = Part.from_uri(
                    file_uri="gs://%s/%s" % (entry.bucket, entry.blob_name),
                    mime_type=mime_type,
                )
        else:
            if extension not in _LIBREOFFICE_CONVERTIBLE_EXTENSIONS:
                return {
                    "error": (
                        "Tipo de archivo no soportado para clasificación "
                        "con Gemini (%s) y sin conversión conocida para "
                        "la extensión .%s." % (mime_type, extension)
                    ),
                }
            content_bytes = download_bytes(entry.bucket, entry.blob_name)
            converted = _convert_to_pdf(content_bytes, extension)
            if converted is None:
                return {
                    "error": (
                        "No se pudo convertir .%s a PDF con LibreOffice "
                        "para poder clasificarlo (ver logs del servidor "
                        "para el detalle)." % extension
                    ),
                }
            file_part = Part.from_bytes(data=converted, mime_type="application/pdf")

        client = get_gemini_client()
        response = _generate_content_with_retry(
            client,
            model=DEFAULT_MODEL,
            contents=[file_part, _build_prompt(domain)],
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=90_000),
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0.0,
            ),
        )
        return json.loads(response.text.strip())
    except Exception as exc:
        logger.warning(
            "# [classify_entry] Fallo clasificando %s: %s",
            entry.blob_name, exc, exc_info=True,
        )
        return {"error": str(exc)}


def _resolve_date(entry, result) -> datetime.date:
    """
    Real date extracted by Gemini when available (`date_hint`,
    AAAA-MM-DD); falls back to the object's own GCS modification date,
    and only then to today -- never blocks naming just because the
    document itself didn't carry a readable date.

    ---

    Fecha real extraída por Gemini cuando está disponible
    (`date_hint`, AAAA-MM-DD); si no, cae en la fecha de modificación
    propia del objeto en GCS, y solo entonces en hoy -- nunca bloquea
    el nombrado solo porque el documento en sí no traía una fecha
    legible.
    """
    date_hint = (result.get("date_hint") or "").strip()
    if date_hint:
        try:
            return datetime.date.fromisoformat(date_hint)
        except ValueError:
            pass
    if entry.gcs_updated_at:
        return entry.gcs_updated_at.date()
    return datetime.date.today()


def build_new_name(
    entry, domain: str, result: dict, ordinal: int | None = None,
) -> str | None:
    """
    Build the virtual filename `naming_service` would produce from a
    Gemini suggestion, or None when there isn't enough to go on
    (unknown type, or missing the field the chosen domain's format
    requires) -- callers must treat None as "leave this one for manual
    review", never invent a placeholder.

    `ordinal` is forwarded to `naming_service` as-is -- Miguel Ángel's
    own format ("...tipo de documento, y fecha y ordinal por si hay
    varios documentos que se llamen igual") already has a place for
    it; a collision must never be resolved by bolting move_service's
    " (N)" suffix on top of a name this function already built in a
    different, fixed format.

    ---

    Construye el nombre de archivo virtual que produciría
    `naming_service` a partir de una sugerencia de Gemini, o None
    cuando no hay suficiente con qué construirlo (tipo desconocido, o
    falta el campo que exige el formato de ese dominio) -- quien llama
    debe tratar None como "dejar este para revisión manual", nunca
    inventar un valor de relleno.

    `ordinal` se reenvía tal cual a `naming_service` -- el propio
    formato de Miguel Ángel ("...tipo de documento, y fecha y ordinal
    por si hay varios documentos que se llamen igual") ya tiene un
    hueco para esto; una colisión nunca debe resolverse pegando el
    sufijo " (N)" de move_service encima de un nombre que esta función
    ya construyó en un formato fijo distinto.
    """
    code = result.get("document_type_code") or ""
    if not code or code == "DESCONOCIDO":
        return None
    extension = entry.name.rsplit(".", 1)[-1] if "." in entry.name else "pdf"
    date = _resolve_date(entry, result)

    if domain == "MACHINE":
        # Corrección S040, misma sesión: para archivos que ya viven en
        # una carpeta de máquina conocida, el código de flota real
        # (resuelto por carpeta, determinista) prevalece siempre sobre
        # lo que Gemini lea dentro del documento -- Gemini no es
        # perfectamente determinista entre llamadas (temperature=0.0
        # no lo garantiza al 100%) y ya se ha visto en producción
        # devolver un código de máquina distinto para el mismo archivo
        # en dos pasadas seguidas. Gemini solo decide el código cuando
        # la carpeta no resuelve a ninguna máquina real -- el caso de
        # cuarentena, que es donde de verdad hace falta que adivine.
        asset = resolve_machine_asset(entry)
        machine_code = (
            asset.code if asset
            else (result.get("machine_code_hint") or "").strip()
        )
        if not machine_code:
            return None
        return naming_service.build_filename_machine(
            machine_code, code, date, ordinal=ordinal, extension=extension,
        )
    if domain == "PERSONAL":
        # Corrección S040, mismo principio que 3.27 para máquina: si
        # el DNI leído en este documento concreto resuelve a una
        # identidad ya sembrada, sus apellidos/nombre canónicos
        # prevalecen sobre lo que Gemini haya leído aquí -- evita que
        # una variante de escritura de este documento (Hallazgo 5)
        # genere un nombre de archivo distinto al resto de documentos
        # de la misma persona.
        identity = resolve_person_identity(result.get("dni_hint"))
        if identity:
            first_surname = identity.first_surname
            second_surname = identity.second_surname
            given_name = identity.given_name
        else:
            first_surname = (result.get("first_surname_hint") or "").strip()
            given_name = (result.get("given_name_hint") or "").strip()
            second_surname = (result.get("second_surname_hint") or "").strip()
        if not first_surname or not given_name:
            return None
        return naming_service.build_filename_personal(
            first_surname, second_surname, given_name, code, date,
            ordinal=ordinal, extension=extension,
        )
    return None


def apply_classification(entry) -> dict:
    """
    Classifies `entry` and, if there was enough to build a proper
    name, applies it -- **virtually only**: writes `DocumentIndexEntry.
    name`, never touches `blob_name` or moves anything in GCS. Miguel
    Ángel, S040: "no vamos a tocar CGS, lo vamos a hacer todo a nivel
    de base de datos (...) al clasificarla le damos el nombre nuevo en
    base de datos."

    `entry.parent_path` is left untouched by this function -- for
    files already living under DOC. MAQUINAS/DOC. PERSONAL this is
    exactly the wanted behaviour (rename in place). Relocating a
    quarantine file into its classified folder virtually is a
    separate, still-unbuilt step (the future always-on task) that will
    reuse `move_service`'s own virtual-relocation machinery, not this
    function.

    Collision-safe: appends the ordinal `naming_service`'s own format
    already has a place for -- never `move_service`'s " (N)" suffix,
    which belongs to a different, unrelated feature (moving files) with
    its own naming convention. Corrected S040 after the first
    controlled test: the original version called
    `move_service._resolve_free_name` directly, which silently produced
    names like `... (1).pdf` instead of Miguel Ángel's own specified
    `..._1.pdf` ordinal.

    Returns the raw Gemini result dict, plus `new_name` (None if
    nothing could be applied), `classified` (bool -- whether a valid
    name could be built at all, true even if it turned out identical
    to the current one) and `renamed` (bool, whether the name
    actually changed). `classified=True, renamed=False` means "already
    had the right name" -- callers must never treat that as a failure.

    ---

    Clasifica `entry` y, si hubo suficiente para construir un nombre
    correcto, lo aplica -- **solo de forma virtual**: escribe
    `DocumentIndexEntry.name`, nunca toca `blob_name` ni mueve nada en
    GCS. Miguel Ángel, S040: "no vamos a tocar CGS, lo vamos a hacer
    todo a nivel de base de datos (...) al clasificarla le damos el
    nombre nuevo en base de datos."

    `entry.parent_path` queda intacto en esta función -- para archivos
    que ya viven bajo DOC. MAQUINAS/DOC. PERSONAL es exactamente el
    comportamiento deseado (renombrar en el sitio). Reubicar
    virtualmente un archivo de cuarentena en su carpeta clasificada es
    un paso aparte, todavía sin construir (la futura tarea always-on)
    que reutilizará la maquinaria de reubicación virtual de
    `move_service`, no esta función.

    A salvo de colisiones: añade el ordinal para el que el propio
    formato de `naming_service` ya tiene hueco -- nunca el sufijo
    " (N)" de `move_service`, que pertenece a otra funcionalidad
    distinta (mover archivos) con su propia convención de nombres.
    Corregido en S040 tras la primera prueba controlada: la versión
    original llamaba directamente a
    `move_service._resolve_free_name`, que generaba en silencio
    nombres tipo `... (1).pdf` en vez del ordinal `..._1.pdf` que
    especificó Miguel Ángel.

    Devuelve el dict de resultado en crudo de Gemini, más `new_name`
    (None si no se pudo aplicar nada) y `renamed` (bool, si el nombre
    cambió de verdad).
    """
    domain = domain_for_entry(entry)
    result = classify_entry(entry, domain)
    if "error" in result:
        result["new_name"] = None
        result["classified"] = False
        result["renamed"] = False
        return result

    result["machine_mismatch_warning"] = check_machine_mismatch(entry, result)

    effective_domain = domain or result.get("domain")
    candidate_name = build_new_name(entry, effective_domain, result)
    if not candidate_name:
        # Bug real S040: esto es un fallo genuino (no hubo suficiente
        # para construir un nombre) -- distinto de "ya tenía el nombre
        # correcto", que es el caso de abajo. Antes de esta corrección
        # los dos caminos devolvían renamed=False y ClassifyView los
        # mostraba igual como "no se pudo aplicar", generando falsos
        # avisos cada vez que se reclasificaba un archivo ya bien
        # nombrado (incidente real: Miguel Ángel repitió la prueba
        # sobre los mismos 21 archivos y la mayoría de los ya
        # correctos salieron como fallo).
        result["new_name"] = None
        result["classified"] = False
        result["renamed"] = False
        return result

    final_name = candidate_name
    ordinal = 1
    while _virtual_location_taken(
        entry.bucket, entry.parent_path, final_name, exclude_pk=entry.pk,
    ):
        final_name = build_new_name(
            entry, effective_domain, result, ordinal=ordinal,
        )
        ordinal += 1

    renamed = final_name != entry.name
    if renamed:
        entry.name = final_name
        entry.save(update_fields=["name", "updated_at"])

    result["new_name"] = final_name
    result["classified"] = True
    result["renamed"] = renamed
    return result


def quarantine_domain_for_entry(entry) -> str | None:
    """
    Domain of a file sitting inside `_CUARENTENA/` -- same rule as
    `domain_for_entry`, but checking the part of `blob_name` AFTER the
    quarantine prefix, since the agent mirrors the original relative
    path underneath it (`_CUARENTENA/DOC. MAQUINAS/...`,
    `h28_migration_agent/uploader.py`'s `build_quarantine_blob_name`).

    ---

    Dominio de un archivo dentro de `_CUARENTENA/` -- misma regla que
    `domain_for_entry`, pero mirando la parte de `blob_name` DESPUÉS
    del prefijo de cuarentena, porque el agente refleja la ruta
    relativa original justo debajo de él
    (`_CUARENTENA/DOC. MAQUINAS/...`, `build_quarantine_blob_name` de
    `h28_migration_agent/uploader.py`).
    """
    relative = entry.blob_name
    if relative.startswith(QUARANTINE_PREFIX):
        relative = relative[len(QUARANTINE_PREFIX):]
    if relative.startswith("DOC. MAQUINAS/"):
        return DocumentTypeCatalog.DOMAIN_MACHINE
    if relative.startswith("DOC. PERSONAL/"):
        return DocumentTypeCatalog.DOMAIN_PERSONAL
    return None


def apply_quarantine_classification(entry) -> dict:
    """
    Full pipeline for ONE quarantine file (H29, S040 -- the "Always-on
    Task que clasifique la cuarentena" of the H29 roadmap, point 2):
    classify, and -- only for MACHINE domain, only when the real
    machine can be resolved with certainty from the mirrored folder
    path already inside quarantine (`resolve_machine_asset`, same as
    3.27) -- relocate it out of quarantine into its real `DOC.
    MAQUINAS` folder, renamed, via `move_service.move_entry()` (pure
    index write, `blob_name` in GCS is never touched, same as every
    other operation in this module).

    PERSONAL domain is classified (the suggested type is recorded)
    but **never relocated automatically** -- Miguel Ángel, S040,
    explicit fallback: "se clasifican todos y los que generen alguna
    duda (...) se marcan como con duda para revisión por un humano."
    `PersonIdentity`-based matching (3.31/3.32) exists to raise
    confidence for a future version of this same pipeline, but this
    function does not yet act on a resolved identity by moving
    anything -- only `build_new_name`'s naming already uses it when
    called from `apply_classification` on files already correctly
    filed. Same caution for MACHINE files whose folder can't be
    resolved: classified, never relocated.

    Returns the same shape as `apply_classification()`
    (`new_name`/`classified`/`renamed`), plus `relocated` (bool -- the
    file's `parent_path` actually changed) and, when relocated,
    `new_parent_path`.

    ---

    Pipeline completo para UN archivo de cuarentena (H29, S040 -- la
    "Always-on Task que clasifique la cuarentena" del punto 2 de la
    hoja de ruta H29): clasifica, y -- solo para dominio MÁQUINA, solo
    cuando la máquina real se puede resolver con certeza a partir de
    la ruta de carpeta ya reflejada dentro de cuarentena
    (`resolve_machine_asset`, igual que 3.27) -- la reubica fuera de
    cuarentena a su carpeta real de `DOC. MAQUINAS`, renombrada, vía
    `move_service.move_entry()` (escritura de índice pura, el
    `blob_name` en GCS nunca se toca, igual que cualquier otra
    operación de este módulo).

    El dominio PERSONAL se clasifica (el tipo sugerido queda
    registrado) pero **nunca se reubica en automático** -- Miguel
    Ángel, S040, red de seguridad explícita: "se clasifican todos y
    los que generen alguna duda (...) se marcan como con duda para
    revisión por un humano." El emparejamiento por `PersonIdentity`
    (3.31/3.32) existe para dar más confianza a una futura versión de
    este mismo pipeline, pero esta función todavía no actúa sobre una
    identidad resuelta moviendo nada -- solo el nombrado de
    `build_new_name` ya la usa cuando se llama desde
    `apply_classification` sobre archivos ya bien archivados. Misma
    cautela para archivos de MÁQUINA cuya carpeta no se pueda
    resolver: se clasifican, nunca se reubican.

    Devuelve la misma forma que `apply_classification()`
    (`new_name`/`classified`/`renamed`), más `relocated` (bool -- si
    el `parent_path` del archivo cambió de verdad) y, cuando se
    reubica, `new_parent_path`.
    """
    domain = quarantine_domain_for_entry(entry)
    result = classify_entry(entry, domain)
    if "error" in result:
        result.update(new_name=None, classified=False, renamed=False, relocated=False)
        return result

    effective_domain = domain or result.get("domain")
    result["machine_mismatch_warning"] = (
        check_machine_mismatch(entry, result)
        if effective_domain == "MACHINE" else None
    )

    if effective_domain != "MACHINE":
        result.update(new_name=None, classified=False, renamed=False, relocated=False)
        return result

    asset = resolve_machine_asset(entry)
    if not asset:
        result.update(new_name=None, classified=False, renamed=False, relocated=False)
        return result

    candidate_name = build_new_name(entry, "MACHINE", result)
    if not candidate_name:
        result.update(new_name=None, classified=False, renamed=False, relocated=False)
        return result

    target_parent_path = entry.parent_path
    if target_parent_path.startswith(QUARANTINE_PREFIX):
        target_parent_path = target_parent_path[len(QUARANTINE_PREFIX):]

    final_name = candidate_name
    ordinal = 1
    while _virtual_location_taken(
        entry.bucket, target_parent_path, final_name, exclude_pk=entry.pk,
    ):
        final_name = build_new_name(
            entry, "MACHINE", result, ordinal=ordinal,
        )
        ordinal += 1

    entry.name = final_name
    move_entry(entry, target_parent_path)

    result["new_name"] = final_name
    result["classified"] = True
    result["renamed"] = True
    result["relocated"] = True
    result["new_parent_path"] = target_parent_path
    return result
