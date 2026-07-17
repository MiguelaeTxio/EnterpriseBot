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
import re

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

IMPORTANTE sobre las pistas de máquina/trabajador: en esta empresa es muy
habitual que el propio nombre de archivo ya incluya el código o la matrícula
de la máquina (ej. "A-45 E-6998-BDY Manual.pdf", "A-45_E-6998-BDY_02.pdf",
"E6998BDY A45 ALLIANZ.pdf") -- a veces con guiones, a veces sin ellos, a
veces con espacios o guiones bajos en su lugar. Debes MIRAR TANTO el nombre
de archivo COMO el contenido del documento para extraer la pista -- nunca
ignores el nombre de archivo. Si el nombre de archivo contiene un código o
matrícula reconocible,úsalo como pista aunque el contenido del documento no
lo repita literalmente.

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
   o la matrícula de la máquina/vehículo -- búscalo tanto en el nombre
   de archivo como en el contenido del documento (ver nota de arriba).
   Devuelve la pista LIMPIA (solo el código o la matrícula en sí, sin
   texto adicional alrededor, ej. "A-45" o "E-6998-BDY", nunca "A-45
   E-6998-BDY Manual"). Si aparecen tanto el código como la matrícula,
   prefiere el código (más corto, más fiable). Cadena vacía "" si
   domain no es "MACHINE" o no aparece ninguna referencia reconocible
   en ningún sitio.
3. worker_dni_hint: si domain es "PERSONAL", el DNI/NIF del
   trabajador -- búscalo tanto en el nombre de archivo como en el
   contenido del documento. Cadena vacía "" si domain no es "PERSONAL"
   o no aparece un DNI/NIF reconocible en ningún sitio.
4. worker_name_hint: si domain es "PERSONAL", el nombre completo del
   trabajador -- búscalo tanto en el nombre de archivo como en el
   contenido del documento (útil como respaldo cuando no hay DNI
   legible). Cadena vacía "" si domain no es "PERSONAL" o no se
   identifica un nombre en ningún sitio.
5. is_confident: true únicamente si domain es "MACHINE" o "PERSONAL"
   Y además hay una pista identificativa (machine_reference_hint o
   worker_dni_hint/worker_name_hint) reconocible en el nombre de
   archivo o en el documento. false en cualquier otro caso, incluido
   cuando el dominio está claro pero no hay ninguna pista para
   identificar a QUÉ máquina o QUÉ trabajador concreto pertenece.
6. reasoning: explicación breve (1-2 frases) de la decisión, indicando
   si la pista salió del nombre de archivo, del contenido, o de ambos.

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


def route_document(pdf_bytes: bytes, filename: str, company) -> dict:
    """
    Envoltorio de classify_and_route() que evita llamar a Gemini por
    completo para manuales de uso -- bug real corregido en S024-cuater
    (Miguel Ángel: "el manual de uso se asigna directamente a la
    máquina... no tiene datos que extraer... va directamente a la
    máquina y ya está. No sé por qué tenemos esta regresión"). El
    enrutado nuevo (H23/S024) reintrodujo el incidente del 2026-07-14
    (manual pesado -> timeout de Gemini) porque llamaba a
    classify_and_route() sobre los bytes completos del manual ANTES de
    llegar al punto donde machine_documents.document_classification_
    service ya evita Gemini para manuales -- ese heurístico solo vivía
    en la CLASIFICACIÓN, nunca en el ENRUTADO, que es un punto de
    llamada a Gemini distinto y anterior.

    Si machine_documents.document_classification_service.
    is_manual_by_filename(filename) es True: nunca toca los bytes ni
    llama a Gemini -- determina la máquina por coincidencia de texto
    del propio nombre de archivo contra el código/matrícula de las
    máquinas de `company` (match_machine_asset_by_filename), y
    devuelve domain=MACHINE directamente, is_confident según haya
    habido coincidencia o no (si no la hay, se enruta igual como
    MACHINE pero sin pista -- nunca "sin identificar": un manual
    SIEMPRE es de dominio máquina, decisión explícita de Miguel Ángel,
    aunque no sepamos de cuál en concreto por el nombre de archivo).

    En cualquier otro caso, delega en classify_and_route() tal cual.

    ---

    Wrapper around classify_and_route() that skips Gemini entirely for
    user manuals -- see docstring above (Spanish) for the full
    incident writeup. Manuals always route to MACHINE domain directly
    via filename-only matching, never touching Gemini nor falling into
    "sin identificar".
    """
    from machine_documents.document_classification_service import (
        is_manual_by_filename,
    )

    if is_manual_by_filename(filename):
        matched_machine = match_machine_asset_by_filename(company, filename)
        result = {
            "domain": DOMAIN_MACHINE,
            "machine_reference_hint": matched_machine.code if matched_machine else "",
            "worker_dni_hint": "",
            "worker_name_hint": "",
            "is_confident": matched_machine is not None,
            "reasoning": (
                "Manual de uso (heurística de nombre de archivo) -- "
                "nunca se envía a Gemini, ni para enrutar ni para "
                "clasificar. Máquina determinada por coincidencia de "
                "texto del nombre de archivo."
                if matched_machine else
                "Manual de uso (heurística de nombre de archivo) -- "
                "nunca se envía a Gemini. No se encontró ninguna "
                "máquina cuyo código/matrícula aparezca en el nombre "
                "de archivo -- se enruta como MACHINE sin asignar."
            ),
        }
        logger.info(
            "# [route_document] %s -> MANUAL DE USO, sin llamada a "
            "Gemini -- maquina=%s.",
            filename, matched_machine.code if matched_machine else "SIN ASIGNAR",
        )
        return result

    return classify_and_route(pdf_bytes, filename)


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

def _normalize_for_matching(value: str) -> str:
    """
    Quita todo lo que no sea letra o dígito y pasa a mayúsculas --
    para que "E-6998-BDY", "E6998BDY" y "e_6998_bdy" comparen igual.
    Añadido S024 tras un caso real (Miguel Ángel): archivos con el
    código de máquina en el nombre, en formatos distintos al
    almacenado en el catálogo, se quedaban "sin asignar" pese a llevar
    la referencia literal -- el emparejamiento exacto byte a byte no
    los reconocía. NUNCA se aplican aquí las sustituciones OCR de
    work_order_processor._normalise_machine_code (letra↔dígito para
    partes manuscritos escaneados) -- ese es un problema distinto
    (mala lectura óptica de escritura a mano), no aplica a texto ya
    limpio extraído de un nombre de archivo o de un PDF nativo.
    ---
    Strips everything that isn't a letter or digit and uppercases --
    so "E-6998-BDY", "E6998BDY" and "e_6998_bdy" compare equal.
    """
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def match_machine_asset_by_filename(company, filename: str):
    """
    Busca un fleet.MachineAsset cuyo `code` o `plate` (normalizados,
    ver _normalize_for_matching) aparezcan como SUBCADENA del nombre
    de archivo (normalizado igual) -- añadida S024-cuater
    exclusivamente para route_document()/manuales de uso: nunca se usa
    para documentos normales (esos sí pasan por Gemini y por
    match_machine_asset(), que compara contra la pista que Gemini
    extrajo, no contra el nombre de archivo entero). Un manual no
    tiene ninguna pista de Gemini que comparar -- Gemini nunca llega a
    verlo -- así que aquí se busca directamente en el propio nombre de
    archivo completo.

    Devuelve la primera coincidencia, o None si ninguna máquina de
    `company` aparece en el nombre de archivo.

    ---

    Looks up a fleet.MachineAsset whose `code` or `plate` (normalized)
    appears as a SUBSTRING of the filename (also normalized) -- added
    S024-cuater exclusively for route_document()/user manuals. Never
    used for regular documents (those go through Gemini and
    match_machine_asset() instead, comparing against Gemini's
    extracted hint, not the whole filename).
    """
    from fleet.models import MachineAsset

    normalized_filename = _normalize_for_matching(filename)
    if not normalized_filename:
        return None

    for machine in MachineAsset.objects.filter(company=company):
        normalized_code = _normalize_for_matching(machine.code)
        if normalized_code and normalized_code in normalized_filename:
            return machine
        if machine.plate:
            normalized_plate = _normalize_for_matching(machine.plate)
            if normalized_plate and normalized_plate in normalized_filename:
                return machine
    return None


def match_machine_asset(company, machine_reference_hint: str):
    """
    Looks up a fleet.MachineAsset by NORMALIZED match (ignoring
    hyphens/spaces/underscores/case) of its `code` or `plate` against
    the hint extracted by classify_and_route(), scoped to `company`.
    Returns the matching MachineAsset instance, or None if no
    normalized match is found (or the hint is empty) -- callers treat
    None as "route to sin asignar".

    Normalized, not exact-string, matching on purpose (S024, real
    case): "E6998BDY" and "E-6998-BDY" must match the same machine --
    see _normalize_for_matching() above.

    Args:
        company: ivr_config.Company instance to scope the lookup to.
        machine_reference_hint: raw text hint from classify_and_route()
            (machine_reference_hint field).

    ---

    Busca un fleet.MachineAsset por coincidencia NORMALIZADA (ignora
    guiones/espacios/guiones bajos/mayúsculas) de su `code` o `plate`
    contra la pista extraída por classify_and_route(), acotado a
    `company`. Devuelve la instancia que coincide, o None si no hay
    coincidencia normalizada (o la pista está vacía) -- quien llama
    trata None como "enrutar a sin asignar".

    Emparejamiento normalizado, no exacto carácter a carácter, a
    propósito (S024, caso real): "E6998BDY" y "E-6998-BDY" deben
    emparejar con la misma máquina -- ver _normalize_for_matching()
    arriba.

    Args:
        company: instancia de ivr_config.Company a la que acotar la
            búsqueda.
        machine_reference_hint: pista de texto en bruto de
            classify_and_route() (campo machine_reference_hint).
    """
    from fleet.models import MachineAsset

    normalized_hint = _normalize_for_matching(machine_reference_hint)
    if not normalized_hint:
        return None

    for machine in MachineAsset.objects.filter(company=company):
        if _normalize_for_matching(machine.code) == normalized_hint:
            logger.info(
                "# [match_machine_asset] Pista %r -> MachineAsset #%d "
                "(%s) por código normalizado.",
                machine_reference_hint, machine.pk, machine.code,
            )
            return machine
        if machine.plate and _normalize_for_matching(machine.plate) == normalized_hint:
            logger.info(
                "# [match_machine_asset] Pista %r -> MachineAsset #%d "
                "(%s) por matrícula normalizada.",
                machine_reference_hint, machine.pk, machine.code,
            )
            return machine

    logger.warning(
        "# [match_machine_asset] Pista %r (normalizada: %r) sin "
        "coincidencia en company=%s -- sin asignar.",
        machine_reference_hint, normalized_hint, company,
    )
    return None


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

    normalized_hint = _normalize_for_matching(worker_dni_hint)
    if not normalized_hint:
        return None

    for company_user in CompanyUser.objects.filter(company=company).select_related("user"):
        if company_user.dni and _normalize_for_matching(company_user.dni) == normalized_hint:
            logger.info(
                "# [match_company_user] DNI %r -> CompanyUser #%d (%s) "
                "por coincidencia normalizada.",
                worker_dni_hint, company_user.pk,
                company_user.user.get_full_name() or company_user.user.username,
            )
            return company_user

    logger.warning(
        "# [match_company_user] DNI %r (normalizado: %r) sin "
        "coincidencia en company=%s -- sin asignar (detected_dni_hint "
        "conserva la pista).",
        worker_dni_hint, normalized_hint, company,
    )
    return None
