# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_ingestion/entity_matching_service.py
"""
Domain routing + entity matching for automatic folder ingestion (H23
carpeta feature, agreed with Miguel Ángel in S024: "voy a subir una
carpeta [...] vamos a determinar a qué máquina, y en el caso de que
sean trabajadores, a qué trabajador, pertenece la documentación").

This is a PLAIN Python package, not a registered Django app -- it has
no models of its own (same precedent as file_organizer/web_scrapping,
see doc-master-enterprisebot §1.1, "scripts auxiliares independientes"),
it only reads fleet.MachineAsset and ivr_config.CompanyUser, both
already registered apps. Deliberately NOT placed inside
machine_documents or personal_documents: this service crosses BOTH
domains for a single mixed-content folder upload, so it can't
correctly live inside either domain's app without creating a
dependency in the wrong direction (machine_documents importing
personal_documents, or vice versa) -- same modularity premise Miguel
Ángel has repeated this session ("cuanto más modularizado esté todo,
mejor"). Will be reused as-is by the future H27 email ingestion (same
routing problem, different source of PDFs).

Two-call design per document during folder ingestion, by design:
1. classify_and_route() (this module) -- CHEAP routing call: which
   domain (MACHINE/PERSONAL/UNKNOWN) and which identifying hint
   (machine code/plate, worker DNI/name) does this document mention?
2. The domain-specific classify_document() (machine_documents or
   personal_documents, chosen based on step 1's result) -- the FULL
   metadata extraction call, unchanged from the single-machine-upload
   flow.
This is a deliberate departure from the "always one call per document"
principle established in H23 (2026-07-14, PythonAnywhere 5-minute
timeout incident): that principle was about not needing a SECOND call
for the SAME domain's metadata, which still holds (classify_document()
in either domain app is still one call). Routing is a genuinely
different concern (which domain, which entity) that doesn't fit either
domain's response_schema without either bloating both schemas with
fields the other domain never uses, or coupling the two domain
services together -- and since folder ingestion already runs inside an
async Celery task (no wall-clock limit to protect against, same
reasoning that justified async in the first place), the extra call's
cost is a rate-limiter/token consideration, not a timeout risk.

No persistence logic lives here -- this module only classifies and
matches, it never creates a MachineDocument/PersonalDocument row.
That's the job of the batch-upload task (H23 roadmap, still to be
built), which decides what to persist based on this module's output.

---

Enrutado de dominio + matching de entidad para la ingesta automática
de carpeta (funcionalidad de H23, acordada con Miguel Ángel en S024:
"voy a subir una carpeta [...] vamos a determinar a qué máquina, y en
el caso de que sean trabajadores, a qué trabajador, pertenece la
documentación").

Este es un paquete Python PLANO, no una app Django registrada -- no
tiene modelos propios (mismo precedente que file_organizer/
web_scrapping, ver doc-master-enterprisebot §1.1, "scripts auxiliares
independientes"), solo lee fleet.MachineAsset e ivr_config.CompanyUser,
ambas apps ya registradas. Deliberadamente NO se coloca dentro de
machine_documents ni de personal_documents: este servicio cruza AMBOS
dominios para una única subida de carpeta con contenido mixto, así que
no puede vivir correctamente dentro de la app de ningún dominio sin
crear una dependencia en el sentido equivocado (machine_documents
importando personal_documents, o viceversa) -- misma premisa de
modularidad que Miguel Ángel ha repetido esta sesión ("cuanto más
modularizado esté todo, mejor"). Se reutilizará tal cual desde la
futura ingesta de correo de H27 (mismo problema de enrutado, distinto
origen de los PDF).

Diseño de dos llamadas por documento durante la ingesta de carpeta, a
propósito:
1. classify_and_route() (este módulo) -- llamada de enrutado BARATA:
   ¿qué dominio (MACHINE/PERSONAL/UNKNOWN) y qué pista identificativa
   (código/matrícula de máquina, DNI/nombre de trabajador) menciona
   este documento?
2. El classify_document() específico de dominio (machine_documents o
   personal_documents, elegido según el resultado del paso 1) -- la
   llamada de extracción de metadatos COMPLETA, sin cambios respecto
   al flujo de subida de una sola máquina.
Esto es un apartamiento deliberado del principio "siempre una llamada
por documento" establecido en H23 (2026-07-14, incidente de timeout de
5 minutos de PythonAnywhere): ese principio trataba de no necesitar una
SEGUNDA llamada para los metadatos del MISMO dominio, que sigue
vigente (classify_document() en cualquiera de las dos apps de dominio
sigue siendo una sola llamada). El enrutado es un problema realmente
distinto (qué dominio, qué entidad) que no encaja en el
response_schema de ningún dominio sin o bien hinchar ambos schemas con
campos que el otro dominio nunca usa, o bien acoplar los dos servicios
de dominio entre sí -- y como la ingesta de carpeta ya corre dentro de
una tarea Celery asíncrona (sin límite de tiempo del que protegerse,
mismo razonamiento que justificó la asincronía en primer lugar), el
coste de la llamada extra es una cuestión de limitador de tasa/tokens,
no de riesgo de timeout.

Ninguna lógica de persistencia vive aquí -- este módulo solo clasifica
y empareja, nunca crea una fila MachineDocument/PersonalDocument. Esa
es responsabilidad de la tarea de subida en lote (hoja de ruta de H23,
todavía sin construir), que decide qué persistir según lo que devuelva
este módulo.
"""
import json
import logging

from google.genai.types import (
    GenerateContentConfig,
    HttpOptions,
    Part,
    ThinkingConfig,
)

from ai_services.document_vision_service import _generate_content_with_retry
from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain constants -- shared vocabulary between this module and its
# callers (the future batch-upload task) / Constantes de dominio --
# vocabulario compartido entre este módulo y quien lo llame (la futura
# tarea de subida en lote)
# ---------------------------------------------------------------------------

DOMAIN_MACHINE = "MACHINE"
DOMAIN_PERSONAL = "PERSONAL"
DOMAIN_UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Step 1 -- domain + entity-hint routing / Paso 1 -- enrutado de
# dominio + pista de entidad
# ---------------------------------------------------------------------------

_ROUTE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "enum": [DOMAIN_MACHINE, DOMAIN_PERSONAL, DOMAIN_UNKNOWN],
        },
        "machine_reference_hint": {"type": "string"},
        "worker_dni_hint": {"type": "string"},
        "worker_name_hint": {"type": "string"},
        "is_confident": {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
    "required": [
        "domain", "machine_reference_hint", "worker_dni_hint",
        "worker_name_hint", "is_confident", "reasoning",
    ],
}

_ROUTE_PROMPT = """Eres un sistema de enrutado de documentación para una empresa de
servicios de grúa en España. Recibes un documento PDF llamado "{filename}" y
debes determinar a qué DOMINIO pertenece, ANTES de que otro sistema lo
clasifique en detalle.

1. domain: "MACHINE" si el documento es documentación oficial de una
   máquina/vehículo/centro de gasto (ficha técnica, ITV, certificado
   de inspección, seguro de un vehículo, permiso de circulación de un
   vehículo, declaración CE de un equipo). "PERSONAL" si es
   documentación de un trabajador concreto (DNI, contrato, nómina,
   carnet de conducir/grúas A NOMBRE de una persona, reconocimiento
   médico, certificado de curso de formación, entrega de EPI).
   "UNKNOWN" si no puedes determinar el dominio con ninguna confianza
   real.
2. machine_reference_hint: si domain es "MACHINE", el código interno
   o la matrícula de la máquina/vehículo tal como aparece literalmente
   en el documento (ej. "A-45", "E-6998-BDY"). Cadena vacía "" si
   domain no es "MACHINE" o no aparece ninguna referencia reconocible.
3. worker_dni_hint: si domain es "PERSONAL", el DNI/NIF del
   trabajador tal como aparece literalmente en el documento. Cadena
   vacía "" si domain no es "PERSONAL" o no aparece un DNI/NIF
   reconocible.
4. worker_name_hint: si domain es "PERSONAL", el nombre completo del
   trabajador tal como aparece en el documento (útil como respaldo
   cuando no hay DNI legible, ej. un carnet escaneado de baja
   calidad). Cadena vacía "" si domain no es "PERSONAL" o no se
   identifica un nombre.
5. is_confident: true únicamente si domain es "MACHINE" o "PERSONAL"
   Y además hay una pista identificativa (machine_reference_hint o
   worker_dni_hint/worker_name_hint) reconocible en el documento.
   false en cualquier otro caso, incluido cuando el dominio está claro
   pero no hay ninguna pista para identificar a QUÉ máquina o QUÉ
   trabajador concreto pertenece.
6. reasoning: explicación breve (1-2 frases) de la decisión.

Responde únicamente con el JSON solicitado."""


def classify_and_route(pdf_bytes: bytes, filename: str) -> dict:
    """
    First-pass routing call: decides which domain (MACHINE/PERSONAL/
    UNKNOWN) a document belongs to and extracts a raw identifying hint
    (machine code/plate, or worker DNI/name) from its content, WITHOUT
    doing the full domain-specific metadata extraction (that's a
    second call to machine_documents.classify_document() or
    personal_documents.classify_document(), made by the caller based
    on this result).

    Returns a dict with domain (str, one of DOMAIN_MACHINE/
    DOMAIN_PERSONAL/DOMAIN_UNKNOWN), machine_reference_hint (str),
    worker_dni_hint (str), worker_name_hint (str), is_confident (bool)
    and reasoning (str). On any error, returns a conservative fallback
    (domain=DOMAIN_UNKNOWN, is_confident=False) and logs the exception
    -- never raises, callers route unmatched/failed documents to the
    "sin asignar" bucket the same way as a low-confidence result.

    ---

    Llamada de enrutado de primera pasada: decide a qué dominio
    (MACHINE/PERSONAL/UNKNOWN) pertenece un documento y extrae una
    pista identificativa en bruto (código/matrícula de máquina, o
    DNI/nombre de trabajador) de su contenido, SIN hacer la extracción
    de metadatos completa específica de dominio (esa es una segunda
    llamada a machine_documents.classify_document() o
    personal_documents.classify_document(), hecha por quien llama
    según este resultado).

    Devuelve un dict con domain (str, uno de DOMAIN_MACHINE/
    DOMAIN_PERSONAL/DOMAIN_UNKNOWN), machine_reference_hint (str),
    worker_dni_hint (str), worker_name_hint (str), is_confident (bool)
    y reasoning (str). Ante cualquier error, devuelve un fallback
    conservador (domain=DOMAIN_UNKNOWN, is_confident=False) y registra
    la excepción -- nunca lanza, quien llama enruta los documentos sin
    emparejar/fallidos al mismo cajón "sin asignar" que un resultado de
    baja confianza.
    """
    _fallback = {
        "domain": DOMAIN_UNKNOWN,
        "machine_reference_hint": "",
        "worker_dni_hint": "",
        "worker_name_hint": "",
        "is_confident": False,
        "reasoning": "",
    }

    try:
        client = get_gemini_client()
        response = _generate_content_with_retry(
            client,
            model=DEFAULT_MODEL,
            contents=[
                Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                _ROUTE_PROMPT.format(filename=filename),
            ],
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=60_000),
                response_mime_type="application/json",
                response_schema=_ROUTE_RESPONSE_SCHEMA,
                thinking_config=ThinkingConfig(thinking_budget=0),
                temperature=0.0,
            ),
        )

        parsed = json.loads(response.text.strip())
        domain = str(parsed.get("domain", DOMAIN_UNKNOWN)).strip().upper()
        if domain not in (DOMAIN_MACHINE, DOMAIN_PERSONAL, DOMAIN_UNKNOWN):
            domain = DOMAIN_UNKNOWN

        result = {
            "domain": domain,
            "machine_reference_hint": str(
                parsed.get("machine_reference_hint", "")
            ).strip(),
            "worker_dni_hint": str(
                parsed.get("worker_dni_hint", "")
            ).strip(),
            "worker_name_hint": str(
                parsed.get("worker_name_hint", "")
            ).strip(),
            "is_confident": bool(parsed.get("is_confident", False)),
            "reasoning": str(parsed.get("reasoning", "")).strip(),
        }
        logger.info(
            "# [classify_and_route] %s -> dominio=%s confianza=%s "
            "pista_maquina=%r pista_dni=%r pista_nombre=%r",
            filename, result["domain"], result["is_confident"],
            result["machine_reference_hint"], result["worker_dni_hint"],
            result["worker_name_hint"],
        )
        return result

    except Exception as exc:
        logger.error(
            "# [classify_and_route] Error enrutando %s: %s",
            filename, exc, exc_info=True,
        )
        return dict(_fallback)


# ---------------------------------------------------------------------------
# Step 2 -- matching the hint against real DB records / Paso 2 --
# emparejar la pista contra registros reales de BD
# ---------------------------------------------------------------------------
#
# Exact matching only, deliberately -- no fuzzy/similarity matching in
# this first cut. A wrong automatic match (assigning a document to the
# WRONG machine or WRONG worker) is worse than an "unassigned" document
# waiting for a human to confirm, especially for personal_documents
# where the data is sensitive (DNI, health). If exact matching proves
# too strict in practice, loosening it is a follow-up decision to make
# WITH Miguel Ángel, not a silent judgment call here.
# ---
# Emparejamiento exclusivamente exacto, a propósito -- sin matching
# difuso/por similitud en este primer corte. Un emparejamiento
# automático equivocado (asignar un documento a la máquina o el
# trabajador INCORRECTO) es peor que un documento "sin asignar"
# esperando confirmación humana, especialmente en personal_documents,
# donde el dato es sensible (DNI, salud). Si el matching exacto resulta
# demasiado estricto en la práctica, relajarlo es una decisión de
# seguimiento a tomar CON Miguel Ángel, no un criterio unilateral aquí.

def match_machine_asset(company, machine_reference_hint: str):
    """
    Looks up a fleet.MachineAsset by exact match (case-insensitive) of
    its `code` or `plate` against the hint extracted by
    classify_and_route(), scoped to `company`. Returns the matching
    MachineAsset instance, or None if no exact match is found (or the
    hint is empty) -- callers treat None as "route to sin asignar".

    Args:
        company: ivr_config.Company instance to scope the lookup to.
        machine_reference_hint: raw text hint from classify_and_route()
            (machine_reference_hint field).

    ---

    Busca un fleet.MachineAsset por coincidencia exacta (sin distinguir
    mayúsculas/minúsculas) de su `code` o `plate` contra la pista
    extraída por classify_and_route(), acotado a `company`. Devuelve la
    instancia de MachineAsset que coincide, o None si no hay
    coincidencia exacta (o la pista está vacía) -- quien llama trata
    None como "enrutar a sin asignar".

    Args:
        company: instancia de ivr_config.Company a la que acotar la
            búsqueda.
        machine_reference_hint: pista de texto en bruto de
            classify_and_route() (campo machine_reference_hint).
    """
    from fleet.models import MachineAsset

    hint = (machine_reference_hint or "").strip().upper()
    if not hint:
        return None

    match = (
        MachineAsset.objects
        .filter(company=company)
        .filter(models_q_code_or_plate(hint))
        .first()
    )
    if match:
        logger.info(
            "# [match_machine_asset] Pista %r -> MachineAsset #%d (%s).",
            hint, match.pk, match.code,
        )
    else:
        logger.warning(
            "# [match_machine_asset] Pista %r sin coincidencia exacta "
            "en company=%s -- sin asignar.",
            hint, company,
        )
    return match


def models_q_code_or_plate(hint: str):
    """
    Builds the Q() filter for match_machine_asset() -- kept as a
    separate tiny function only so the import of django.db.models.Q
    stays local to this module's single use site (this file otherwise
    has no Django ORM query-building elsewhere), not for reuse.
    ---
    Construye el filtro Q() de match_machine_asset() -- se mantiene
    como función diminuta aparte solo para que el import de
    django.db.models.Q quede local al único sitio de este archivo que
    lo usa (el resto del archivo no construye queries ORM), no para
    reutilización.
    """
    from django.db.models import Q

    return Q(code__iexact=hint) | Q(plate__iexact=hint)


def match_company_user(company, worker_dni_hint: str):
    """
    Looks up an ivr_config.CompanyUser by exact match (case-
    insensitive) of its `dni` field against the hint extracted by
    classify_and_route(), scoped to `company`. Returns the matching
    CompanyUser instance, or None if no exact match is found (or the
    hint is empty) -- callers treat None as "route to sin asignar",
    keeping worker_dni_hint on the created PersonalDocument row
    (detected_dni_hint) for traceability, per PersonalDocument's model
    docstring.

    Deliberately does NOT fall back to matching by worker_name_hint --
    name matching is far more error-prone (spelling variants, common
    surnames) for data this sensitive; the DNI is the only identifier
    trusted for automatic assignment in this first cut. name_hint is
    still captured by classify_and_route() and should be surfaced to
    whoever reviews the "sin asignar" bucket by hand, just never used
    to auto-match.

    Args:
        company: ivr_config.Company instance to scope the lookup to.
        worker_dni_hint: raw text hint from classify_and_route()
            (worker_dni_hint field).

    ---

    Busca un ivr_config.CompanyUser por coincidencia exacta (sin
    distinguir mayúsculas/minúsculas) de su campo `dni` contra la pista
    extraída por classify_and_route(), acotado a `company`. Devuelve la
    instancia de CompanyUser que coincide, o None si no hay
    coincidencia exacta (o la pista está vacía) -- quien llama trata
    None como "enrutar a sin asignar", conservando worker_dni_hint en
    la fila PersonalDocument creada (detected_dni_hint) para
    trazabilidad, según el docstring del modelo PersonalDocument.

    Deliberadamente NO recurre a emparejar por worker_name_hint -- el
    matching por nombre es mucho más propenso a error (variantes
    ortográficas, apellidos comunes) para un dato tan sensible; el DNI
    es el único identificador de confianza para asignación automática
    en este primer corte. name_hint se sigue capturando en
    classify_and_route() y debe mostrarse a quien revise a mano el
    bloque "sin asignar", pero nunca se usa para emparejar
    automáticamente.

    Args:
        company: instancia de ivr_config.Company a la que acotar la
            búsqueda.
        worker_dni_hint: pista de texto en bruto de
            classify_and_route() (campo worker_dni_hint).
    """
    from ivr_config.models import CompanyUser

    hint = (worker_dni_hint or "").strip().upper()
    if not hint:
        return None

    match = (
        CompanyUser.objects
        .filter(company=company, dni__iexact=hint)
        .first()
    )
    if match:
        logger.info(
            "# [match_company_user] DNI %r -> CompanyUser #%d (%s).",
            hint, match.pk,
            match.user.get_full_name() or match.user.username,
        )
    else:
        logger.warning(
            "# [match_company_user] DNI %r sin coincidencia exacta en "
            "company=%s -- sin asignar (detected_dni_hint conserva la "
            "pista).",
            hint, company,
        )
    return match
