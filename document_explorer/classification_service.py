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

from django.utils import timezone
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
        "domain": {
            "type": "string",
            "enum": ["MACHINE", "PERSONAL", "DESCONOCIDO"],
        },
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
        "is_dossier": {"type": "boolean"},
    },
    "required": [
        "domain", "document_type_code", "confidence", "reasoning",
        "machine_code_hint", "brand_model_hint",
        "first_surname_hint", "second_surname_hint",
        "given_name_hint", "dni_hint", "date_hint", "is_dossier",
    ],
}

_PROMPT_TEMPLATE = """Eres un clasificador de documentación \
administrativa de una empresa \
española de grúas y maquinaria pesada. Se te da UN documento (PDF), y debes \
identificar su tipo dentro de una lista CERRADA de tipos posibles -- nunca \
inventes un tipo fuera de esta lista, ni renombres uno existente con tus \
propias palabras.

{domain_instruction}

TIPOS DE DOCUMENTO POSIBLES (código -- descripción):
{catalog_lines}

Si el documento no encaja claramente en ninguno de los tipos anteriores, \
usa el código "DESCONOCIDO" y explica por qué en "reasoning".

is_dossier: SOLO true cuando tengas la CERTEZA de que el archivo es la \
unión de DOS O MÁS documentos catalogados DISTINTOS, cada uno \
identificable por separado -- por ejemplo: una tarjeta ITV + un permiso \
de circulación; un DNI + un certificado de un curso; un DNI + un permiso \
de conducción. El número de páginas no importa (un dossier puede tener \
tres páginas o quince). NUNCA marques is_dossier=true solo porque el \
documento no encaje en ningún tipo de la lista y por eso uses \
"DESCONOCIDO" -- eso es un documento único que no reconoces, no un \
dossier, y es un caso completamente distinto. Si tienes cualquier duda \
real sobre si es un único documento o varios, usa is_dossier=false -- \
la certeza es obligatoria, la sospecha no basta. Cuando is_dossier=true, \
explica en "reasoning" qué documentos distintos identificaste dentro \
del archivo.

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


# Un TOKEN (palabra) de un segmento de carpeta es un código de flota si
# empieza por letra(s) + guion opcional + dígitos, tal como usa
# fleet.MachineAsset.code (S040: "A54, Z45, B27"). Ancla en el propio
# token, no en el segmento completo -- corrección real S041: algunas
# carpetas escriben el código primero ("A-29 E-0356-BBZ (GR)"), pero
# otras (carretillas/dumpers) escriben antes una palabra descriptiva
# ("CARRETILLA T13 - E-1364-BFL", "DUMPER T27 E-9982-BHD") -- con el
# ancla en el segmento completo esos casos nunca llegaban a probar el
# código real, y el archivo se quedaba sin reubicar aunque el tipo
# documental sí se hubiera identificado con certeza (hallazgo real:
# manuales de despiece correctamente tipificados MANUAL_DESPIECE que
# nunca salían de cuarentena).
_FOLDER_MACHINE_CODE_RE = re.compile(r"^([A-Z]+-?\d+)")


def resolve_machine_asset(entry) -> MachineAsset | None:
    """
    Best-effort lookup of the real `fleet.MachineAsset` a MACHINE-domain
    file's folder belongs to, by scanning every word of every
    `parent_path` segment for something matching a fleet code and
    querying `MachineAsset.code` (dashes stripped, case-insensitive --
    folders write "A-29", the fleet catalogue writes "A29"). Read-only,
    `fleet` (H12) is live production infrastructure, not H17-H25 --
    safe to query per the H29 annex 3.15 isolation rule, which only
    excludes document_ingestion/entity_matching_service/
    machine_documents/personal_documents.

    Word-by-word, not segment-by-segment (S041 fix) -- a segment can
    carry a descriptive word before the real code ("CARRETILLA T13 -
    E-1364-BFL"), and the code is never guaranteed to be the first
    word. A token that merely looks like a code (e.g. a plate,
    "E-1364") but matches no real `MachineAsset` is harmless --
    querying it just returns nothing and scanning continues; only a
    real match short-circuits the search.

    Returns None if nothing in the path matches any real machine --
    callers must treat that as "can't check", never as "no mismatch".

    ---

    Búsqueda de mejor esfuerzo del `fleet.MachineAsset` real al que
    pertenece la carpeta de un archivo de dominio MÁQUINA, recorriendo
    cada palabra de cada segmento de `parent_path` en busca de algo con
    forma de código de flota y consultando `MachineAsset.code` (sin
    guiones, sin distinguir mayúsculas -- las carpetas escriben "A-29",
    el catálogo de flota escribe "A29"). Solo lectura, `fleet` (H12) es
    infraestructura viva en producción, no H17-H25 -- consultarlo es
    seguro según la regla de aislamiento 3.15 del anexo H29, que solo
    excluye document_ingestion/entity_matching_service/
    machine_documents/personal_documents.

    Palabra a palabra, no segmento a segmento (corrección S041) -- un
    segmento puede llevar una palabra descriptiva antes del código real
    ("CARRETILLA T13 - E-1364-BFL"), y el código no siempre es la
    primera palabra. Un token que simplemente parece un código (p. ej.
    una matrícula, "E-1364") pero no coincide con ningún
    `MachineAsset` real es inofensivo -- consultarlo solo devuelve
    nada y la búsqueda continúa; solo una coincidencia real corta la
    búsqueda.

    Devuelve None si nada en la ruta coincide con ninguna máquina real
    -- quien llama debe tratarlo como "no se puede comprobar", nunca
    como "no hay discrepancia".
    """
    for segment in entry.parent_path.split("/"):
        for word in segment.strip().split():
            match = _FOLDER_MACHINE_CODE_RE.match(word)
            if not match:
                continue
            candidate_code = match.group(1).replace("-", "")
            asset = MachineAsset.objects.filter(
                code__iexact=candidate_code,
            ).first()
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


# Categoría de aterrizaje para toda identidad creada de forma
# automática (S041, decisión explícita de Miguel Ángel) -- ningún
# documento dice de forma fiable a cuál de las 13 categorías reales
# bajo DOC. PERSONAL/PERSONAL/ pertenece un trabajador nuevo
# (OPERARIOS, TALLER, ADMINISTRACION...), así que aterriza aquí,
# pendiente de que un humano la mueva a la real con la herramienta de
# mover ya existente.
_NEW_WORKER_STAGING_FOLDER = "DOC. PERSONAL/PERSONAL/PTE CONTRATACION"


def resolve_or_create_person_identity(
    result: dict, entry=None,
) -> PersonIdentity | None:
    """
    Same lookup as `resolve_person_identity()`, extended with two
    more behaviours confirmed explicitly by Miguel Ángel (S041) for
    when the `dni_hint` is well-formed (passes `is_valid_spanish_
    dni()`) but matches no existing `PersonIdentity`:

    1. Checks whether the extracted full name (`first_surname_hint`
       + `second_surname_hint` + `given_name_hint`) matches an
       existing `PersonIdentity` under a DIFFERENT dni. If so, this
       is treated as a suspected DNI misreading (same real-world
       failure mode as `is_valid_spanish_dni`'s own docstring, S040:
       Gemini can misread a digit even on a clear document) --
       NEVER creates a duplicate person for this. Sets
       `result["person_identity_note"]` with both DNIs so a human can
       decide, and returns None (unresolved, stays flagged).
    2. If the name doesn't match anyone either, this is a genuinely
       new worker. Creates a real new `PersonIdentity`, landing under
       `_NEW_WORKER_STAGING_FOLDER` -- verbatim, Miguel Ángel: "hay
       que dotar al sistema de la función de crear ese nuevo
       trabajador, para que tenga su carpeta y su documentación esté
       en su sitio." Sets `result["person_identity_note"]`
       announcing the creation. The file this run is processing gets
       relocated there this same pass, same as any resolved identity.

    Only ever called with a `dni_hint` that already passed
    `is_valid_spanish_dni()` -- an invalid/unreadable DNI never
    reaches here, same caution as `resolve_person_identity`: no name
    or first/given name missing means not enough to safely create
    anyone, returns None without creating.

    ---

    Misma búsqueda que `resolve_person_identity()`, ampliada con dos
    comportamientos más confirmados explícitamente por Miguel Ángel
    (S041) para cuando el `dni_hint` está bien formado (pasa
    `is_valid_spanish_dni()`) pero no coincide con ningún
    `PersonIdentity` existente:

    1. Comprueba si el nombre completo extraído (`first_surname_hint`
       + `second_surname_hint` + `given_name_hint`) coincide con un
       `PersonIdentity` ya existente bajo un DNI DISTINTO. Si es así,
       se trata como sospecha de error de lectura del DNI (mismo
       fallo real ya documentado en el propio docstring de
       `is_valid_spanish_dni`, S040: Gemini puede leer mal un dígito
       incluso en un documento claro) -- NUNCA se crea una persona
       duplicada por esto. Deja `result["person_identity_note"]` con
       los dos DNI para que lo decida un humano, y devuelve None (sin
       resolver, se queda marcado).
    2. Si el nombre tampoco coincide con nadie, es un trabajador
       nuevo de verdad. Crea un `PersonIdentity` real, que aterriza
       en `_NEW_WORKER_STAGING_FOLDER` -- verbatim, Miguel Ángel: "hay
       que dotar al sistema de la función de crear ese nuevo
       trabajador, para que tenga su carpeta y su documentación esté
       en su sitio." Deja `result["person_identity_note"]` anunciando
       la creación. El archivo de esta pasada se reubica ahí mismo,
       igual que con cualquier identidad ya resuelta.

    Solo se llama nunca con un `dni_hint` que ya pasó
    `is_valid_spanish_dni()` -- un DNI inválido/ilegible nunca llega
    aquí, misma cautela que `resolve_person_identity`: sin nombre o
    sin nombre de pila no hay datos suficientes para crear a nadie
    con seguridad, devuelve None sin crear nada.
    """
    dni_hint = (result.get("dni_hint") or "").strip()
    identity = resolve_person_identity(dni_hint)
    if identity:
        return identity
    if not dni_hint or not is_valid_spanish_dni(dni_hint):
        return None

    first_surname = (result.get("first_surname_hint") or "").strip()
    second_surname = (result.get("second_surname_hint") or "").strip()
    given_name = (result.get("given_name_hint") or "").strip()
    if not first_surname or not given_name:
        return None

    name_match = PersonIdentity.objects.filter(
        first_surname__iexact=first_surname,
        given_name__iexact=given_name,
    )
    if second_surname:
        name_match = name_match.filter(second_surname__iexact=second_surname)
    dni = _normalize_dni(dni_hint)
    suspect = name_match.exclude(dni=dni).first()
    if suspect:
        result["person_identity_note"] = (
            "Posible error de lectura del DNI: el nombre coincide "
            "con %s %s, %s (DNI registrado %s), pero este documento "
            "trae %s -- no se crea a nadie nuevo, revisar a mano."
            % (
                suspect.first_surname, suspect.second_surname,
                suspect.given_name, suspect.dni, dni,
            )
        )
        return None

    folder_name = (
        "%s %s, %s" % (first_surname, second_surname, given_name)
        if second_surname
        else "%s, %s" % (first_surname, given_name)
    )
    identity = PersonIdentity.objects.create(
        dni=dni,
        first_surname=first_surname,
        second_surname=second_surname,
        given_name=given_name,
        folder_path="%s/%s" % (_NEW_WORKER_STAGING_FOLDER, folder_name),
        source_entry=entry,
    )
    result["person_identity_note"] = (
        "Trabajador nuevo creado automáticamente (%s, DNI %s) en "
        "PTE CONTRATACION -- pendiente de que un humano lo mueva a "
        "su categoría real." % (folder_name, dni)
    )
    return identity


# Cuenta a cuya papelera van los dossiers eliminados automáticamente
# (H29, S041) -- Miguel Ángel, dato real verificado en base de datos
# (pk=1, único CompanyUser con ese username): "el que va es al mío,
# al de administrador total, el superusuario. Yo soy el único que
# puede recuperar esos archivos." Cuenta compartida del departamento
# de administración, no una cuenta personal -- decisión explícita de
# Miguel Ángel de todos modos, se aplica tal cual.
_DOSSIER_TRASH_USERNAME = "alvarez_admin"


def _resolve_dossier_trash_user():
    """
    Returns the `CompanyUser` to attribute automatic dossier
    deletions to, or None if it can't be resolved (account renamed
    or removed) -- callers must never trash to a null `deleted_by`:
    an orphaned `deleted_at` with no owner is invisible in every
    papelera view (`deleted_by=company_user` filter), unrecoverable
    in practice from the panel -- exactly the "borrado accidental sin
    poder recuperar" H29 exists to prevent.

    ---

    Devuelve el `CompanyUser` al que se atribuyen los borrados
    automáticos de dossiers, o None si no se puede resolver (cuenta
    renombrada o eliminada) -- quien llama nunca debe reubicar a
    papelera con un `deleted_by` nulo: un `deleted_at` huérfano sin
    dueño es invisible en cualquier vista de papelera (filtro
    `deleted_by=company_user`), irrecuperable en la práctica desde el
    panel -- justo el "borrado accidental sin poder recuperar" que
    H29 existe para evitar.
    """
    from ivr_config.models import CompanyUser
    return CompanyUser.objects.select_related("user").filter(
        user__username=_DOSSIER_TRASH_USERNAME,
    ).first()


def trash_dossier_entry(entry) -> bool:
    """
    Soft-deletes `entry` to `_DOSSIER_TRASH_USERNAME`'s papelera --
    pure index write (`deleted_at`/`deleted_by`), `blob_name` in GCS
    never touched, same principle as every other operation in this
    module. Returns False (no-op, entry left untouched) when the
    admin `CompanyUser` can't be resolved -- see
    `_resolve_dossier_trash_user`.

    ---

    Reubica `entry` a la papelera de `_DOSSIER_TRASH_USERNAME` --
    escritura de índice pura (`deleted_at`/`deleted_by`), el
    `blob_name` en GCS nunca se toca, mismo principio que cualquier
    otra operación de este módulo. Devuelve False (no hace nada,
    `entry` queda intacto) cuando no se puede resolver el
    `CompanyUser` administrador -- ver `_resolve_dossier_trash_user`.
    """
    admin = _resolve_dossier_trash_user()
    if admin is None:
        logger.error(
            "# [trash_dossier_entry] No se pudo resolver el "
            "CompanyUser '%s' -- dossier NO eliminado, se deja "
            "clasificado sin aplicar (pk=%d).",
            _DOSSIER_TRASH_USERNAME, entry.pk,
        )
        return False
    entry.deleted_at = timezone.now()
    entry.deleted_by = admin
    entry.save(update_fields=["deleted_at", "deleted_by"])
    return True


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
    extension = (
        entry.name.rsplit(".", 1)[-1].lower()
        if "." in entry.name else ""
    )

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
            file_part = Part.from_bytes(
                data=converted, mime_type="application/pdf",
            )

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

    PERSONAL domain follows the same certainty principle, corrected
    S041 at Miguel Ángel's explicit direction (working copy of the
    Microsoft 365 reality, DB-only operation, low risk -- "vamos a
    hacer ya los movimientos de manera real [en base de datos] (...)
    vamos a ver los resultados y si hay que cambiar algo, se cambia"):
    when the `dni_hint` read off this document resolves to an already
    seeded `PersonIdentity` (`resolve_person_identity()` -- exact DNI
    match, the same hard-identifier principle as `resolve_machine_asset`
    for MACHINE, H29 3.27), it IS relocated out of quarantine into
    `PersonIdentity.folder_path`, renamed via the canonical
    surnames/name on the identity.

    Extended further, same session: a well-formed `dni_hint`
    (`is_valid_spanish_dni()`) matching no existing `PersonIdentity`
    is no longer an automatic dead end --
    `resolve_or_create_person_identity()` checks the extracted name
    against every existing identity first (suspected DNI misreading,
    never a duplicate created) and, only when the name doesn't match
    anyone either, creates a real new worker landing in
    `_NEW_WORKER_STAGING_FOLDER` ("PTE CONTRATACION" -- Miguel Ángel:
    no document reliably says which of the real categories a brand
    new worker belongs to). Either way `result["person_identity_note"]`
    carries the explanation into the audit log detail.

    No identity resolved or created (DNI unreadable, invalid, name
    missing) means the same fallback as before: classified, never
    relocated, left flagged for human review. Same caution for
    MACHINE files whose folder can't be resolved: classified, never
    relocated.

    Before any domain branching -- a file gets ONE more chance to be
    intercepted regardless of domain: when Gemini is CERTAIN the file
    is a composition of two or more distinct catalogued documents
    (`document_type_code == "DESCONOCIDO"` AND `is_dossier` true --
    H29, S041, Miguel Ángel's explicit decision, real examples: an
    ITV card + a permiso de circulación; a DNI + a course
    certificate; a DNI + a driving licence), it is soft-deleted
    straight to `_DOSSIER_TRASH_USERNAME`'s papelera
    (`trash_dossier_entry()`) instead of being left flagged for
    review. `is_dossier` is a certainty signal, never a guess --
    "DESCONOCIDO" alone (couldn't recognise a single document, e.g.
    an uncatalogued type) never triggers this, only stays flagged as
    before.

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

    El dominio PERSONAL sigue el mismo principio de certeza, corregido
    en S041 por indicación explícita de Miguel Ángel (estamos sobre
    una copia de la realidad de Microsoft 365, operación solo de base
    de datos, riesgo bajo -- "vamos a hacer ya los movimientos de
    manera real [en base de datos] (...) vamos a ver los resultados y
    si hay que cambiar algo, se cambia"): cuando el `dni_hint` leído en
    este documento resuelve a un `PersonIdentity` ya sembrado
    (`resolve_person_identity()` -- coincidencia exacta de DNI, mismo
    principio de identificador duro que `resolve_machine_asset` para
    MÁQUINA, H29 3.27), SÍ se reubica fuera de cuarentena a
    `PersonIdentity.folder_path`, renombrada con los apellidos/nombre
    canónicos de la identidad.

    Ampliado más adelante, misma sesión: un `dni_hint` bien formado
    (`is_valid_spanish_dni()`) que no coincide con ningún
    `PersonIdentity` ya no es un callejón sin salida automático --
    `resolve_or_create_person_identity()` primero comprueba el nombre
    extraído contra todas las identidades existentes (sospecha de
    error de lectura del DNI, nunca se crea un duplicado) y, solo
    cuando el nombre tampoco coincide con nadie, crea un trabajador
    nuevo de verdad que aterriza en `_NEW_WORKER_STAGING_FOLDER`
    ("PTE CONTRATACION" -- Miguel Ángel: ningún documento dice de
    forma fiable a cuál de las categorías reales pertenece un
    trabajador recién llegado). En cualquiera de los dos casos,
    `result["person_identity_note"]` lleva la explicación hasta el
    detalle del historial.

    Sin identidad resuelta ni creada (DNI ilegible, inválido, sin
    nombre) se mantiene el mismo fallback de antes: se clasifica,
    nunca se reubica, queda marcado para revisión humana. Misma
    cautela para archivos de MÁQUINA cuya carpeta no se pueda
    resolver: se clasifican, nunca se reubican.

    Antes de cualquier ramificación por dominio -- un archivo tiene
    UNA oportunidad más de ser interceptado sea cual sea su dominio:
    cuando Gemini tiene CERTEZA de que el archivo es la composición
    de dos o más documentos catalogados distintos
    (`document_type_code == "DESCONOCIDO"` Y `is_dossier` cierto --
    H29, S041, decisión explícita de Miguel Ángel, ejemplos reales:
    una tarjeta ITV + un permiso de circulación; un DNI + un
    certificado de curso; un DNI + un permiso de conducción), se
    reubica directamente a la papelera de `_DOSSIER_TRASH_USERNAME`
    (`trash_dossier_entry()`) en vez de quedar marcado para revisión.
    `is_dossier` es una señal de certeza, nunca una sospecha --
    "DESCONOCIDO" a secas (no se reconoce un único documento, p. ej.
    un tipo sin catalogar) nunca dispara esto, sigue quedando
    marcado como antes.

    Devuelve la misma forma que `apply_classification()`
    (`new_name`/`classified`/`renamed`), más `relocated` (bool -- si
    el `parent_path` del archivo cambió de verdad) y, cuando se
    reubica, `new_parent_path`.
    """
    domain = quarantine_domain_for_entry(entry)
    result = classify_entry(entry, domain)
    if "error" in result:
        result.update(
            new_name=None, classified=False,
            renamed=False, relocated=False,
        )
        return result

    if result.get("document_type_code") == "DESCONOCIDO" \
            and result.get("is_dossier"):
        if trash_dossier_entry(entry):
            result.update(
                new_name=None, classified=False,
                renamed=False, relocated=False, trashed=True,
            )
            return result
        result["trashed"] = False

    effective_domain = domain or result.get("domain")
    result["machine_mismatch_warning"] = (
        check_machine_mismatch(entry, result)
        if effective_domain == "MACHINE" else None
    )

    if effective_domain == "PERSONAL":
        identity = resolve_or_create_person_identity(result, entry)
        if not identity:
            result.update(
                new_name=None, classified=False,
                renamed=False, relocated=False,
            )
            return result

        candidate_name = build_new_name(entry, "PERSONAL", result)
        if not candidate_name:
            result.update(
                new_name=None, classified=False,
                renamed=False, relocated=False,
            )
            return result

        target_parent_path = identity.folder_path.strip("/")

        final_name = candidate_name
        ordinal = 1
        while _virtual_location_taken(
            entry.bucket, target_parent_path, final_name, exclude_pk=entry.pk,
        ):
            final_name = build_new_name(
                entry, "PERSONAL", result, ordinal=ordinal,
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

    if effective_domain != "MACHINE":
        result.update(
            new_name=None, classified=False,
            renamed=False, relocated=False,
        )
        return result

    asset = resolve_machine_asset(entry)
    if not asset:
        result.update(
            new_name=None, classified=False,
            renamed=False, relocated=False,
        )
        return result

    candidate_name = build_new_name(entry, "MACHINE", result)
    if not candidate_name:
        result.update(
            new_name=None, classified=False,
            renamed=False, relocated=False,
        )
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
