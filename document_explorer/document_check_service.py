# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/document_check_service.py
"""
Check of a document uploaded from a subject's file (S130).

Miguel Ángel uploaded the insurance receipt of van X12 as "Carta
verde" (the right type was hidden from the list) and nothing noticed.
He asked for two things:

1. When a document is uploaded from the file of a machine or a worker,
   check that its content matches the chosen type and warn, never
   block, when it looks like another type ("esto parece un Recibo del
   seguro, no una Carta verde").
2. "Los datos a extraer que sean los que tienen que ser según
   documentos, que tenemos CDG sin matrícula": from each machine
   document, read the data that document really carries (plate, chassis
   number, make and model, insurer and policy) and fill the empty
   fields of the cost centre. Each field is only trusted from the
   document types that state it officially (`MACHINE_FACTS_BY_TYPE`);
   a field that already has a value is never overwritten -- a
   different value is reported instead.

One Gemini call per document: over the text already extracted
(embedded PDF text or Cloud Vision, cached in `ocr_text`) when there is
enough of it, otherwise over the file itself. Any failure returns an
empty result: the check never stops an upload.

---

Comprobación de un documento subido desde la ficha de un sujeto
(S130). Ver arriba: aviso (nunca bloqueo) si el contenido parece de
otro tipo, y relleno de los datos vacíos del centro de gasto con los
que el documento trae de verdad, cada dato solo desde los tipos que lo
acreditan; un dato que ya tiene valor nunca se sobrescribe, se avisa.
Una llamada a Gemini por documento, sobre el texto ya extraído si
basta, si no sobre el archivo. Cualquier fallo devuelve un resultado
vacío: la comprobación nunca para una subida.
"""

import json
import logging
import re

import fitz
from google.genai.errors import ServerError
from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from ai_services.gemini_rate_limiter import acquire_gemini_slot
from document_explorer.models import DocumentTypeCatalog

logger = logging.getLogger(__name__)

NO_TYPE = "NINGUNO"
MIN_TEXT_CHARS = 200
MAX_TEXT_CHARS = 12000
MAX_PDF_PAGES = 3
IMAGE_DPI = 150

# Machine fields each type states officially. Plate everywhere it is
# printed as the vehicle's own registration; chassis and make/model
# only from registration certificate, technical sheet and ITV; insurer
# and policy only from insurance documents.
# Campos de máquina que cada tipo acredita oficialmente.
_REGISTRATION = ("plate", "chassis_number", "brand_model")
_INSURANCE = ("plate", "insurer", "policy_number")
MACHINE_FACTS_BY_TYPE = {
    "PERMISO_CIRCULACION": _REGISTRATION,
    "FICHA_TECNICA": _REGISTRATION,
    "ITV": _REGISTRATION,
    "AUTORIZACION_PROVISIONAL_CIRCULACION": _REGISTRATION,
    "SEGURO": _INSURANCE,
    "POLIZA_SEGURO": _INSURANCE,
    "CARTA_VERDE": _INSURANCE,
    "CERTIFICADO_SEGURO": _INSURANCE,
}

FACT_LABELS = {
    "plate": "matrícula",
    "chassis_number": "bastidor",
    "brand_model": "marca y modelo",
    "insurance_info": "seguro",
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "detected_type_code": {"type": "string"},
        "detected_description": {"type": "string"},
        "plate": {"type": "string"},
        "chassis_number": {"type": "string"},
        "brand_model": {"type": "string"},
        "insurer": {"type": "string"},
        "policy_number": {"type": "string"},
    },
    "required": ["detected_type_code", "detected_description"],
}

# Current (1234BCD), special vehicles (E1234BCD), temporary (P1234BCD),
# trailers (R1234BCD, old MA01520R) and old provincial (MA1234BC,
# M123456). / Actual, especial, temporal, remolque y provincial antigua
# (S130: las de R3, R4 y A68 se rechazaban).
_PLATE_RE = re.compile(
    r"^(?:[0-9]{4}[A-Z]{3}|[EPR][0-9]{4}[A-Z]{3}"
    r"|[A-Z]{1,2}[0-9]{4}[A-Z]{0,2}|[A-Z]{1,2}[0-9]{5,6}"
    r"|[A-Z]{1,2}[0-9]{5}R)$"
)


def candidate_types(is_machine):
    """
    Active catalogue types of the subject's domain.
    ---
    Tipos activos del catálogo del dominio del sujeto.
    """
    domains = (
        DocumentTypeCatalog.DOMAIN_MACHINE if is_machine
        else DocumentTypeCatalog.DOMAIN_PERSONAL,
        DocumentTypeCatalog.DOMAIN_BOTH,
    )
    return list(DocumentTypeCatalog.objects.filter(
        is_active=True, domain__in=domains,
    ).exclude(family=DocumentTypeCatalog.FAMILY_MEDIA).order_by("label"))


def _prompt(candidates, chosen_type, is_machine):
    types_text = "\n".join(
        "- %s: %s" % (doc_type.code, doc_type.label) for doc_type in candidates
    )
    machine_part = (
        "- plate: matrícula del vehículo o máquina a la que se refiere el "
        "documento, sin espacios ni guiones (p. ej. 1234ABC, MA1234BC, "
        "E1234BCD); vacío si no aparece o si el documento cita varias.\n"
        "- chassis_number: número de bastidor (VIN) completo; vacío si no "
        "aparece.\n"
        "- brand_model: marca y modelo del vehículo; vacío si no aparece.\n"
        "- insurer: compañía aseguradora; vacío si no es un documento de "
        "seguro.\n"
        "- policy_number: número de póliza; vacío si no aparece.\n"
        if is_machine else
        "- plate, chassis_number, brand_model, insurer, policy_number: "
        "vacíos.\n"
    )
    return (
        "Eres un asistente que revisa documentación de un grupo de "
        "empresas de grúas y maquinaria en España. Un supervisor ha "
        "subido este documento indicando que es: %s (%s).\n"
        "Estos son los únicos tipos de documento posibles:\n%s\n\n"
        "Responde:\n"
        "- detected_type_code: el código de la lista que corresponde a lo "
        "que es REALMENTE el documento; si no es ninguno, '%s'.\n"
        "- detected_description: qué es el documento, en pocas palabras y "
        "en castellano.\n%s"
        "No inventes nada: deja vacío lo que no esté escrito en el "
        "documento."
    ) % (
        chosen_type.label, chosen_type.code, types_text, NO_TYPE,
        machine_part,
    )


def _ask_gemini(prompt, text, data, filename):
    if text and len(text.strip()) >= MIN_TEXT_CHARS:
        contents = [
            "Texto del documento:\n" + text[:MAX_TEXT_CHARS], prompt,
        ]
    else:
        lower = filename.lower()
        if lower.endswith(".pdf"):
            mime = "application/pdf"
        elif lower.endswith(".png"):
            mime = "image/png"
        elif lower.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        else:
            return None
        if mime == "application/pdf":
            images = _first_pages_as_images(data)
            contents = (
                [Part.from_bytes(data=image, mime_type="image/jpeg")
                 for image in images] + [prompt]
                if images else
                [Part.from_bytes(data=data, mime_type=mime), prompt]
            )
        else:
            contents = [Part.from_bytes(data=data, mime_type=mime), prompt]
    client = get_gemini_client()
    # S130: "Deadline expired" (504) real con PDFs escaneados largos en
    # la primera pasada; un reintento, y el PDF ya va recortado.
    for attempt in (1, 2):
        acquire_gemini_slot()
        try:
            response = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=contents,
                config=GenerateContentConfig(
                    http_options=HttpOptions(timeout=90_000),
                    response_mime_type="application/json",
                    response_schema=_SCHEMA,
                    temperature=0.0,
                ),
            )
            return json.loads(response.text.strip())
        except ServerError:
            if attempt == 2:
                raise
            logger.warning(
                "# [COMPROBACION] Gemini sin respuesta a tiempo con %s; "
                "reintento.", filename,
            )
    return None


def _first_pages_as_images(data):
    """
    First MAX_PDF_PAGES pages of a PDF as JPEG images at IMAGE_DPI.
    Plate, chassis and insurer are always on the first pages; sending
    the scanned PDF itself made Gemini time out (504 DEADLINE_EXCEEDED,
    S130), even cut to three pages. Rendering is not OCR. Returns []
    when the PDF cannot be opened (then the PDF goes as it is).
    ---
    Primeras MAX_PDF_PAGES páginas de un PDF como JPEG a IMAGE_DPI.
    Mandar el PDF escaneado hacía que Gemini no respondiera a tiempo
    incluso recortado a tres páginas (S130). Pintar no es OCR.
    """
    try:
        source = fitz.open(stream=data, filetype="pdf")
        return [
            source[index].get_pixmap(dpi=IMAGE_DPI).tobytes("jpeg")
            for index in range(min(source.page_count, MAX_PDF_PAGES))
        ]
    except Exception:  # noqa: BLE001 -- sin imágenes, el PDF tal cual
        return []


def normalize_plate(value):
    """
    Spanish plate without spaces or dashes, or "" if it does not look
    like one.
    ---
    Matrícula española sin espacios ni guiones, o "" si no lo parece.
    """
    plate = re.sub(r"[\s\-.]", "", (value or "").upper())
    return plate if _PLATE_RE.match(plate) else ""


def _same_type_family(chosen_code, detected_code):
    # Pairs scanned together in real files (permit + technical sheet,
    # policy + receipt): either reading is right, no warning.
    # Pares que en los archivos reales van escaneados juntos.
    from document_explorer.heuristic_type_service import DOSSIER_PAIRS

    return frozenset({chosen_code, detected_code}) in DOSSIER_PAIRS


def check_document(*, document_type, is_machine, data, filename, text):
    """
    Ask Gemini what the document is and what data it carries.

    Returns a dict (empty on any failure):
        {"type_mismatch": {"code", "label", "description"} or None,
         "facts": {"plate", "chassis_number", "brand_model",
                   "insurer", "policy_number"}}
    ---
    Pregunta a Gemini qué es el documento y qué datos trae.
    """
    candidates = candidate_types(is_machine)
    try:
        answer = _ask_gemini(
            _prompt(candidates, document_type, is_machine), text, data,
            filename,
        )
    except Exception:  # noqa: BLE001 -- nunca para la subida
        logger.exception(
            "# [COMPROBACION] Falló la lectura de %s (%s)",
            filename, document_type.code,
        )
        return {}
    if not answer:
        return {}

    result = {"type_mismatch": None, "facts": {}}
    detected = (answer.get("detected_type_code") or "").strip().upper()
    by_code = {doc_type.code: doc_type for doc_type in candidates}
    if (
        detected and detected != NO_TYPE and detected in by_code
        and detected != document_type.code
        and not _same_type_family(document_type.code, detected)
    ):
        result["type_mismatch"] = {
            "code": detected,
            "label": by_code[detected].label,
            "description": (answer.get("detected_description") or "").strip(),
        }
    if is_machine:
        result["facts"] = {
            "plate": normalize_plate(answer.get("plate")),
            "chassis_number": re.sub(
                r"\s", "", (answer.get("chassis_number") or "").upper(),
            )[:64],
            "brand_model": (answer.get("brand_model") or "").strip()[:200],
            "insurer": (answer.get("insurer") or "").strip()[:100],
            "policy_number": (answer.get("policy_number") or "").strip()[:60],
        }
    return result


def apply_machine_facts(machine, document_type_code, facts, save=True):
    """
    Fill the machine's EMPTY fields with the facts this document type
    states officially. Never overwrites: a different existing value is
    reported. Returns {"filled": {label: value}, "different":
    {label: (current, read)}}.
    ---
    Rellena los campos VACÍOS de la máquina con los datos que este tipo
    acredita. Nunca sobrescribe: un valor distinto se avisa.
    """
    allowed = MACHINE_FACTS_BY_TYPE.get(document_type_code, ())
    read = {}
    for name in ("plate", "chassis_number", "brand_model"):
        if name in allowed and facts.get(name):
            read[name] = facts[name]
    if "insurer" in allowed and facts.get("insurer"):
        insurance = facts["insurer"]
        if facts.get("policy_number"):
            insurance = "%s -- póliza %s" % (insurance, facts["policy_number"])
        read["insurance_info"] = insurance

    filled, different, update_fields = {}, {}, []
    for name, value in read.items():
        max_length = machine._meta.get_field(name).max_length
        value = value[:max_length] if max_length else value
        current = (getattr(machine, name) or "").strip()
        if not current:
            setattr(machine, name, value)
            update_fields.append(name)
            filled[FACT_LABELS[name]] = value
        elif name == "plate" and normalize_plate(current) not in ("", value):
            different[FACT_LABELS[name]] = (current, value)
        elif name == "chassis_number" and (
            re.sub(r"[^A-Z0-9]", "", current.upper())
            != re.sub(r"[^A-Z0-9]", "", value)
        ):
            different[FACT_LABELS[name]] = (current, value)
    if update_fields and save:
        machine.save(update_fields=update_fields)
        logger.info(
            "# [COMPROBACION] %s: datos tomados del documento (%s): %s",
            machine.code, document_type_code, filled,
        )
    return {"filled": filled, "different": different}


def _intake_prompt(candidates):
    types_text = "\n".join(
        "- %s: %s" % (doc_type.code, doc_type.label) for doc_type in candidates
    )
    return (
        "Eres un asistente que revisa documentación de un grupo de "
        "empresas de grúas y maquinaria en España. Un supervisor está "
        "dando de alta una máquina o vehículo nuevo con este documento.\n"
        "Estos son los únicos tipos de documento posibles:\n%s\n\n"
        "Responde:\n"
        "- detected_type_code: el código de la lista que corresponde a lo "
        "que es el documento; si no es ninguno, '%s'.\n"
        "- detected_description: qué es el documento, en pocas palabras y "
        "en castellano.\n"
        "- plate: matrícula del vehículo o máquina, sin espacios ni "
        "guiones; vacío si no aparece o si el documento cita varias.\n"
        "- chassis_number: número de bastidor (VIN) completo; vacío si no "
        "aparece.\n"
        "- brand_model: marca y modelo; vacío si no aparece.\n"
        "- insurer: compañía aseguradora; vacío si no es de seguro.\n"
        "- policy_number: número de póliza; vacío si no aparece.\n"
        "No inventes nada: deja vacío lo que no esté escrito en el "
        "documento."
    ) % (types_text, NO_TYPE)


def read_machine_document(data, filename):
    """
    Machine intake (S148): type and data of one document, no type chosen.

    Returns {"code", "label", "facts"}; code "" when not recognised.
    ---
    Alta de máquina por documentos (S148, Miguel Ángel: lo mismo que
    en Personal): qué es el documento y qué datos trae, sin tipo
    elegido. Texto incrustado del PDF o Cloud Vision (nunca OCR del
    servidor); si no basta, Gemini sobre las primeras páginas.
    """
    from document_explorer.cloud_vision_service import (
        cloud_vision_text, pdf_embedded_text,
    )

    candidates = candidate_types(True)
    text = ""
    if filename.lower().endswith(".pdf"):
        text = pdf_embedded_text(data)
    if len(text.strip()) < MIN_TEXT_CHARS:
        try:
            text = cloud_vision_text(data, filename) or text
        except Exception:  # noqa: BLE001 -- se cae a Gemini con el archivo
            logger.exception("# [ALTA MAQUINA] Cloud Vision falló: %s",
                             filename)
    answer = _ask_gemini(_intake_prompt(candidates), text, data, filename)
    answer = answer or {}
    by_code = {doc_type.code: doc_type for doc_type in candidates}
    code = (answer.get("detected_type_code") or "").strip().upper()
    if code not in by_code:
        code = ""
    facts = {
        "plate": normalize_plate(answer.get("plate")),
        "chassis_number": re.sub(
            r"\s", "", (answer.get("chassis_number") or "").upper(),
        )[:64],
        "brand_model": (answer.get("brand_model") or "").strip()[:200],
        "insurer": (answer.get("insurer") or "").strip()[:100],
        "policy_number": (answer.get("policy_number") or "").strip()[:60],
    }
    return {
        "code": code,
        "label": by_code[code].label if code else "",
        "description": (answer.get("detected_description") or "").strip(),
        "facts": facts,
        "text": text,
    }


def merge_machine_facts(readings):
    """
    The machine data of several readings, each field only from the
    types that state it (MACHINE_FACTS_BY_TYPE); the most repeated wins.
    ---
    Datos de máquina de varias lecturas: cada dato solo de los tipos que
    lo acreditan; gana el que más se repite.
    """
    import collections

    votes = collections.defaultdict(collections.Counter)
    for reading in readings:
        allowed = MACHINE_FACTS_BY_TYPE.get(reading.get("code"), ())
        facts = reading.get("facts") or {}
        for name in ("plate", "chassis_number", "brand_model"):
            if name in allowed and facts.get(name):
                votes[name][facts[name]] += 1
        if "insurer" in allowed and facts.get("insurer"):
            insurance = facts["insurer"]
            if facts.get("policy_number"):
                insurance = "%s -- póliza %s" % (
                    insurance, facts["policy_number"])
            votes["insurance_info"][insurance[:100]] += 1
    return {
        name: counter.most_common(1)[0][0]
        for name, counter in votes.items()
    }
