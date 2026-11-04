# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/local_download_service.py
"""
H24 (S144). Download of a just-onboarded worker's files to the local
OneDrive tree, through the H28 agent.

---

H24 (S144). Descarga a la carpeta local de OneDrive de los documentos
de un trabajador recién dado de alta, a través del agente H28 (Miguel
Ángel: "descargamos a su carpeta de personal [...] solamente el que se
dé de alta en ese momento").

- `create_for_person()`: lo llama el alta (`PersonalCreateView`) tras
  subir y clasificar los documentos; apunta los archivos de esa
  persona, nada más.
- `claim_pending()` / `report()`: los usan los webhooks del agente
  (mismo token que el latido). El agente pide los trabajos sin
  terminar en cada barrido, descarga, avisa de cada archivo y, al
  terminar, cierra el trabajo. Un fallo se apunta y se reintenta en el
  barrido siguiente hasta completarla.
- `status_payload()`: lo que ve la pantalla de alta mientras espera.
"""
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from .models import (
    DocumentIndexEntry, LocalDownloadJob, PersonIdentity,
    SystemAgentHeartbeat,
)

AGENT_NAME = "h28_migration_agent"
BUCKET = "cgs_grupo_alvarez"


def create_for_person(person, requested_by=None):
    """
    Create the download job for the person's files; None if none.

    ---

    Crea el trabajo de descarga con los archivos de la persona (los
    recién subidos en el alta); None si no tiene ninguno.
    """
    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    entries = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=person_ct,
        domain_object_id=person.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).order_by("pk")
    files = [
        {"blob": entry.blob_name,
         "path": "%s/%s" % (entry.parent_path, entry.name)}
        for entry in entries
    ]
    if not files:
        return None
    return LocalDownloadJob.objects.create(
        person=person, requested_by=requested_by, files=files,
    )


def claim_pending(host=""):
    """
    Jobs not finished yet, marked as in progress for this host.

    ---

    Trabajos sin terminar (pendientes o a medias, que se reintentan),
    marcados como en curso por este equipo.
    """
    jobs = list(LocalDownloadJob.objects.exclude(
        status=LocalDownloadJob.STATUS_DONE,
    ).order_by("created_at"))
    now = timezone.now()
    for job in jobs:
        job.status = LocalDownloadJob.STATUS_IN_PROGRESS
        job.last_attempt_at = now
        job.host = (host or "")[:255]
        job.save(update_fields=["status", "last_attempt_at", "host"])
    return [{"id": job.pk, "files": job.files} for job in jobs]


def report(job, downloaded=None, error=None, done=False):
    """
    Progress from the agent: files downloaded, last error, finished.

    ---

    Avance que comunica el agente: archivos descargados, último error
    (vacío si va bien) y si la descarga ha terminado.
    """
    fields = []
    if downloaded is not None:
        job.downloaded_count = min(max(downloaded, 0), len(job.files))
        fields.append("downloaded_count")
    if error is not None:
        job.last_error = error[:2000]
        fields.append("last_error")
    if done:
        job.status = LocalDownloadJob.STATUS_DONE
        job.downloaded_count = len(job.files)
        job.last_error = ""
        job.finished_at = timezone.now()
        fields += [
            "status", "downloaded_count", "last_error", "finished_at",
        ]
    if fields:
        job.save(update_fields=sorted(set(fields)))
    return job


def status_payload(job):
    """
    What the onboarding screen shows while it waits.

    ---

    Lo que muestra la pantalla de alta mientras espera: estado,
    descargados/total, último error y el último latido del agente.
    """
    heartbeat = SystemAgentHeartbeat.objects.filter(
        agent_name=AGENT_NAME,
    ).first()
    minutes = None
    if heartbeat:
        minutes = int(
            (timezone.now() - heartbeat.last_beat_at).total_seconds() // 60
        )
    return {
        "id": job.pk,
        "status": job.status,
        "done": job.status == LocalDownloadJob.STATUS_DONE,
        "downloaded": job.downloaded_count,
        "total": len(job.files),
        "error": job.last_error,
        "host": job.host,
        "agent_minutes_since_beat": minutes,
    }
