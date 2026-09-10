# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/personal_intake_service.py
"""
H31 (S100), Bloque 1 -- extracción real de datos para el alta de
trabajador nuevo guiada por documentación. Miguel Ángel, verbatim,
corrigiendo la primera implementación (formulario manual): "Dar de
alta no es hincharse una persona a meter todos los datos de un
trabajador. Dar de alta es subir la documentación a la plataforma y
que la plataforma lo dé de alta [...] que el sistema coja la
documentación y dé de alta al trabajador."

Deliberadamente NO importa nada de `classification_service` (H29) ni
depende de un `DocumentIndexEntry` ya indexado -- este pipeline es
nuevo y no tiene relación con H28/H29, con el explorador de archivos,
ni con ninguna cuarentena (ver anexo H31, preguntas 3/4, corregidas en
S100). Reutiliza únicamente el cliente Gemini transversal y ya
validado de `ai_services` (mismo principio DRY que sí aplica al
propio `classification_service`, doc-master sección 4.1.1) -- el
patrón de reintento (`_generate_content_with_retry`) se mantiene
LOCAL a este módulo, mismo criterio que ya adoptó
`classification_service` frente a `ai_services.document_vision_
service`: no se importa un auxiliar privado cruzando el límite entre
apps.

Todo el flujo es SÍNCRONO: el supervisor sube 1-N documentos en el
mismo request, se extraen los datos, se devuelven al momento -- nunca
se persiste nada a medio resolver, nunca hay cola ni barrido
posterior.
"""
import logging
import time

from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from ai_services.gemini_rate_limiter import acquire_gemini_slot

logger = logging.getLogger(__name__)

_MAX_GEMINI_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 60

# Vocabulario cerrado real para el paquete típico de alta -- verbatim
# Miguel Ángel: "dame el DNI, dame el contrato en principio [...] pero
# sobre todo DNI y contrato [...] dame el reconocimiento médico."
# Códigos confirmados contra el catálogo real (document_explorer/
# migrations/0002_documenttypecatalog.py, 0004_seed_closed_
# vocabulary.py) -- nunca inventados aquí.
_DOCUMENT_TYPE_CHOICES = ("DNI", "CONTRATO", "RECONOCIMIENTO_MEDICO", "DESCONOCIDO")

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "document_type_code": {
            "type": "string", "enum": list(_DOCUMENT_TYPE_CHOICES),
        },
        "confidence": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
        "reasoning": {"type": "string"},
        "first_surname_hint": {"type": "string"},
        "second_surname_hint": {"type": "string"},
        "given_name_hint": {"type": "string"},
        "dni_hint": {"type": "string"},
        "employer_company_hint": {"type": "string"},
        "hire_date_hint": {"type": "string"},
    },
    "required": [
        "document_type_code", "confidence", "reasoning",
        "first_surname_hint", "second_surname_hint", "given_name_hint",
        "dni_hint", "employer_company_hint", "hire_date_hint",
    ],
}

_PROMPT = """Eres un asistente de RRHH de una empresa española de \
grúas y maquinaria pesada. Se te da UN documento (imagen o PDF) \
entregado para dar de alta a un trabajador nuevo.

1. Identifica de qué tipo de documento se trata, SOLO entre estos \
códigos: DNI (documento nacional de identidad o NIE, anverso o \
reverso), CONTRATO (contrato laboral), RECONOCIMIENTO_MEDICO \
(reconocimiento médico), o DESCONOCIDO si no encaja en ninguno.

2. Extrae, cuando el documento los contenga de forma legible:
   - Si es un DNI: primer apellido, segundo apellido, nombre, y el \
número de DNI/NIE tal cual aparece (incluida la letra final).
   - Si es un CONTRATO laboral: el nombre de la empresa empleadora \
real (tal cual aparece, sin normalizar), y la fecha de inicio/alta \
en la empresa (formato AAAA-MM-DD).
   - Cualquier campo que no aparezca o no se pueda leer con \
confianza, déjalo como cadena vacía -- nunca inventes un valor.

Devuelve el resultado como el JSON estructurado indicado, sin texto \
adicional."""


def _generate_content_with_retry(client, **kwargs):
    """Mismo patrón de reintento que `classification_service` (H29,
    mantenido local a propósito -- ver docstring del módulo)."""
    last_exc = None
    for attempt in range(1, _MAX_GEMINI_ATTEMPTS + 1):
        acquire_gemini_slot()
        try:
            return client.models.generate_content(**kwargs)
        except Exception as exc:
            last_exc = exc
            exc_str = str(exc)
            is_retryable = (
                "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str
                or "504" in exc_str or "DEADLINE_EXCEEDED" in exc_str
                or "503" in exc_str or "UNAVAILABLE" in exc_str
            )
            if not is_retryable or attempt == _MAX_GEMINI_ATTEMPTS:
                raise
            logger.warning(
                "# [personal_intake_service] Error transitorio de "
                "Vertex AI (intento %d/%d): %s. Reintentando en %ds.",
                attempt, _MAX_GEMINI_ATTEMPTS, exc_str[:200],
                _RETRY_DELAY_SECONDS,
            )
            time.sleep(_RETRY_DELAY_SECONDS)
    raise last_exc  # pragma: no cover -- inalcanzable


def extract_one_document(data: bytes, mime_type: str) -> dict:
    """
    Extrae datos de UN documento subido (bytes en memoria, nunca
    todavía indexado en GCS -- este flujo sube de verdad solo tras la
    confirmación del supervisor). Devuelve el JSON ya parseado, o
    {"error": ...} si Gemini falla -- nunca lanza, el llamador decide
    cómo mostrarlo al supervisor.
    """
    try:
        client = get_gemini_client()
        response = _generate_content_with_retry(
            client,
            model=DEFAULT_MODEL,
            contents=[
                Part.from_bytes(data=data, mime_type=mime_type),
                _PROMPT,
            ],
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=90_000),
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0.0,
            ),
        )
        import json
        return json.loads(response.text.strip())
    except Exception as exc:
        logger.warning(
            "# [personal_intake_service] Fallo extrayendo documento: %s",
            exc, exc_info=True,
        )
        return {"error": str(exc)}


def merge_person_draft(extractions: list) -> dict:
    """
    Combina los resultados de `extract_one_document` de varios
    documentos (p. ej. DNI + contrato) en un único borrador de
    PersonIdentity. Regla de combinación: el DNI manda en identidad
    (apellidos/nombre/dni), el CONTRATO manda en
    empresa/fecha de alta -- cada campo se rellena desde el primer
    documento que lo trae con confianza ALTA o MEDIA, nunca se
    sobrescribe un valor ya bueno por uno de confianza BAJA de otro
    documento. Campos que ningún documento resuelve quedan vacíos,
    para que el supervisor los rellene a mano en el paso de
    confirmación -- nunca se bloquea el alta por un campo que no se
    pudo leer.
    """
    draft = {
        "dni": "", "first_surname": "", "second_surname": "",
        "given_name": "", "employer_company": "", "hire_date": "",
    }
    warnings = []
    for idx, result in enumerate(extractions):
        if "error" in result:
            warnings.append(
                "Documento %d: no se pudo leer (%s)."
                % (idx + 1, result["error"]),
            )
            continue
        confidence_ok = result.get("confidence") in ("ALTA", "MEDIA")
        if not confidence_ok:
            warnings.append(
                "Documento %d: lectura de baja confianza, revisar a mano."
                % (idx + 1),
            )
            continue
        if not draft["dni"] and result.get("dni_hint"):
            draft["dni"] = result["dni_hint"]
        if not draft["first_surname"] and result.get("first_surname_hint"):
            draft["first_surname"] = result["first_surname_hint"]
        if not draft["second_surname"] and result.get("second_surname_hint"):
            draft["second_surname"] = result["second_surname_hint"]
        if not draft["given_name"] and result.get("given_name_hint"):
            draft["given_name"] = result["given_name_hint"]
        if not draft["employer_company"] and result.get("employer_company_hint"):
            draft["employer_company"] = result["employer_company_hint"]
        if not draft["hire_date"] and result.get("hire_date_hint"):
            draft["hire_date"] = result["hire_date_hint"]
    return {"draft": draft, "warnings": warnings}
