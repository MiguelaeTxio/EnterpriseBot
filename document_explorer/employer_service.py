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

- SOLO trabajadores activos y SOLO a partir de ahora, al entrar un
  documento (Miguel Ángel, S125): lo que ya constaba (Excel histórico)
  se queda como estaba; nunca un barrido hacia atrás -- faltan contratos
  y se rompería lo que estaba bien. Si la empresa queda mal, el
  supervisor sube el contrato que falta. Un inactivo nunca se toca.
- Manda el contrato más reciente (CONTRATO, prórroga o modificación,
  por fecha del contrato) que identifique la empresa; si ningún
  contrato la identifica (trabajador nuevo solo con el alta), el alta
  más reciente.
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
from document_explorer.classification_service import (
    _generate_content_with_retry,
)
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
# Documentos que activan a un trabajador (S124) y que por tanto pueden
# llevarlo a ACTIVOS/{EMPRESA}/: los de contrato y el alta.
ACTIVATING_TYPE_CODES = CONTRACT_TYPE_CODES + ("ALTA",)
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
        "Este archivo es un documento laboral de una empresa española "
        "(contrato de trabajo, prórroga, modificación o alta en la "
        "Seguridad Social). De estas empresas, "
        "¿cuál es la EMPLEADORA, la que contrata al trabajador? No "
        "confundir con clientes, obras u otras empresas mencionadas.\n"
        "%s\n\n"
        "Responde employer_tax_id con el CIF de la lista que "
        "corresponda, o '%s' si ninguna de ellas es la empleadora o no "
        "se puede saber."
    ) % (options, NONE_CODE)
    data = download_bytes(entry.bucket, entry.blob_name)
    client = get_gemini_client()
    response = _generate_content_with_retry(
        client,
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


def person_contracts(person, codes=CONTRACT_TYPE_CODES):
    """
    The person's documents of those types, newest first.

    ---

    Documentos de la persona de esos tipos (por defecto contrato,
    prórroga, modificación), el más reciente primero por fecha.
    """
    return DocumentIndexEntry.objects.filter(
        entry_kind=DocumentIndexEntry.KIND_FILE,
        domain_content_type=ContentType.objects.get_for_model(
            PersonIdentity,
        ),
        domain_object_id=person.pk,
        document_type__code__in=codes,
        is_obsolete=False,  # S125: nunca un duplicado exacto obsoleto.
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
    documents = list(person_contracts(person)) + list(
        person_contracts(person, codes=("ALTA",)),
    )
    for contract in documents:
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


def refresh_after_contract(person, document_type_code, entry=None):
    """
    Hook for every contract or ALTA that enters (never raises).

    ---

    Enganche para todo contrato o alta que entra (cuarentena, panel,
    WhatsApp), SOLO para trabajadores activos: si es un contrato, lo
    lee (fechas y fin si es temporal, S125), recalcula la empresa y, si
    la persona no está en su carpeta ACTIVOS/{EMPRESA}/, traslada su
    documentación allí. A un inactivo no se le toca nada ni se le
    activa. Nunca lanza excepción -- un fallo aquí no puede tumbar la
    ingesta. Se llama desde Celery (`queue_contract_refresh`).
    """
    from document_explorer.contract_service import (
        apply_reading, read_contract,
    )
    from document_explorer.person_folder_service import relocate_if_needed

    if document_type_code not in ACTIVATING_TYPE_CODES:
        return None
    if person.is_active_employee is not True:
        return None
    result = None
    try:
        if entry is not None and document_type_code in CONTRACT_TYPE_CODES:
            reading = read_contract(entry)
            if reading is not None:
                apply_reading(entry, reading)
        result = refresh_employer_company(person)
        relocated, folder, moved = relocate_if_needed(person)
        result["relocated_to"] = folder if relocated else ""
    except Exception:
        logger.exception(
            "# [EMPLOYER] No se pudo actualizar empresa/carpeta de %s",
            person.pk,
        )
    return result


def queue_contract_refresh(person, document_type_code, entry):
    """
    Queue the hook after the current transaction (Gemini is slow).

    ---

    Encola el enganche al confirmar la transacción en curso: Gemini
    tarda y nunca debe ir dentro de la petición web de una subida.
    """
    from django.db import transaction

    from document_explorer.tasks import refresh_contract_task

    if document_type_code not in ACTIVATING_TYPE_CODES:
        return
    if person.is_active_employee is not True:
        return
    transaction.on_commit(lambda: refresh_contract_task.delay(
        person.pk, document_type_code, entry.pk if entry else None,
    ))
