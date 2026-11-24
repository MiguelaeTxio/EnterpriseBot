# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/mail_service.py
"""
Read the CAE notices uploaded by the mail agent and extract demands.

---

H31 (S156). Lee los avisos de las plataformas CAE que el agente de
correos sube al cubo y saca lo que pide cada uno.

1. `sweep_new_mails` (cada 5 minutos): cada carpeta de
   CORREOS DOCUMENTACION/NUEVOS con su `correo.json` (el agente la sube
   la ultima) se registra una vez. Yolanda reenvia los avisos como
   adjunto: cada `.msg` adjunto es un aviso original (`CaeMail`). Un
   correo sin `.msg` es el aviso en si.
2. `process_mail`: abre el aviso (extract_msg), pide a Gemini la
   plataforma, el cliente, la empresa del grupo y cada documento que
   pide (`CaeDemand`). Un aviso que solo trae un recuento o un enlace
   queda leido, sin demandas y con su resumen.

Gemini saturado (429) se reintenta desde la tarea; en el ultimo
intento queda como error visible.
"""
import datetime
import hashlib
import json
import logging
import os
import re
import tempfile

import extract_msg
from django.db import transaction
from django.utils import timezone
from google.genai.types import GenerateContentConfig, HttpOptions

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from document_explorer.classification_service import (
    _generate_content_with_retry,
)
from spare_parts.gcs_service import download_bytes, get_storage_client

from .models import CaeDemand, CaeMail
from .subjects import link_demand

logger = logging.getLogger(__name__)

BUCKET = "cgs_grupo_alvarez"
NEW_PREFIX = "CORREOS DOCUMENTACION/NUEVOS/"
MAIL_JSON_NAME = "correo.json"
# Texto maximo del aviso que se manda a Gemini.
MAX_PROMPT_CHARS = 40000
# Avisos ya leídos que el barrido vuelve a encolar para releer (S156).
_REQUEUE_BATCH = 20

# Plataforma por el dominio del remitente (el mismo nombre siempre,
# sin depender de como lo escriba Gemini). Lo que no este aqui lo
# nombra Gemini.
DOMAIN_PLATFORMS = {
    "egestiona.com": "egestiona",
    "egestiona.es": "egestiona",
    "sercae.com": "SerCAE",
    "quironprevencion.com": "Quioo",
    "jeveal.com": "Jeveal",
    "delamallorente.com": "Nidus Prevención",
    "cellnextelecom.com": "Cellnex (Cosmos)",
    "e-coordina.com": "e-coordina",
    "twind.io": "Twind",
    "seyses.com": "SEYSES",
    "nalandaglobal.com": "Nalanda",
    "grupompe.es": "MPE",
}

_PROMPT = """Eres el asistente del departamento de documentación de un \
grupo de empresas de grúas (Grúas Adolfo Álvarez S.L., Transgrual S.L.). \
Te paso un correo de una plataforma de coordinación de actividades \
empresariales (CAE) de un cliente. Devuelve en JSON:

- platform: nombre de la plataforma (egestiona, SerCAE, Quioo, Nidus, \
Jeveal, Twind, e-coordina, Cellnex, SEYSES, Nalanda...).
- client: el cliente o centro de trabajo para el que se pide la \
documentación (por ejemplo "Totem", "Orange", "Endesa", "Limasam"), o \
vacío si no se dice.
- our_company: la empresa del grupo a la que va dirigido (tal cual \
aparece), o vacío.
- summary: una o dos frases en castellano con lo que dice el correo.
- has_detail: true si el correo dice qué documentos concretos pide o \
cuáles caducan; false si solo da un recuento, un enlace o un aviso \
genérico.
- demands: una entrada por cada documento concreto que se pide, falta, \
caduca o cambia de estado, solo si el correo lo dice expresamente. \
Cada una con:
  - subject_type: EMPRESA, TRABAJADOR, MAQUINA u OTRO.
  - subject_name: nombre del trabajador, de la máquina (descripción o \
código interno, p. ej. "B-23") o de la empresa.
  - subject_ref: DNI/NIE del trabajador o matrícula de la máquina \
(p. ej. "1532DVF"), o vacío.
  - document: el documento tal cual lo nombra la plataforma.
  - state: estado o motivo (pendiente, caducado, próximo a caducar, \
rechazado, no apto, apto...).
  - due_date: fecha límite o de caducidad en formato AAAA-MM-DD, o vacío.
  - site: centro, obra o proyecto si se indica, o vacío.
  - document_type_code: el código del CATÁLOGO de abajo que corresponde \
a ese documento, o vacío si ninguno encaja. Los de dominio COMPANY son \
de la empresa, PERSONAL de un trabajador y MACHINE de una máquina.

No inventes nada que no esté en el correo.

CATÁLOGO (código — nombre — dominio):
{catalog}

CORREO:
"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "string"},
        "client": {"type": "string"},
        "our_company": {"type": "string"},
        "summary": {"type": "string"},
        "has_detail": {"type": "boolean"},
        "demands": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject_type": {
                        "type": "string",
                        "enum": ["EMPRESA", "TRABAJADOR", "MAQUINA", "OTRO"],
                    },
                    "subject_name": {"type": "string"},
                    "subject_ref": {"type": "string"},
                    "document": {"type": "string"},
                    "state": {"type": "string"},
                    "due_date": {"type": "string"},
                    "site": {"type": "string"},
                    "document_type_code": {"type": "string"},
                },
                "required": [
                    "subject_type", "subject_name", "subject_ref",
                    "document", "state", "due_date", "site",
                    "document_type_code",
                ],
            },
        },
    },
    "required": [
        "platform", "client", "our_company", "summary", "has_detail",
        "demands",
    ],
}


class TransientMailError(Exception):
    """
    Gemini saturated or unavailable: try again later.

    ---

    Gemini saturado o caído: se reintenta más tarde.
    """


def _mail_key(prefix, attachment_name):
    source = "%s|%s" % (prefix, attachment_name)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _aware(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value)
    return value


def _parse_iso(value):
    try:
        return _aware(datetime.datetime.fromisoformat(value))
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    try:
        return datetime.date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def _platform_for(address):
    domain = (address or "").lower().rsplit("@", 1)[-1]
    for known, name in DOMAIN_PLATFORMS.items():
        if domain == known or domain.endswith("." + known):
            return name
    return ""


def sweep_new_mails():
    """
    Register the mails uploaded since the last sweep, one row per notice.

    ---

    Registra los correos subidos desde el último barrido: un CaeMail
    por cada .msg adjunto (o por el correo si no trae ninguno) y lo
    manda a procesar. Devuelve cuántos avisos ha registrado.
    """
    from .tasks import process_cae_mail_task

    known = set(CaeMail.objects.values_list("source_prefix", flat=True))
    blobs = get_storage_client().bucket(BUCKET).list_blobs(
        prefix=NEW_PREFIX)
    folders = sorted({
        blob.name[:-len(MAIL_JSON_NAME) - 1] for blob in blobs
        if blob.name.endswith("/" + MAIL_JSON_NAME)
    })
    registered = []
    for folder in folders:
        if folder in known:
            continue
        record = json.loads(download_bytes(
            BUCKET, "%s/%s" % (folder, MAIL_JSON_NAME)).decode("utf-8"))
        forwarded_at = _parse_iso(record.get("received")) or timezone.now()
        originals = [
            item["name"] for item in record.get("attachments", [])
            if item.get("name", "").lower().endswith(".msg")
        ] or [""]
        with transaction.atomic():
            for name in originals:
                mail, created = CaeMail.objects.get_or_create(
                    key=_mail_key(folder, name),
                    defaults={"source_prefix": folder,
                              "attachment_name": name,
                              "forwarded_at": forwarded_at},
                )
                if created:
                    registered.append(mail.pk)
    # S156: los avisos ya leídos que han vuelto a PENDIENTE para
    # releerse (la migración 0002, o «Volver a leer» en la pantalla de
    # avisos) se encolan aquí, como mucho _REQUEUE_BATCH por barrido.
    # Los que nunca se han leído (processed_at vacío) ya los encola su
    # registro o su propio reintento: no se duplican.
    pending = list(CaeMail.objects.filter(
        status=CaeMail.STATUS_PENDING, processed_at__isnull=False,
    ).exclude(pk__in=registered).order_by("pk").values_list(
        "pk", flat=True)[:_REQUEUE_BATCH])
    # Una sola vez: desde aquí sigue el camino de un aviso nuevo.
    CaeMail.objects.filter(pk__in=pending).update(processed_at=None)
    for pk in registered + pending:
        transaction.on_commit(
            lambda pk=pk: process_cae_mail_task.delay(pk))
    return len(registered)


def _read_msg(data):
    """
    Sender, date, subject and text of a .msg file.

    ---

    Remitente, fecha, asunto y texto de un .msg. Se escribe a un
    temporal porque extract_msg trabaja sobre archivos.
    """
    handle, path = tempfile.mkstemp(suffix=".msg")
    try:
        with os.fdopen(handle, "wb") as temp:
            temp.write(data)
        message = extract_msg.Message(path)
        try:
            sender = message.sender or ""
            match = re.search(r"<([^>]+)>", sender)
            address = match.group(1) if match else sender
            name = sender.split("<")[0].strip().strip('"') if match else ""
            return {
                "sender_name": name,
                "sender_address": address.strip(),
                "subject": message.subject or "",
                "received_at": _aware(message.date)
                if isinstance(message.date, datetime.datetime) else None,
                "body_text": re.sub(r"\n\s*\n+", "\n",
                                    message.body or "").strip(),
                "attachments": [
                    getattr(a, "longFilename", None)
                    or getattr(a, "shortFilename", None) or "?"
                    for a in message.attachments
                ],
            }
        finally:
            message.close()
    finally:
        os.remove(path)


def _read_original(mail):
    """
    The original notice: the attached .msg, or the mail itself.

    ---

    El aviso original: el .msg adjunto, o el propio correo.
    """
    if mail.attachment_name:
        return _read_msg(download_bytes(
            BUCKET, "%s/%s" % (mail.source_prefix, mail.attachment_name)))
    record = json.loads(download_bytes(
        BUCKET, "%s/%s" % (mail.source_prefix, MAIL_JSON_NAME)
    ).decode("utf-8"))
    return {
        "sender_name": record.get("sender_name", ""),
        "sender_address": record.get("sender_address", ""),
        "subject": record.get("subject", ""),
        "received_at": _parse_iso(record.get("received")),
        "body_text": record.get("body", ""),
        "attachments": [item.get("name", "")
                        for item in record.get("attachments", [])
                        if not item.get("hidden")],
    }


def _catalog_text():
    """Active catalogue types for the prompt, one per line.
    ---
    Tipos activos del catálogo para el prompt, uno por línea.
    """
    from document_explorer.models import DocumentTypeCatalog

    return "\n".join(
        "%s — %s — %s" % (code, label, domain)
        for code, label, domain in DocumentTypeCatalog.objects.filter(
            is_active=True,
        ).order_by("domain", "code").values_list("code", "label", "domain")
    )


def _ask_gemini(original):
    text = "De: %s <%s>\nFecha: %s\nAsunto: %s\nAdjuntos: %s\n\n%s" % (
        original["sender_name"], original["sender_address"],
        original["received_at"], original["subject"],
        "; ".join(original["attachments"]) or "-",
        original["body_text"][:MAX_PROMPT_CHARS],
    )
    response = _generate_content_with_retry(
        get_gemini_client(),
        model=DEFAULT_MODEL,
        contents=[_PROMPT.format(catalog=_catalog_text()) + text],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=180_000),
            response_mime_type="application/json",
            response_schema=_SCHEMA,
            temperature=0.0,
        ),
    )
    return json.loads(response.text.strip())


def process_mail(mail_id, final=False):
    """
    Read one notice and store what it asks for.

    ---

    Lee un aviso y guarda lo que pide. TransientMailError si Gemini
    falla y quedan intentos; en el último, error visible. Devuelve el
    estado final.
    """
    mail = CaeMail.objects.filter(pk=mail_id).first()
    if mail is None or mail.status == CaeMail.STATUS_PROCESSED:
        return "skip"
    try:
        original = _read_original(mail)
    except Exception as exc:  # noqa: BLE001
        logger.exception("# [CAE] No se pudo abrir el aviso %s", mail.pk)
        mail.status = CaeMail.STATUS_ERROR
        mail.error = "No se pudo abrir el correo: %s" % exc
        mail.save(update_fields=["status", "error"])
        return mail.status
    mail.sender_name = original["sender_name"][:255]
    mail.sender_address = original["sender_address"][:255]
    mail.subject = original["subject"][:500]
    mail.received_at = original["received_at"]
    mail.body_text = original["body_text"]
    try:
        result = _ask_gemini(original)
    except Exception as exc:  # noqa: BLE001
        if not final:
            mail.save(update_fields=[
                "sender_name", "sender_address", "subject",
                "received_at", "body_text"])
            raise TransientMailError(str(exc)) from exc
        logger.exception("# [CAE] Gemini falló con el aviso %s", mail.pk)
        mail.status = CaeMail.STATUS_ERROR
        mail.error = "Gemini no pudo leer el aviso: %s" % exc
        mail.save()
        return mail.status
    with transaction.atomic():
        mail.platform = (_platform_for(mail.sender_address)
                         or result.get("platform", ""))[:100]
        mail.client = result.get("client", "")[:255]
        mail.our_company = result.get("our_company", "")[:255]
        mail.summary = result.get("summary", "")
        demands = result.get("demands") or []
        mail.has_detail = bool(result.get("has_detail")) and bool(demands)
        mail.status = CaeMail.STATUS_PROCESSED
        mail.error = ""
        mail.processed_at = timezone.now()
        mail.save()
        mail.demands.all().delete()
        CaeDemand.objects.bulk_create([
            link_demand(
                CaeDemand(
                    mail=mail,
                    subject_type=item.get("subject_type")
                    or CaeDemand.SUBJECT_OTHER,
                    subject_name=item.get("subject_name", "")[:255],
                    subject_ref=item.get("subject_ref", "")[:100],
                    document=(item.get("document") or "?")[:500],
                    state=item.get("state", "")[:255],
                    due_date=_parse_date(item.get("due_date")),
                    site=item.get("site", "")[:255],
                ),
                mail, (item.get("document_type_code") or "").strip(),
            )
            for item in demands
        ])
    logger.info("# [CAE] Aviso %s (%s): %d documento(s) pedidos.",
                mail.pk, mail.platform, len(demands))
    return mail.status
