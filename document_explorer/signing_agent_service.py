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
import re
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
# S153 (agente v3): avisar de la caducidad del certificado de una
# empresa con esta antelación.
EXPIRY_WARNING_DAYS = 60
# CIF de la empresa en un certificado de representante: "(R: B29405040)"
# en el nombre, o el identificador de organización "VATES-B29405040".
_CIF_IN_NAME = re.compile(r"\(R:\s*([A-Z0-9]{8,10})\)", re.IGNORECASE)
_CIF_IN_OID = re.compile(r"(?:OID\.2\.5\.4\.97|organizationIdentifier)"
                         r"\s*=\s*VAT[A-Z]{2}-([A-Z0-9]{8,10})",
                         re.IGNORECASE)
_ORG = re.compile(r'(?:^|,\s*)O=("(?:[^"]|"")*"|[^,]*)')
_THUMBPRINT = re.compile(r"^[0-9A-F]{40}$")


class NoValidCertificate(Exception):
    """
    The company has no valid certificate on any agent.
    ---
    La empresa no tiene ningún certificado vigente en el agente.
    """


def parse_certificate(raw):
    """
    One certificate reported by the agent, or None if not a company one.
    ---
    Un certificado de los que cuenta el agente (huella, sujeto, nombre,
    fechas), normalizado; None si no es de representante de una empresa
    (sin CIF) o le falta algo.
    """
    if not isinstance(raw, dict):
        return None
    thumbprint = str(raw.get("t") or "").strip().upper()
    subject = str(raw.get("s") or "")
    if not _THUMBPRINT.match(thumbprint):
        return None
    match = _CIF_IN_NAME.search(subject) or _CIF_IN_OID.search(subject)
    if not match:
        return None
    try:
        not_before = datetime.date.fromisoformat(str(raw.get("a"))[:10])
        not_after = datetime.date.fromisoformat(str(raw.get("b"))[:10])
    except ValueError:
        return None
    org = _ORG.search(subject)
    company = org.group(1).strip().strip('"').replace('""', '"') if org \
        else ""
    return {
        "thumbprint": thumbprint,
        "cif": match.group(1).upper(),
        "company": company[:200],
        "holder": str(raw.get("n") or "")[:200],
        "not_before": not_before.isoformat(),
        "not_after": not_after.isoformat(),
    }


def company_certificates(today=None):
    """
    Company certificates seen by the active agents, by CIF.
    ---
    Los certificados de empresa que ven los agentes activos, agrupados
    por CIF (de más nuevo a más viejo), con el vigente que se usa al
    firmar ("current"), los días que le quedan y el nivel de aviso:
    "danger" si no hay ninguno vigente, "warning" si caduca en menos de
    EXPIRY_WARNING_DAYS días, "" si está bien.
    """
    today = today or timezone.localdate()
    by_cif = {}
    for agent in SigningAgent.objects.filter(is_active=True):
        for cert in agent.certificates or []:
            entry = by_cif.setdefault(cert["cif"], {
                "cif": cert["cif"], "company": cert["company"],
                "certs": {}})
            entry["certs"][cert["thumbprint"]] = cert
    result = []
    for entry in by_cif.values():
        certs = sorted(entry["certs"].values(),
                       key=lambda c: c["not_after"], reverse=True)
        for cert in certs:
            cert["valid"] = (cert["not_before"] <= today.isoformat()
                             <= cert["not_after"])
            cert["expires"] = datetime.date.fromisoformat(
                cert["not_after"])
        current = next((c for c in certs if c["valid"]), None)
        days = (current["expires"] - today).days if current else None
        if current is None:
            level = "danger"
        elif days <= EXPIRY_WARNING_DAYS:
            level = "warning"
        else:
            level = ""
        company = (current or certs[0])["company"] or entry["company"]
        last_expired = (certs[0]["expires"] if certs and not current
                        else None)
        # Situación concreta del aviso, para «No mostrar más».
        alert_key = ""
        if level:
            when = current["expires"] if current else last_expired
            alert_key = "%s:%s" % (level, when.isoformat() if when
                                   else "")
        result.append({
            "cif": entry["cif"], "company": company, "certs": certs,
            "current": current, "days": days, "level": level,
            "last_expired": last_expired, "alert_key": alert_key,
        })
    return sorted(result, key=lambda e: e["company"])


def current_certificate(cif, today=None):
    """
    The valid certificate to sign with for a CIF.
    ---
    El certificado vigente con el que se firma por ese CIF (el que más
    tarde caduca); NoValidCertificate si no hay ninguno.
    """
    for entry in company_certificates(today):
        if entry["cif"] == cif:
            if entry["current"] is None:
                raise NoValidCertificate(
                    "%s (%s) no tiene ningún certificado digital vigente "
                    "en el ordenador del agente%s. Hace falta uno nuevo." % (
                        entry["company"] or "La empresa", cif,
                        " (el último caducó el %s)"
                        % entry["last_expired"].strftime("%d/%m/%Y")
                        if entry["last_expired"] else ""))
            return entry["current"]
    raise NoValidCertificate(
        "El agente no ve ningún certificado de la empresa %s. Comprueba "
        "que el agente está actualizado (versión 3) y encendido." % cif)


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


def record_heartbeat(agent, host="", aliases=None, autofirma="", error="",
                     certificates=None):
    """
    Save what the agent reports (PC, certificates, AutoFirma, error).
    ---
    Guarda lo que cuenta el agente: ordenador, certificados que ve
    (alias de AutoFirma y, desde la versión 3, los de empresa con su
    huella y fechas), versión de AutoFirma y último error.
    """
    agent.host = (host or "")[:255]
    if certificates is not None:
        parsed = [parse_certificate(raw) for raw in certificates[:200]]
        agent.certificates = [c for c in parsed if c]
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
    agent.save(update_fields=["host", "aliases", "certificates",
                              "autofirma_version", "last_error",
                              "last_seen_at"])


def create_job(signature, documents, notes, by, all_pages=False):
    """
    Queue generated PDFs [(name, bytes, config)] for the signature.
    ---
    Deja en cola los PDF generados [(nombre, bytes, configuración de la
    firma visible)] para que el agente los firme con el certificado de
    la firma elegida.
    """
    purge_old()
    alias, thumbprint = signature.certificate_alias, ""
    if signature.certificate_cif:
        # S153 (agente v3): el certificado vigente de la empresa, por su
        # huella; NoValidCertificate si no hay ninguno (no se encola).
        cert = current_certificate(signature.certificate_cif)
        thumbprint = cert["thumbprint"]
        alias = "%s (%s) · %s · hasta %s" % (
            cert["company"], cert["cif"], cert["holder"],
            cert["expires"].strftime("%d/%m/%Y"))
    with transaction.atomic():
        job = SignedFormJob.objects.create(
            signature=signature,
            certificate_alias=alias[:255],
            certificate_thumbprint=thumbprint, all_pages=all_pages,
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
