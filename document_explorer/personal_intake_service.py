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
import difflib
import json
import logging
import time

from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from ai_services.gemini_rate_limiter import acquire_gemini_slot

logger = logging.getLogger(__name__)

_MAX_GEMINI_ATTEMPTS = 3
# H31 (S100), incidente real: 60s (heredado de classification_service,
# donde no importa porque corre en segundo plano/lote) generaba
# esperas de varios minutos en un modal SÍNCRONO -- el supervisor
# espera en vivo, y con 15 documentos procesados uno a uno, dos o tres
# reintentos de 60s se acumulan sin que nada lo explique en pantalla.
# 5s basta para que Vertex AI se recupere de un 429/504 transitorio
# sin convertir la espera en minutos.
_RETRY_DELAY_SECONDS = 5

# H31 (S100), ampliación pedida por Miguel Ángel: "mejoramos para
# incluir el resto de documentos. Supuestamente ya disponemos de lo
# necesario para clasificar todo lo referente a personal." El
# vocabulario cerrado inicial (DNI/CONTRATO/RECONOCIMIENTO_MEDICO) se
# sustituye por el catálogo REAL completo de PERSONAL
# (`DocumentTypeCatalog`, domain="PERSONAL", is_active=True) --
# confirmado con Comando S real contra la BD de producción, 79 tipos
# activos a fecha de esta sesión (ALTA, CONTRATO, DNI, NOMINA, CAP,
# CARNET_CONDUCIR, FORMACION... la lista completa vive en la propia
# tabla, nunca hardcodeada aquí). Se consulta en cada llamada -- un
# tipo nuevo que Miguel Ángel añada al catálogo se reconoce solo, sin
# tocar este archivo.
def _personal_type_catalog():
    from document_explorer.models import DocumentTypeCatalog
    return list(
        DocumentTypeCatalog.objects.filter(
            domain="PERSONAL", is_active=True,
        ).order_by("code").values_list("code", "label"),
    )


def _build_response_schema():
    codes = [code for code, _label in _personal_type_catalog()] + ["DESCONOCIDO"]
    return {
        "type": "object",
        "properties": {
            "document_type_code": {"type": "string", "enum": codes},
            "confidence": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
            "reasoning": {"type": "string"},
            "first_surname_hint": {"type": "string"},
            "second_surname_hint": {"type": "string"},
            "given_name_hint": {"type": "string"},
            "dni_hint": {"type": "string"},
            "ss_number_hint": {"type": "string"},
            "birth_date_hint": {"type": "string"},
            "expiry_hint": {"type": "string"},
            "issue_hint": {"type": "string"},
            "address_hint": {"type": "string"},
            "city_hint": {"type": "string"},
            "province_hint": {"type": "string"},
            "employer_company_hint": {"type": "string"},
            "hire_date_hint": {"type": "string"},
        },
        "required": [
            "document_type_code", "confidence", "reasoning",
            "first_surname_hint", "second_surname_hint", "given_name_hint",
            "dni_hint", "ss_number_hint", "birth_date_hint", "expiry_hint", "issue_hint",
            "address_hint", "city_hint", "province_hint",
            "employer_company_hint", "hire_date_hint",
        ],
    }


def _type_list_text():
    return "\n".join(
        "%s -- %s" % (code, label) for code, label in _personal_type_catalog()
    )


def _build_prompt(intro: str, include_dates: bool = True) -> str:
    # H31 (S100), corrección de Miguel Ángel en la propia sesión: "el
    # fechado lo estábamos haciendo ya sin Gemini [...] a través de la
    # lectura de OCR [...] ya no es necesario llamar a Gemini para
    # obtener las fechas." Pedirle la fecha a Gemini es redundante (y
    # menos fiable) en cuanto hay texto OCR real que pasar por
    # `classify_dates_in_text()` -- el motor determinista de H30,
    # calibrado durante semanas. `include_dates=False` (camino normal,
    # con texto OCR) omite el punto de fechas del prompt por completo;
    # solo el camino de Vision directo (sin texto OCR posible) sigue
    # pidiéndosela a Gemini, porque ahí no hay otra fuente.
    date_instructions = ""
    if include_dates:
        date_instructions = """
   - La fecha de caducidad/validez del propio documento, si la \
tiene (formato AAAA-MM-DD) -- no todos los tipos la tienen, \
déjala vacía si no aplica o no se puede leer.
   - Si el documento NO tiene fecha de caducidad propia (una nómina, \
un parte, una autorización sin plazo...), la fecha de emisión/firma \
del propio documento (formato AAAA-MM-DD) -- sirve para saber cuál \
es el más reciente cuando hay varios del mismo tipo."""
    return """Eres un asistente de RRHH de una empresa española de \
grúas y maquinaria pesada. %s

1. Identifica de qué tipo de documento se trata -- elige el código \
que mejor encaje entre estos (los mismos que ya usa la plataforma \
para clasificar documentación de personal):
%s
Si no encaja en ninguno, usa DESCONOCIDO.

2. Extrae, cuando el documento los contenga de forma legible:
   - Apellidos y nombre de la persona a la que pertenece el \
documento, si aparecen (primer apellido, segundo apellido, nombre).
   - El número de afiliación a la Seguridad Social (NSS), tal cual \
aparece (puede llevar espacios o guiones), si el documento lo trae -- \
suele aparecer en el ALTA de la Seguridad Social o en el IDC \
(Informe de Datos para la Cotización).
   - Si es un DNI o NIE: el número tal cual aparece (incluida la \
letra final), la fecha de nacimiento, y -- si el reverso trae el \
domicilio -- la dirección (calle y número), la población y la \
provincia, cada una en su propio campo, tal cual aparecen.%s
   - Si es un CONTRATO laboral: el nombre de la empresa empleadora \
real (tal cual aparece, sin normalizar), y la fecha de inicio/alta \
en la empresa (formato AAAA-MM-DD).
   - Cualquier campo que no aparezca o no se pueda leer con \
confianza, déjalo como cadena vacía -- nunca inventes un valor.

Devuelve el resultado como el JSON estructurado indicado, sin texto \
adicional.""" % (intro, _type_list_text(), date_instructions)


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


def normalize_dni(raw_dni: str) -> str:
    """
    Normalización compartida de DNI/NIE -- mayúsculas, sin espacios ni
    guiones. Usada tanto por la extracción (para poder comprobar
    duplicados nada más leer los documentos) como por
    `PersonalCreateView` (S100, movida aquí para no duplicarla).

    CORREGIDO EN S100 (misma sesión), incidente real de Miguel Ángel
    con su propio DNI: probó el alta y el DNI leído salió
    "074633524L" en vez de "74633524L" -- exactamente el mismo fallo
    ya documentado y corregido en H29 (S042,
    `classification_service._normalize_dni`): un DNI son SIEMPRE
    exactamente 8 dígitos + 1 letra de control (un NIE ya son 9
    caracteres sin ambigüedad); un valor de 10 caracteres que empieza
    por "0" y el resto son 8 dígitos + letra solo puede ser un DNI
    real con un cero espurio añadido por Gemini al leer el MRZ, nunca
    un número genuinamente distinto -- los DNI españoles no los
    tienen. Misma corrección, replicada aquí a propósito (no
    importada de `classification_service`/H29, para no acoplar este
    pipeline nuevo al de H28/H29 -- ver anexo H31, preguntas 3/4).
    """
    value = (raw_dni or "").strip().upper().replace(" ", "").replace("-", "")
    if (
        len(value) == 10 and value[0] == "0"
        and value[1:9].isdigit() and value[9].isalpha()
    ):
        value = value[1:]
    return value


# H31 (S100), mismo motivo que la corrección del cero espurio de
# arriba: algoritmo real y público de la letra de control del DNI/NIE
# español -- ya usado en `classification_service.is_valid_spanish_dni`
# (H29), replicado aquí (no importado, mismo criterio de
# desacoplamiento de H28/H29) para poder detectar gratis, sin ninguna
# llamada de red, un dígito mal leído por el OCR/Gemini antes de que
# llegue a crear una ficha con un DNI real pero incorrecto.
_DNI_CHECK_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_NIE_PREFIX_DIGIT = {"X": "0", "Y": "1", "Z": "2"}


def is_valid_spanish_dni(raw_dni: str) -> bool:
    """Valida un DNI/NIE español por su letra de control real."""
    value = normalize_dni(raw_dni)
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


# H31 (S100), corrección explícita de Miguel Ángel tras el incidente
# real del filtro de Personal (una ficha nueva quedaba invisible
# porque el contrato traía "ASISTENCIA Y GRUAS GRANADA S.L." y el
# Excel real usa "ASIST.GRUAS GRANADA"): *"hay que normalizar [...]
# el nombre de la empresa tiene que ser ya como lo que tenemos en el
# Excel [...] no puedo ir a otras empresas [...] a cuál se parece
# más, pues va a esa."* Mismas variantes reales conocidas por
# `panel.views_documentation_h30.COMPANY_FILTER_CHOICES` -- mantener
# sincronizadas si se añade o cambia una empresa real. El texto libre
# que Gemini lee del contrato NUNCA se guarda tal cual en
# `PersonIdentity.employer_company`; el propio documento del contrato,
# ya indexado, sigue siendo la trazabilidad real de lo que decía el
# papel si hiciera falta consultarlo.
_KNOWN_EMPLOYER_COMPANIES = (
    "GRUAS ADOLFO ALVAREZ SL",
    "TRANSGRUAL SL",
    "GRUALDI S.L",
    "ASIST.GRUAS GRANADA",
)


def normalize_employer_company(raw_text: str) -> str:
    """
    Normaliza el texto de empresa leído de un contrato a la variante
    real más parecida de `_KNOWN_EMPLOYER_COMPANIES` -- nunca se deja
    el texto libre tal cual. Cadena vacía si `raw_text` está vacío
    (ninguna empresa legible en el contrato, no se inventa una).
    """
    text = (raw_text or "").strip()
    if not text:
        return ""
    normalized = text.upper()
    return max(
        _KNOWN_EMPLOYER_COMPANIES,
        key=lambda known: difflib.SequenceMatcher(
            None, normalized, known,
        ).ratio(),
    )


def _build_text_prompt(ocr_text: str) -> str:
    intro = (
        "Se te da el TEXTO ya extraído por OCR de un documento "
        "entregado para dar de alta a un trabajador nuevo (el "
        "propio texto puede tener errores de OCR -- ruido, letras "
        "mal leídas -- interprétalo con criterio).\n\n"
        "TEXTO DEL DOCUMENTO:\n---\n%s\n---" % ocr_text
    )
    return _build_prompt(intro, include_dates=False)


def _call_gemini_json(contents, timeout_ms: int = 30_000) -> dict:
    """
    H31 (S100), incidente real: 90s por intento (heredado de
    `classification_service`, donde tiene sentido para analizar una
    imagen/PDF entero) hacía que un documento con mala suerte pudiera
    acaparar varios minutos él solo (hasta 3 intentos x 90s). La
    llamada de solo TEXTO (el camino normal, tras OCR) es una tarea
    mucho más ligera -- 30s de margen real es generoso para ella.
    `timeout_ms` es explícito para que el camino de Vision directo
    (imagen/PDF completo, último recurso) pueda seguir pidiendo más
    tiempo sin heredarlo por accidente al camino rápido.
    """
    client = get_gemini_client()
    response = _generate_content_with_retry(
        client,
        model=DEFAULT_MODEL,
        contents=contents,
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=timeout_ms),
            response_mime_type="application/json",
            response_schema=_build_response_schema(),
            temperature=0.0,
        ),
    )
    return json.loads(response.text.strip())


def _pdf_embedded_text(data: bytes) -> str:
    """
    H31 (S100), corrección real: muchos PDF del alta NO son un
    escaneo/foto -- son documentos generados digitalmente por un
    ordenador (Resoluciones de la Seguridad Social, contratos
    generados desde una plantilla...) que ya llevan el texto real
    incrustado dentro del propio archivo. Mandarlos a OCR (leer los
    píxeles renderizados) introduce ruido -- saltos de línea y
    espaciados distintos a los del texto real -- que puede romper
    justo la coincidencia de contexto que `classify_dates_in_text()`
    necesita ver pegada (verificado con un caso real: el motor
    clasifica bien "con fecha 19/06/2024" leyendo el texto real
    incrustado del PDF, verbatim exacto). Extraer este texto ya
    incrustado es gratis, instantáneo, y más fiable que cualquier OCR
    -- es el texto real del documento, no una lectura visual.

    Devuelve cadena vacía (nunca lanza) si el PDF no trae texto real
    -- es un escaneo/foto -- para que el llamador caiga a Cloud Vision
    en ese caso.
    """
    import fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
        parts = [page.get_text() for page in doc[:2]]
        return "\n".join(parts).strip()
    except Exception as exc:
        logger.warning(
            "# [personal_intake_service] Fallo leyendo texto incrustado "
            "del PDF: %s", exc,
        )
        return ""


def _cloud_vision_text(data: bytes, mime_type: str, filename: str) -> str:
    """
    OCR real vía Cloud Vision API (H31, S100) -- sustituye a Tesseract
    local tras el aviso de Miguel Ángel: el OCR local consume CPU
    compartida real de PythonAnywhere, con cuota diaria por cuenta, y
    varias altas de 15-20 documentos el mismo día podrían agotarla y
    bloquear el resto del trabajo. Cloud Vision corre en la nube de
    Google (mismo proyecto/credenciales ya usadas para Vertex AI, vía
    `ai_services.gemini_client.ensure_gcp_credentials()`), responde en
    menos de un segundo por imagen, y no gasta ni un ciclo de CPU en
    el servidor.

    Imagen (jpg/jpeg/png): `text_detection()`, sincrono estándar.
    PDF: `batch_annotate_files()` con `DOCUMENT_TEXT_DETECTION`,
    acotado a las 2 primeras páginas -- mismo límite que ya usaba
    `date_verification_service.ocr_pdf_to_text(max_pages=2)`, un DNI o
    la primera página de un contrato nunca necesitan más.
    Devuelve cadena vacía (nunca None) si no hay texto reconocible, o
    si la extensión no está soportada -- el llamador decide el
    fallback.
    """
    from google.cloud import vision

    from ai_services.gemini_client import ensure_gcp_credentials

    ensure_gcp_credentials()
    client = vision.ImageAnnotatorClient()
    name_lower = (filename or "").lower()

    if name_lower.endswith((".jpg", ".jpeg", ".png")):
        image = vision.Image(content=data)
        response = client.text_detection(image=image)
        if response.error.message:
            raise RuntimeError(response.error.message)
        return response.full_text_annotation.text or ""

    if name_lower.endswith(".pdf"):
        input_config = vision.InputConfig(
            content=data, mime_type="application/pdf",
        )
        feature = vision.Feature(
            type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION,
        )
        # H31 (S100): páginas 1-based en la API -- 1 y 2, mismo límite
        # de 2 páginas que el OCR local que sustituye.
        request = vision.AnnotateFileRequest(
            input_config=input_config, features=[feature], pages=[1, 2],
        )
        response = client.batch_annotate_files(requests=[request])
        texts = []
        for file_response in response.responses:
            for page_response in file_response.responses:
                if page_response.error.message:
                    continue
                texts.append(page_response.full_text_annotation.text or "")
        return "\n".join(texts)

    return ""


def extract_one_document(data: bytes, mime_type: str, filename: str = "") -> dict:
    """
    Extrae datos de UN documento subido (bytes en memoria, nunca
    todavía indexado en GCS -- este flujo sube de verdad solo tras la
    confirmación del supervisor). Devuelve el JSON ya parseado, o
    {"error": ...} si falla -- nunca lanza, el llamador decide cómo
    mostrarlo al supervisor.

    REESCRITO EN S100 (misma sesión) dos veces: primero de Gemini
    Vision directo a OCR local (Tesseract) + Gemini de texto (Miguel
    Ángel: "eso tarda muchísimo"); después de Tesseract local a Cloud
    Vision API (Miguel Ángel: el OCR local consume CPU compartida real
    de PythonAnywhere, con riesgo de agotar la cuota diaria si varios
    trabajadores se dan de alta el mismo día con 15-20 documentos cada
    uno). Cloud Vision (`_cloud_vision_text()`) corre en la nube de
    Google, sin CPU local, rápido, y Gemini sigue interpretando solo
    el TEXTO ya extraído (nunca la imagen/PDF entero -- eso es lo que
    lo hacía lento). La fecha de nacimiento, cuando el documento trae
    un MRZ real de DNI/NIE español, se resuelve además con
    `extract_dni_mrz_birthdate()` (H30) sobre el propio texto --
    validación por dígito de control ICAO, sin coste de API, funciona
    igual sea cual sea el motor de OCR que produjo el texto.

    Si Cloud Vision no logra extraer ningún texto (imagen ilegible,
    extensión no soportada), cae al último recurso -- Gemini Vision
    directo sobre el archivo -- nunca se deja sin leer.

    CORREGIDO EN LA MISMA SESIÓN (S100): la primera versión de este
    bloque pedía la fecha directamente a Gemini de forma genérica,
    ignorando por completo el motor real de fechado ya calibrado en
    H30 (`classify_dates_in_text()` -- contexto de emisión/caducidad,
    dos semanas de correcciones reales sobre casos concretos: saltos
    de línea del OCR, comas, fechas de ruido...). Miguel Ángel,
    verbatim, al ver documentos marcados en rojo sin motivo y dos
    ALTA sin poder decidir cuál es la vigente: *"¿qué ha pasado con
    todos estos motores que llevamos dos semanas creando? [...] la
    extracción de fecha [...] lo estamos ignorando."* Corregido: el
    texto OCR se pasa por `classify_dates_in_text()` -- que devuelve
    caducidad Y emisión, exactamente lo que
    `document_management.vigencia_service` necesita para decidir cuál
    es el más reciente en tipos sin caducidad propia (ALTA, nóminas...)
    -- y ese resultado manda sobre lo que haya dicho Gemini. El MRZ
    (`extract_dni_mrz_expiry`) sigue reforzando el caso DNI/NIE
    específico por encima incluso de `classify_dates_in_text`, por ser
    el más fiable de los tres (validación por dígito de control).
    """
    from document_explorer.date_verification_service import (
        classify_dates_in_text, extract_dni_mrz_birthdate,
        extract_dni_mrz_expiry,
    )
    try:
        text = ""
        if filename and filename.lower().endswith(".pdf"):
            text = _pdf_embedded_text(data)
        if not text and filename:
            text = _cloud_vision_text(data, mime_type, filename)
        if not text:
            # Cloud Vision no encontró texto (o extensión no
            # soportada) -- último recurso, Vision directo con Gemini
            # sobre el archivo, mismo camino que la v1. Analizar una
            # imagen/PDF entero es más pesado que interpretar texto,
            # por eso conserva el timeout largo (90s) explícitamente.
            result = _call_gemini_json(
                [
                    Part.from_bytes(data=data, mime_type=mime_type),
                    _build_prompt("Se te da UN documento (imagen o PDF) "
                                  "entregado para dar de alta a un "
                                  "trabajador nuevo."),
                ],
                timeout_ms=90_000,
            )
        elif not text.strip():
            result = {
                "error": "El OCR no encontró texto legible en el documento.",
            }
        else:
            result = _call_gemini_json(_build_text_prompt(text[:8000]))
            engine_expiry, engine_issue, _others = classify_dates_in_text(text)
            if engine_expiry:
                result["expiry_hint"] = engine_expiry.isoformat()
            if engine_issue:
                result["issue_hint"] = engine_issue.isoformat()
            mrz_birthdate = extract_dni_mrz_birthdate(text)
            if mrz_birthdate:
                result["birth_date_hint"] = mrz_birthdate.isoformat()
            mrz_expiry = extract_dni_mrz_expiry(text)
            if mrz_expiry:
                result["expiry_hint"] = mrz_expiry.isoformat()
        return result
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
    PersonIdentity. Regla de combinación: el DNI/NIE manda en
    identidad (apellidos/nombre/dni/nacimiento/domicilio), el CONTRATO
    manda en empresa/fecha de alta -- cada campo se rellena desde el
    primer documento de SU TIPO que lo trae con confianza ALTA o
    MEDIA, nunca se sobrescribe un valor ya bueno por uno de otro
    documento. Campos que ningún documento resuelve quedan vacíos,
    para que el supervisor los rellene a mano en el paso de
    confirmación -- nunca se bloquea el alta por un campo que no se
    pudo leer.

    CORREGIDO EN S100 (misma sesión), incidente real: con el
    vocabulario ampliado a 79 tipos, el código NUNCA comprobaba de qué
    tipo era cada documento antes de fusionar identidad -- con solo
    2-3 tipos apenas se notaba, pero con 15 documentos de tipos
    distintos en el mismo lote, cualquiera con una fecha parecida
    (una nómina, un parte, una autorización) podía "ganar" el campo
    `birth_date` antes de que se procesara el DNI real, con el
    resultado real observado: `PersonIdentity.birth_date=None` pese a
    que el DNI sí traía la fecha correcta (validada por MRZ). El
    docstring de esta función ya decía "el DNI manda en identidad" --
    nunca se implementó de verdad hasta ahora.
    """
    draft = {
        "dni": "", "first_surname": "", "second_surname": "",
        "given_name": "", "birth_date": "",
        "address_street": "", "city": "", "province": "",
        "employer_company": "", "hire_date": "", "ss_affiliation_number": "",
    }
    IDENTITY_TYPES = ("DNI", "NIE")
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
        doc_type = result.get("document_type_code", "")
        if doc_type in IDENTITY_TYPES:
            if not draft["dni"] and result.get("dni_hint"):
                candidate_dni = normalize_dni(result["dni_hint"])
                if candidate_dni and not is_valid_spanish_dni(candidate_dni):
                    warnings.append(
                        "Documento %d: el DNI leído (%s) no pasa la letra "
                        "de control real -- revísalo a mano antes de "
                        "confirmar." % (idx + 1, candidate_dni),
                    )
                draft["dni"] = candidate_dni
            if not draft["first_surname"] and result.get("first_surname_hint"):
                draft["first_surname"] = result["first_surname_hint"]
            if not draft["second_surname"] and result.get("second_surname_hint"):
                draft["second_surname"] = result["second_surname_hint"]
            if not draft["given_name"] and result.get("given_name_hint"):
                draft["given_name"] = result["given_name_hint"]
            if not draft["birth_date"] and result.get("birth_date_hint"):
                draft["birth_date"] = result["birth_date_hint"]
            if not draft["address_street"] and result.get("address_hint"):
                draft["address_street"] = result["address_hint"]
            if not draft["city"] and result.get("city_hint"):
                draft["city"] = result["city_hint"]
            if not draft["province"] and result.get("province_hint"):
                draft["province"] = result["province_hint"]
        # H31 (S100), corrección real de Miguel Ángel: la imagen que
        # trae el número de afiliación "unas veces la coge como
        # tarjeta de la Seguridad Social y otras veces la pone como
        # que no la reconoce [...] realmente no es la tarjeta de la
        # Seguridad Social" -- la clasificación del documento que trae
        # este dato es inconsistente, pero el propio número es
        # bastante inequívoco. Se acepta de CUALQUIER documento, no
        # solo de ALTA/IDC/SEG_SOCIAL -- para no perderlo por una
        # clasificación de tipo que ni siquiera pretendía ser
        # determinante aquí.
        if not draft["ss_affiliation_number"] and result.get("ss_number_hint"):
            draft["ss_affiliation_number"] = result["ss_number_hint"]
        if doc_type == "CONTRATO":
            if not draft["employer_company"] and result.get("employer_company_hint"):
                draft["employer_company"] = normalize_employer_company(
                    result["employer_company_hint"],
                )
            if not draft["hire_date"] and result.get("hire_date_hint"):
                draft["hire_date"] = result["hire_date_hint"]
    return {"draft": draft, "warnings": warnings}
