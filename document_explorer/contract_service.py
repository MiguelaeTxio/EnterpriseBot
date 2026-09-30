# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/contract_service.py
"""
H30 (S125). Reads a labour contract (or its extension/modification)
with Gemini: employer, contract date and end date if fixed-term.

---

H30 (S125). Lee un contrato de trabajo (o su prórroga/modificación) con
Gemini: empresa empleadora, fecha del contrato y fecha de fin si es
temporal. Un único lector para:

- el comando `reread_active_contracts` (solo trabajadores ACTIVOS --
  Miguel Ángel, S125: "tendríamos que hacerlo única y exclusivamente
  con los trabajadores que hay activos para que reflejen bien la empresa
  en la que se encuentran y que las fechas y caducidades de los
  contratos son las correctas"; nunca se toca ni se reactiva a un
  inactivo);
- cada contrato que entra de un trabajador activo (enganche).

Por qué hace falta: de los 258 contratos/prórrogas/modificaciones de
los activos (consulta real S125), ningún contrato tenía fecha de fin --
un temporal ya vencido no se podía avisar como caducado.
"""
import json
import logging

from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from document_explorer.classification_service import (
    _generate_content_with_retry,
)
from document_explorer.models import CompanyFiscalProfile, DocumentIndexEntry
from document_explorer.subject_upload_service import content_type_of
from document_explorer.worker_request_service import _parse_iso
from spare_parts.gcs_service import download_bytes

logger = logging.getLogger(__name__)

NONE_CODE = "NINGUNA"
_GEMINI_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
_CONTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "employer_tax_id": {"type": "string"},
        "start_date": {"type": "string"},
        "end_date": {"type": "string"},
        "is_indefinite": {"type": "boolean"},
    },
    "required": [
        "employer_tax_id", "start_date", "end_date", "is_indefinite",
    ],
}


def _squash(value):
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def read_contract(entry):
    """
    Read employer, start and end date of one contract document.

    ---

    Lee empresa, fecha de inicio y fecha de fin de un documento de
    contrato. Devuelve un dict {profile, start_date, end_date,
    is_indefinite} (None en lo que no se lea), o None si el archivo no
    es legible para Gemini.
    """
    data = download_bytes(entry.bucket, entry.blob_name)
    mime = content_type_of(data, entry.name)
    if mime not in _GEMINI_TYPES:
        return None
    profiles = list(CompanyFiscalProfile.objects.all())
    options = "\n".join(
        "- %s: %s" % (profile.tax_id, profile.legal_name)
        for profile in profiles
    )
    prompt = (
        "Este archivo es un contrato de trabajo español, o su prórroga "
        "o modificación. Responde:\n"
        "- employer_tax_id: el CIF de la EMPRESA EMPLEADORA (la que "
        "contrata, nunca un cliente u obra) de esta lista, o '%s' si no "
        "es ninguna o no se puede saber:\n%s\n"
        "- start_date: fecha de inicio del contrato (en una prórroga, la "
        "fecha de inicio de la prórroga), AAAA-MM-DD, o cadena vacía.\n"
        "- end_date: fecha de fin si el contrato es de duración "
        "determinada y la fecha figura (o se deduce sin duda de inicio "
        "+ duración), AAAA-MM-DD; cadena vacía si es indefinido, de fin "
        "de obra sin fecha, o no se lee.\n"
        "- is_indefinite: true si es indefinido.\n"
        "No inventes ninguna fecha."
    ) % (NONE_CODE, options)
    response = _generate_content_with_retry(
        get_gemini_client(),
        model=DEFAULT_MODEL,
        contents=[Part.from_bytes(data=data, mime_type=mime), prompt],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=120_000),
            response_mime_type="application/json",
            response_schema=_CONTRACT_SCHEMA,
            temperature=0.0,
        ),
    )
    answer = json.loads(response.text.strip())
    tax_id = _squash(answer.get("employer_tax_id"))
    start = _parse_iso(answer.get("start_date"))
    end = _parse_iso(answer.get("end_date"))
    if start and end and end < start:
        end = None  # Imposible: nunca se guarda una fecha absurda.
    return {
        "profile": next(
            (p for p in profiles if _squash(p.tax_id) == tax_id), None,
        ),
        "start_date": start,
        "end_date": None if answer.get("is_indefinite") else end,
        "is_indefinite": bool(answer.get("is_indefinite")),
    }


def dates_to_write(entry, reading):
    """
    Fields that change on the entry according to a reading.

    ---

    Campos que cambian en el documento según una lectura. La fecha de
    inicio solo se escribe si se ha leído (nunca se borra una fecha
    existente por no leerla); la de fin se escribe si se lee, y se
    quita si el contrato es indefinido.
    """
    changes = {}
    if reading["start_date"] and reading["start_date"] != entry.issue_date:
        changes["issue_date"] = reading["start_date"]
    if reading["end_date"] and reading["end_date"] != entry.expiry_date:
        changes["expiry_date"] = reading["end_date"]
    elif reading["is_indefinite"] and entry.expiry_date is not None:
        changes["expiry_date"] = None
    return changes


def apply_reading(entry, reading):
    """
    Write the reading's dates on the entry. Returns the changes.

    ---

    Escribe en el documento las fechas de la lectura. Devuelve los
    cambios hechos.
    """
    changes = dates_to_write(entry, reading)
    if changes:
        DocumentIndexEntry.objects.filter(pk=entry.pk).update(**changes)
        for field, value in changes.items():
            setattr(entry, field, value)
        logger.info(
            "# [CONTRACT] Documento %s: %s", entry.pk, changes,
        )
    return changes
