# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/signing_agent_service.py
"""
S153. Digital signature through the signing agent (AutoFirma on the PC
that holds the company certificates).

---

S153. Firma digital con el agente de firmas. Miguel Ángel: el
certificado de la empresa está instalado en el ordenador de Yolanda y no
deja exportar la clave privada, así que no puede firmar el servidor. Los
documentos generados en la pestaña Firmas quedan en cola (cifrados); el
agente de ese ordenador los recoge, los firma con AutoFirma usando el
certificado de Windows (la clave no sale de allí) y los devuelve. El
agente se identifica con un código que se genera en la pestaña Firmas;
aquí solo se guarda su huella.
"""
import datetime
import hashlib
import secrets

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from document_explorer.confidential import decrypt, encrypt
from document_explorer.models import (
    SignedFormFile,
    SignedFormJob,
    SigningAgent,
)

TOKEN_BYTES = 32
# Un documento que el agente cogió y no devolvió en este tiempo vuelve a
# la cola (el ordenador se apagó a mitad, se cortó la conexión...).
STALE_MINUTES = 15
# Lo que tarda en quedar desconectado un agente sin dar señales.
ONLINE_MINUTES = 3
KEEP_DAYS = 7
MAX_FILES_PER_POLL = 5
NOT_ALIAS_PREFIXES = ("buscando tarjeta",)


def token_hash(token):
    """
    SHA-256 hex of an agent code.
    ---
    La huella SHA-256 de un código de agente.
    """
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def create_agent(name, by):
    """
    New agent; returns (agent, code). The code is shown only once.
    ---
    Crea un agente y devuelve (agente, código). El código solo se
    enseña esta vez: aquí se guarda su huella.
    """
    token = secrets.token_urlsafe(TOKEN_BYTES)
    agent = SigningAgent.objects.create(
        name=name, token_hash=token_hash(token), created_by=by)
    return agent, token


def agent_for_request(request):
    """
    The active agent of a request's Bearer code, or None.
    ---
    El agente activo del código que trae la petición
    (Authorization: Bearer ...), o None.
    """
    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ").strip()
    if not token:
        return None
    return SigningAgent.objects.filter(
        token_hash=token_hash(token), is_active=True).first()


def is_online(agent):
    """
    True if the agent was heard from in the last minutes.
    ---
    True si el agente ha dado señales en los últimos minutos.
    """
    return bool(agent.last_seen_at and timezone.now() - agent.last_seen_at
                < datetime.timedelta(minutes=ONLINE_MINUTES))


def record_heartbeat(agent, host="", aliases=None, autofirma="", error=""):
    """
    Save what the agent reports (PC, certificates, AutoFirma, error).
    ---
    Guarda lo que cuenta el agente: ordenador, certificados que ve,
    versión de AutoFirma y último error.
    """
    agent.host = (host or "")[:255]
    if aliases is not None:
        # S153: AutoFirma mezcla en la lista avisos que no son
        # certificados ("Buscando tarjeta compatible en el terminal 0
        # (Windows Hello for Business 1)"); fuera, y sin repetidos.
        clean = []
        for alias in (str(a).strip()[:255] for a in aliases):
            if alias and alias not in clean and not alias.lower(
                    ).startswith(NOT_ALIAS_PREFIXES):
                clean.append(alias)
        agent.aliases = clean[:50]
    agent.autofirma_version = (autofirma or "")[:120]
    agent.last_error = (error or "")[:2000]
    agent.last_seen_at = timezone.now()
    agent.save(update_fields=["host", "aliases", "autofirma_version",
                              "last_error", "last_seen_at"])


def create_job(signature, documents, notes, by):
    """
    Queue generated PDFs [(name, bytes, config)] for the signature.
    ---
    Deja en cola los PDF generados [(nombre, bytes, configuración de la
    firma visible)] para que el agente los firme con el certificado de
    la firma elegida.
    """
    purge_old()
    with transaction.atomic():
        job = SignedFormJob.objects.create(
            signature=signature,
            certificate_alias=signature.certificate_alias,
            notes=notes, created_by=by)
        SignedFormFile.objects.bulk_create([
            SignedFormFile(job=job, name=name,
                           unsigned_encrypted=encrypt(data),
                           signature_config=config or "")
            for name, data, config in documents
        ])
    return job


def take_pending(agent, limit=MAX_FILES_PER_POLL):
    """
    Hand the next files to sign to the agent (marked as signing).
    ---
    Entrega al agente los siguientes documentos a firmar y los marca
    como "firmándose". Los que se quedaron a medias hace rato vuelven a
    entregarse.
    """
    stale = timezone.now() - datetime.timedelta(minutes=STALE_MINUTES)
    with transaction.atomic():
        files = list(
            SignedFormFile.objects.select_for_update().filter(
                job__status=SignedFormJob.STATUS_PENDING,
            ).filter(
                Q(status=SignedFormFile.STATUS_PENDING)
                | Q(status=SignedFormFile.STATUS_SIGNING,
                    taken_at__lt=stale),
            ).select_related("job").order_by("pk")[:limit]
        )
        now = timezone.now()
        for item in files:
            item.status = SignedFormFile.STATUS_SIGNING
            item.taken_at = now
            item.save(update_fields=["status", "taken_at"])
    return files


def unsigned_pdf(item):
    """
    The generated PDF of a queued file.
    ---
    El PDF generado (sin firma digital) de un documento de la cola.
    """
    return decrypt(bytes(item.unsigned_encrypted))


def signed_pdf(item):
    """
    The signed PDF of a file.
    ---
    El PDF firmado de un documento.
    """
    return decrypt(bytes(item.signed_encrypted))


def finish_file(item, signed=None, error=""):
    """
    Store the agent's answer for one file and close the job if done.
    ---
    Guarda la respuesta del agente para un documento (el PDF firmado o
    el error) y, si ya no queda ninguno por firmar, cierra el lote.
    """
    if signed is not None:
        if not signed.startswith(b"%PDF"):
            signed, error = None, "el agente no ha devuelto un PDF"
    if signed is not None:
        item.signed_encrypted = encrypt(signed)
        item.status = SignedFormFile.STATUS_DONE
        item.error = ""
    else:
        item.status = SignedFormFile.STATUS_ERROR
        item.error = (error or "error desconocido")[:2000]
    item.save(update_fields=["signed_encrypted", "status", "error"])
    job = item.job
    statuses = set(job.files.values_list("status", flat=True))
    if statuses & {SignedFormFile.STATUS_PENDING,
                   SignedFormFile.STATUS_SIGNING}:
        return
    job.status = (SignedFormJob.STATUS_DONE
                  if statuses == {SignedFormFile.STATUS_DONE}
                  else SignedFormJob.STATUS_ERROR)
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "finished_at"])


def purge_old(days=KEEP_DAYS):
    """
    Delete jobs (and their PDFs) older than `days`.
    ---
    Borra los lotes (y sus PDF) de hace más de `days` días: la cola no
    es un archivo.
    """
    limit = timezone.now() - datetime.timedelta(days=days)
    SignedFormJob.objects.filter(created_at__lt=limit).delete()
