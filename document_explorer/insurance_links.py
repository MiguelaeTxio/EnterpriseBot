# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/insurance_links.py
"""
Link the company's insurance documents to their group company (S156).

The insurance files of DOC. EMPRESA/SEGUROS were typed with the generic
receipt/policy type and linked to the single ivr_config.Company row, so
a CAE demand ("Justificante pago Seguro Responsabilidad Civil" of Grúas
Adolfo Álvarez) never found them. The Gemini reading already made for
the insurance reports (InsuranceDocumentReading) says the policyholder,
the kind of insurance and the period covered; this applies it.

---

Enlaza los seguros de la empresa a su empresa del grupo (S156), con la
lectura de Gemini que ya existe de los informes de seguros: tomador
(empresa del grupo por CIF o por nombre), tipo de seguro (subtipo de RC
o de accidentes de convenio) y periodo cubierto (emisión y caducidad).
Después, nombre canónico {EMPRESA}_{TIPO}_{FECHA}. Lo que no es de una
de las 4 empresas, o no tiene lectura, se deja como está.
"""
import datetime
import logging
import re

from django.contrib.contenttypes.models import ContentType
from django.db import close_old_connections

from document_explorer.buckets import PRIMARY_BUCKET
from document_explorer.cae_documents import (
    _COMPANY_TOKENS,
    _company_tax_id,
    _plain,
    rename_cae_entry,
)
from document_explorer.models import (
    CompanyFiscalProfile,
    DocumentIndexEntry,
    DocumentTypeCatalog,
)

logger = logging.getLogger(__name__)

INSURANCE_ROOT = "DOC. EMPRESA/SEGUROS"
GENERIC_CODES = ("RECIBO_SEGURO_EMPRESA", "POLIZA_SEGURO_EMPRESA")
SUBTYPE_CODES = {
    ("responsabilidad_civil", "recibo"): "RECIBO_SEGURO_RC_EMPRESA",
    ("responsabilidad_civil", "poliza"): "POLIZA_SEGURO_RC_EMPRESA",
    ("responsabilidad_civil", "certificado"): "POLIZA_SEGURO_RC_EMPRESA",
    ("accidentes_convenio", "recibo"): "RECIBO_SEGURO_ACCIDENTES_EMPRESA",
    ("accidentes_convenio", "poliza"): "POLIZA_SEGURO_ACCIDENTES_EMPRESA",
    ("accidentes_convenio", "certificado"):
        "POLIZA_SEGURO_ACCIDENTES_EMPRESA",
}
_TAX_ID_RE = re.compile(r"\b([A-HJ-NP-SUVW])[\s.-]?(\d{8})\b")
_BATCH = 300
# Lecturas con Gemini por pasada (una cada 10 minutos).
_READ_BATCH = 10


def _group_tax_id(policyholder):
    """Group company of a policyholder text, or None.
    ---
    Empresa del grupo del tomador: por su CIF si es de una de las 4; si
    no (o lleva un CIF equivocado), por el nombre.
    """
    text = _plain(policyholder)
    for letter, digits in _TAX_ID_RE.findall(text):
        if letter + digits in _COMPANY_TOKENS:
            return letter + digits
    return _company_tax_id(text)


def _date(value):
    try:
        return datetime.date.fromisoformat(value) if value else None
    except ValueError:
        return None


def link_insurance_entry(entry, data, fiscal_ct, types):
    """Apply one insurance reading to its index entry. True if changed.
    ---
    Aplica la lectura de un seguro a su entrada del índice: empresa del
    grupo, subtipo y fechas; luego nombre canónico.
    """
    tax_id = _group_tax_id(data.get("policyholder") or "")
    company = (
        CompanyFiscalProfile.objects.filter(tax_id=tax_id).first()
        if tax_id else None
    )
    if company is None or data.get("document_kind") == "no_es_seguro":
        return False
    entry.domain_content_type = fiscal_ct
    entry.domain_object_id = company.pk
    fields = ["domain_content_type", "domain_object_id"]
    code = SUBTYPE_CODES.get(
        (data.get("category"), data.get("document_kind")))
    if code and code in types:
        entry.document_type = types[code]
        fields.append("document_type")
    start = _date(data.get("period_start"))
    end = _date(data.get("period_end"))
    if start:
        entry.issue_date = start
        fields.append("issue_date")
    if end:
        entry.expiry_date = end
        fields.append("expiry_date")
    entry.save(update_fields=fields)
    rename_cae_entry(entry)
    return True


def link_insurance(limit=_BATCH):
    """Link the read insurance files not yet tied to a group company.
    ---
    Enlaza los seguros de DOC. EMPRESA/SEGUROS con lectura que aún no
    están enlazados a una empresa del grupo. Devuelve cuántos.
    """
    fiscal_ct = ContentType.objects.get_for_model(CompanyFiscalProfile)
    types = {
        row.code: row for row in DocumentTypeCatalog.objects.filter(
            code__in=set(SUBTYPE_CODES.values()))
    }
    entries = list(DocumentIndexEntry.objects.filter(
        bucket=PRIMARY_BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        parent_path__startswith=INSURANCE_ROOT,
        document_type__code__in=GENERIC_CODES,
        insurance_reading__isnull=False,
        insurance_reading__data__isnull=False,
    ).exclude(domain_content_type=fiscal_ct).select_related(
        "document_type", "insurance_reading")[:limit])
    linked = 0
    for entry in entries:
        close_old_connections()
        try:
            linked += int(link_insurance_entry(
                entry, entry.insurance_reading.data, fiscal_ct, types))
        except Exception:
            logger.exception("# [insurance_links] No se pudo enlazar %s",
                             entry.pk)
    return linked


def read_new_insurance(limit=_READ_BATCH):
    """Read with Gemini the company insurance files never read (S156).
    ---
    Lee con Gemini los seguros de DOC. EMPRESA/SEGUROS que nunca se han
    leído o que han cambiado (otro md5), para que se enlacen a su
    empresa sin esperar a un informe de seguros. Los que fallaron no se
    reintentan aquí (los reintenta el informe). Devuelve cuántos.
    """
    from insurance import readings

    entries = [
        entry for entry in DocumentIndexEntry.objects.filter(
            bucket=PRIMARY_BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            parent_path__startswith=INSURANCE_ROOT,
            document_type__code__in=GENERIC_CODES,
        ).select_related("insurance_reading")
        if readings.mime_type(entry) is not None
        and not any(
            word in (entry.parent_path + "/" + entry.name).upper()
            for word in readings.EXCLUDED_PATH_WORDS)
        and _needs_reading(entry)
    ][:limit]
    done = 0
    for entry in entries:
        close_old_connections()
        _data, error = readings.read(entry)
        done += int(not error)
    return done


def _needs_reading(entry):
    try:
        reading = entry.insurance_reading
    except Exception:  # RelatedObjectDoesNotExist: sin lectura
        return True
    return (entry.md5_hash or "") != reading.md5_hash
