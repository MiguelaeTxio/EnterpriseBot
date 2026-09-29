# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/employer_service.py
"""
H30 (S125). Employer company of a worker taken from his/her own
contracts, not from the staff Excel.

---

H30 (S125). Empresa empleadora de un trabajador sacada de sus propios
contratos, no del Excel de plantilla. Miguel Ángel: "teniendo los
contratos deberíamos presentar la empresa correcta (con el nombre
normalizado) que se informe en el contrato y modificarla cuando se
actualice si procede."

- Manda el contrato más reciente (CONTRATO, prórroga o modificación,
  por fecha del contrato) que identifique la empresa.
- Caso limpio: el texto OCR ya guardado trae el CIF de UNA sola
  empresa del grupo (310 de 383 contratos reales, S125). Si no (dos
  CIF, ninguno, sin texto), Gemini lee el propio archivo y dice cuál de
  las empresas del grupo es la empleadora -- Miguel Ángel: "si nos va
  a dar problemas, llamamos a Gemini directamente".
- `employer_company` guarda la forma canónica que ya usa el sistema
  (filtro por empresa, carpeta ACTIVOS/{EMPRESA}, perfil fiscal); en
  pantalla se ve la razón social normalizada del `CompanyFiscalProfile`
  (`PersonIdentity.employer_legal_name`).
"""
import json
import logging
import re
import unicodedata

from django.contrib.contenttypes.models import ContentType
from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from ai_services.gemini_rate_limiter import acquire_gemini_slot
from document_explorer.models import (
    CompanyFiscalProfile, DocumentIndexEntry, PersonIdentity,
)
from document_explorer.personal_intake_service import (
    _KNOWN_EMPLOYER_COMPANIES,
)

logger = logging.getLogger(__name__)

CONTRACT_TYPE_CODES = (
    "CONTRATO", "PRORROGA_CONTRATO", "MODIFICACION_CONTRATO",
)
NONE_CODE = "NINGUNA"
_GEMINI_MIME_TYPES = {
    "application/pdf", "image/jpeg", "image/png", "image/webp",
}
_EMPLOYER_SCHEMA = {
    "type": "object",
    "properties": {"employer_tax_id": {"type": "string"}},
    "required": ["employer_tax_id"],
}


def _squash(value):
    """
    Uppercase, no accents, no spaces/dots/dashes/line breaks.

    ---

    Mayúsculas, sin acentos y sin espacios, puntos, guiones ni saltos
    de línea (así "B-29.405.040" casa con "B29405040").
    """
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"[\s.\-]", "", value.upper())


def canonical_employer_text(profile):
    """
    The employer_company text the system uses for a profile.

    ---

    El texto de `employer_company` que usa el sistema para una empresa:
    su variante en `_KNOWN_EMPLOYER_COMPANIES` (la misma del alta de
    personal nuevo), para que filtro, carpeta y perfil fiscal sigan
    casando. Si no hubiera ninguna, su primer alias.
    """
    aliases = [
        line.strip() for line in profile.name_aliases.splitlines()
        if line.strip()
    ]
    for alias in aliases:
        if alias.upper() in _KNOWN_EMPLOYER_COMPANIES:
            return alias
    return aliases[0] if aliases else profile.legal_name


def company_from_text(text):
    """
    The group company whose tax ID is the only one in the text, or None.

    ---

    La empresa del grupo cuyo CIF es el único del grupo que aparece en
    el texto, o None (ninguno, o varios -- entonces decide Gemini).
    """
    squashed = _squash(text)
    if not squashed:
        return None
    hits = [
        profile for profile in CompanyFiscalProfile.objects.all()
        if _squash(profile.tax_id) and _squash(profile.tax_id) in squashed
    ]
    return hits[0] if len(hits) == 1 else None


def company_from_file(entry):
    """
    Ask Gemini which group company is the employer in a contract file.

    ---

    Pregunta a Gemini, sobre el propio archivo del contrato, cuál de las
    empresas del grupo es la EMPLEADORA (nunca un cliente u otra parte
    que aparezca). None si no es ninguna o no se puede leer.
    """
    from spare_parts.gcs_service import download_bytes

    content_type = (entry.content_type or "").split(";")[0].lower()
    if content_type not in _GEMINI_MIME_TYPES:
        return None
    profiles = list(CompanyFiscalProfile.objects.all())
    options = "\n".join(
        "- %s: %s" % (profile.tax_id, profile.legal_name)
        for profile in profiles
    )
    prompt = (
        "Este archivo es un contrato de trabajo (o su prórroga o "
        "modificación) de una empresa española. De estas empresas, "
        "¿cuál es la EMPLEADORA, la que contrata al trabajador? No "
        "confundir con clientes, obras u otras empresas mencionadas.\n"
        "%s\n\n"
        "Responde employer_tax_id con el CIF de la lista que "
        "corresponda, o '%s' si ninguna de ellas es la empleadora o no "
        "se puede saber."
    ) % (options, NONE_CODE)
    data = download_bytes(entry.bucket, entry.blob_name)
    client = get_gemini_client()
    acquire_gemini_slot()
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=[Part.from_bytes(data=data, mime_type=content_type), prompt],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=90_000),
            response_mime_type="application/json",
            response_schema=_EMPLOYER_SCHEMA,
            temperature=0.0,
        ),
    )
    answer = _squash(
        json.loads(response.text.strip()).get("employer_tax_id"),
    )
    return next(
        (p for p in profiles if _squash(p.tax_id) == answer), None,
    )


def person_contracts(person):
    """
    The person's contracts, newest first (contract date).

    ---

    Contratos de la persona (contrato, prórroga, modificación), el más
    reciente primero por fecha del contrato.
    """
    return DocumentIndexEntry.objects.filter(
        entry_kind=DocumentIndexEntry.KIND_FILE,
        domain_content_type=ContentType.objects.get_for_model(
            PersonIdentity,
        ),
        domain_object_id=person.pk,
        document_type__code__in=CONTRACT_TYPE_CODES,
        deleted_at__isnull=True,
        purged_at__isnull=True,
    ).select_related("document_type").order_by(
        "-issue_date", "-period_start_date", "-indexed_at", "-pk",
    )


def employer_from_contracts(person, use_gemini=True):
    """
    Return (profile, contract, method, unresolved newer contracts).

    ---

    Devuelve (empresa, contrato que la informa, método "CIF"/"Gemini",
    contratos más recientes que no la identificaron). Empresa None si
    ningún contrato la identifica.
    """
    unresolved = []
    for contract in person_contracts(person):
        profile = company_from_text(contract.ocr_text)
        method = "CIF"
        if profile is None and use_gemini:
            try:
                profile = company_from_file(contract)
            except Exception:
                logger.exception(
                    "# [EMPLOYER] Gemini falló con el contrato %s",
                    contract.pk,
                )
                profile = None
            method = "Gemini"
        if profile is not None:
            return profile, contract, method, unresolved
        unresolved.append(contract)
    return None, None, "", unresolved


def refresh_employer_company(person, use_gemini=True, save=True):
    """
    Set the person's employer from the contracts, if it changes.

    ---

    Fija la empresa de la persona según sus contratos, solo si procede
    (hay un contrato que la identifica y es distinta de la actual).
    Devuelve un resumen para el registro o el informe.
    """
    profile, contract, method, unresolved = employer_from_contracts(
        person, use_gemini=use_gemini,
    )
    old = person.employer_company or ""
    result = {
        "person": person, "old": old, "new": old, "changed": False,
        "contract": contract, "method": method, "unresolved": unresolved,
        "profile": profile,
    }
    if profile is None:
        return result
    new = canonical_employer_text(profile)
    result["new"] = new
    if new != old:
        result["changed"] = True
        if save:
            person.employer_company = new
            person.save(update_fields=["employer_company", "updated_at"])
            logger.info(
                "# [EMPLOYER] PersonIdentity pk=%s: empresa '%s' -> '%s' "
                "(contrato %s, %s).",
                person.pk, old, new, contract.pk, method,
            )
    return result


def refresh_after_contract(person, document_type_code):
    """
    Hook for every contract that enters (never raises).

    ---

    Enganche para todo contrato que entra (cuarentena, panel,
    WhatsApp): si el tipo es de contrato, recalcula la empresa. Nunca
    lanza excepción -- un fallo aquí no puede tumbar la ingesta.
    """
    if document_type_code not in CONTRACT_TYPE_CODES:
        return None
    try:
        return refresh_employer_company(person)
    except Exception:
        logger.exception(
            "# [EMPLOYER] No se pudo recalcular la empresa de %s",
            person.pk,
        )
        return None
