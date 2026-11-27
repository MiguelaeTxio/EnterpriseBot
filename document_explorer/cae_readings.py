# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/cae_readings.py
"""
Type by content the past-month CAE files the name rules cannot (S156).

The monthly folders of 2023-2025 of each company ("CERTIF. SS. SS., TC´S
Y HACIENDA/<year>/<month>") hold many files whose name says nothing
("1641930014.pdf", "GR TGSS 01.pdf", "CERTIFICADO GRUAS.pdf"). Miguel
Ángel (27/11/2026): read them by their content with Gemini, limited to
the CAE company types. The month comes from the folder, as with the
rules; the company, from the path.

---

Tipa por su contenido los archivos CAE de meses anteriores que las
reglas por el nombre no saben tipar, con Gemini y limitado a los tipos
de empresa de la CAE. El mes sale de la carpeta y la empresa de la
ruta, igual que con las reglas. Cada archivo se lee una vez (por
contenido): un fallo o un «no es de la CAE» no se repite.
"""
import json
import logging

from django.db import close_old_connections

from document_explorer.buckets import CAE_ROOT, PRIMARY_BUCKET
from document_explorer.cae_documents import type_cae_entry
from document_explorer.models import (
    CaeDocumentReading,
    DocumentIndexEntry,
    DocumentTypeCatalog,
)

logger = logging.getLogger(__name__)

# Tipos que se pueden leer: los de empresa de la CAE.
CAE_CODES = (
    "TC1_EMPRESA", "TC2_EMPRESA", "RECIBO_LIQUIDACION_SS", "ITA_EMPRESA",
    "VIDA_LABORAL_EMPRESA", "CERT_CORRIENTE_SS_EMPRESA", "CERT_ART42_TGSS",
    "CERT_CORRIENTE_AEAT", "CERT_REA", "RECIBO_IAE",
)
HISTORY_MARK = "Y HACIENDA/20"
_READ_BATCH = 20
_MIMES = {"pdf": "application/pdf", "jpg": "image/jpeg",
          "jpeg": "image/jpeg", "png": "image/png"}

PROMPT = """Eres un administrativo de una empresa de grúas española.
Te paso un documento de la carpeta mensual de Seguridad Social y
Hacienda de la empresa. Di de qué tipo es, eligiendo SOLO uno de estos
códigos, o "" si no es ninguno:
{catalog}

Pistas: el TC1 es la «Relación nominal»/«Recibo de liquidación de
cotizaciones» resumido por empresa; el TC2 es la relación nominal de
trabajadores; el recibo de liquidación es el justificante de pago a la
Seguridad Social; el certificado de estar al corriente lo emite la
TGSS o la AEAT; el del artículo 42 es el de la TGSS para contratistas.
Responde solo con el JSON pedido."""

SCHEMA = {
    "type": "object",
    "properties": {"document_type_code": {"type": "string"}},
    "required": ["document_type_code"],
}


def _catalog():
    rows = DocumentTypeCatalog.objects.filter(
        code__in=CAE_CODES).values_list("code", "label")
    return "\n".join("- %s: %s" % row for row in rows)


def _pending(limit):
    return list(DocumentIndexEntry.objects.filter(
        bucket=PRIMARY_BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        parent_path__startswith=CAE_ROOT + "/",
        parent_path__contains=HISTORY_MARK,
        document_type__isnull=True, cae_reading__isnull=True,
    ).order_by("pk")[:limit])


def _read_code(entry, storage, client, catalog):
    from google.genai.types import GenerateContentConfig
    from google.genai.types import HttpOptions
    from google.genai.types import Part
    from google.genai.types import ThinkingConfig

    from ai_services.document_vision_service import (
        _generate_content_with_retry)
    from ai_services.gemini_client import DEFAULT_MODEL
    from insurance.readings import _first_pages

    extension = entry.name.rsplit(".", 1)[-1].lower()
    mime = _MIMES.get(extension)
    if mime is None:
        return ""
    blob = storage.bucket(entry.bucket).get_blob(entry.blob_name)
    if blob is None:
        raise ValueError("no está en el cubo")
    content = blob.download_as_bytes()
    if mime == "application/pdf":
        content = _first_pages(content)
    response = _generate_content_with_retry(
        client, model=DEFAULT_MODEL,
        contents=[Part.from_bytes(data=content, mime_type=mime),
                  PROMPT.format(catalog=catalog)],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=120_000),
            response_mime_type="application/json",
            response_schema=SCHEMA,
            thinking_config=ThinkingConfig(thinking_level="low"),
            temperature=0.0,
        ),
    )
    code = (json.loads(response.text.strip()).get("document_type_code")
            or "").strip()
    return code if code in CAE_CODES else ""


def read_untyped_history(limit=_READ_BATCH):
    """Rules first, then Gemini, for untyped past-month CAE files.
    ---
    Para los archivos CAE de meses anteriores sin tipo: primero otra vez
    las reglas (las nuevas, «VIDA CCC», «REA»...) y, si siguen sin tipo,
    la lectura con Gemini. Devuelve cuántos ha tipado.
    """
    from ai_services.gemini_client import get_gemini_client
    from spare_parts.gcs_service import get_storage_client

    entries = _pending(limit)
    if not entries:
        return 0
    storage, client, catalog = None, None, _catalog()
    typed = 0
    for entry in entries:
        close_old_connections()
        try:
            if type_cae_entry(entry):
                typed += 1
                continue
        except Exception:  # noqa: BLE001
            logger.exception("# [cae_readings] reglas %s", entry.pk)
        code, error = "", ""
        try:
            storage = storage or get_storage_client()
            client = client or get_gemini_client()
            code = _read_code(entry, storage, client, catalog)
        except Exception as exc:  # noqa: BLE001 -- se guarda y se sigue
            error = str(exc)[:500] or exc.__class__.__name__
            logger.warning("# [cae_readings] %s: %s", entry.pk, error)
        CaeDocumentReading.objects.update_or_create(
            entry=entry, defaults={"md5_hash": entry.md5_hash or "",
                                   "code": code, "error": error})
        if code:
            try:
                typed += int(type_cae_entry(entry, code=code))
            except Exception:  # noqa: BLE001
                logger.exception("# [cae_readings] tipar %s", entry.pk)
    return typed
