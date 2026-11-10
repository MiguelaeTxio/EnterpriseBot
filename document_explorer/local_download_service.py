# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/local_download_service.py
"""
H24 (S144). A worker's folder in the local OneDrive tree, kept by the
H28 agent.

---

H24 (S144). La carpeta de un trabajador en el árbol local de OneDrive,
que mantiene el agente H28 (Miguel Ángel: "se da de alta, se clasifica
en el cubo y descargamos a su carpeta de personal"; "poner inactivo a
una persona en el panel y que [...] en el local también la ponga en
inactivos").

El local NO sigue la organización del cubo (PERSONAL/ACTIVOS/<EMPRESA>):
sigue la vuestra, por categorías y con su carpeta de inactivos
(LOCAL_CONTAINERS). Reglas:

- La carpeta actual de la persona es la de su última descarga o, si no
  tiene ninguna, la carpeta local de la que se subieron sus documentos
  (el nombre del objeto en el cubo es su ruta en local). Si tiene, se
  conserva su nombre tal cual.
- La categoría sale de su sección (Administración, Guardas, Taller,
  Asistencia; el resto, OPERARIOS) y de si está activo o de baja.
- Una persona nueva: "APELLIDOS, NOMBRE (CÓDIGO)" con el código de su
  empresa (GR, TR, GL, AGG); en Asistencia, "NOMBRE APELLIDOS".
- Si cambia de sitio, el agente mueve la carpeta ENTERA, tal cual, con
  todo lo que tenga. Después descarga solo lo que se subió desde el
  panel (alta, ficha) y no está en local. Nunca toca nada fuera de la
  carpeta de la persona.
"""
import collections
import re
import unicodedata

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from .models import (
    DocumentIndexEntry, LocalDownloadJob, PersonIdentity,
    SystemAgentHeartbeat,
)

AGENT_NAME = "h28_migration_agent"
BUCKET = "cgs_grupo_alvarez"
LOCAL_ROOT = "DOC. PERSONAL/PERSONAL"
# Lo subido desde el panel vive solo en el cubo (estructura virtual).
PANEL_PREFIXES = (LOCAL_ROOT + "/ACTIVOS/", LOCAL_ROOT + "/INACTIVOS/")

OPERARIOS = "OPERARIOS"
TALLER = "TALLER"
ADMINISTRACION = "ADMINISTRACION"
GUARDA = "GUARDA"
ASISTENCIA = "PERSONAL ASISTENCIA GRANADA"
# Categoría -> (carpeta de activos, carpeta de inactivos).
LOCAL_CONTAINERS = {
    OPERARIOS: ("OPERARIOS", "OPERARIOS/TRABAJADORES INACTIVOS"),
    TALLER: ("TALLER", "TALLER/BAJAS"),
    ADMINISTRACION: ("ADMINISTRACION", "ADMINISTRACION/BAJAS"),
    GUARDA: ("GUARDA", "GUARDA/OBSOLETOS"),
    ASISTENCIA: (
        "PERSONAL ASISTENCIA GRANADA/TRABAJADORES TRANSGRUAL",
        "PERSONAL ASISTENCIA GRANADA/EX TRABAJADORES",
    ),
}
# Carpetas donde ya hay trabajadores, para reconocer la carpeta de una
# persona a partir de dónde se subieron sus documentos (las de bajas
# antiguas incluidas).
KNOWN_CONTAINERS = sorted(
    {c for pair in LOCAL_CONTAINERS.values() for c in pair}
    | {"BAJAS/OPERARIOS BAJAS", "BAJAS/BAJA PERSONAL"},
    key=len, reverse=True,
)
COMPANY_CODES = (
    ("TRANSGRUAL", "TR"),
    ("GRUALDI", "GL"),
    ("ASISTENCIA", "AGG"),
    # S146: texto canónico del alta ("ASIST.GRUAS GRANADA").
    ("GRANADA", "AGG"),
    ("ADOLFO", "GR"),
    ("GRUAS ALVAREZ", "GR"),
)


def _plain(text):
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).upper()


def _person_entries(person):
    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    # S149: sin los confidenciales (nóminas, S147): en el cubo están
    # cifrados y solo los abren el trabajador y quien los envió; en
    # local quedaría un archivo ilegible a la vista de todos.
    return DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=person_ct,
        domain_object_id=person.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        is_confidential=False,
    ).order_by("pk")


def person_folder_of(path):
    """
    The person folder a local path is in, or None.
    ---
    La carpeta de persona (categoría conocida + su carpeta) en la que
    está una ruta local, o None si no está en ninguna.
    """
    prefix = LOCAL_ROOT + "/"
    if not path.startswith(prefix):
        return None
    rest = path[len(prefix):]
    for container in KNOWN_CONTAINERS:
        if rest.startswith(container + "/"):
            name = rest[len(container) + 1:].split("/", 1)[0]
            if name and "/" in rest[len(container) + 1:]:
                return "%s/%s/%s" % (LOCAL_ROOT, container, name)
    return None


def current_local_folder(person):
    """
    Where the person's folder is now in the local tree, or "".
    ---
    Dónde está ahora la carpeta de la persona en local: la de su última
    descarga o, si no tiene, la carpeta de la que se subieron más
    documentos suyos; "" si no tiene ninguna.
    """
    last = LocalDownloadJob.objects.filter(person=person).exclude(
        folder="").order_by("-created_at", "-pk").first()
    if last is not None:
        return last.folder
    counts = collections.Counter(
        folder for folder in (
            person_folder_of(blob) for blob in _person_entries(
                person).values_list("blob_name", flat=True)
        ) if folder
    )
    return counts.most_common(1)[0][0] if counts else ""


def _category(person):
    from hr_calendar.clock_settings import current_sections

    section = current_sections([person.pk]).get(person.pk)
    name = _plain(section.name if section else "")
    if name.startswith("ADMINISTRACION"):
        return ADMINISTRACION
    if name.startswith("GUARDA"):
        return GUARDA
    if name.startswith("TALLER"):
        return TALLER
    if name == "ASISTENCIA":
        return ASISTENCIA
    return OPERARIOS


def new_folder_name(person, category):
    """
    Folder name for someone without a local folder yet.
    ---
    Nombre de la carpeta de quien todavía no tiene: "APELLIDOS, NOMBRE
    (CÓDIGO)"; en Asistencia, "NOMBRE APELLIDOS" (como las que hay).
    """
    surnames = " ".join(
        p for p in (person.first_surname, person.second_surname) if p)
    if category == ASISTENCIA:
        return _plain("%s %s" % (person.given_name, surnames)).strip()
    name = "%s, %s" % (surnames, person.given_name)
    code = _company_code(person)
    return _plain(name + (" (%s)" % code if code else "")).strip()


_CODE_SUFFIX = re.compile(r"\((TR|GR|GL|AGG)\)\s*$")


def _company_code(person):
    company = _plain(person.employer_company)
    return next((c for key, c in COMPANY_CODES if key in company), "")


def target_local_folder(person, current=""):
    """
    Where the person's folder must be (section and active or not).
    ---
    Dónde tiene que estar la carpeta: la categoría de su sección, la de
    activos o la de inactivos, con el nombre que ya tenga.
    """
    category = _category(person)
    active, inactive = LOCAL_CONTAINERS[category]
    container = active if person.is_active_employee else inactive
    name = current.rsplit("/", 1)[-1] if current else new_folder_name(
        person, category)
    # S146 (Miguel Ángel): en local las carpetas llevan el código de su
    # empresa (TR, GR, GL, AGG). Una carpeta que ya existe sin código lo
    # recibe; si ya trae uno entre paréntesis, se respeta tal cual.
    # Si trae exactamente uno de los códigos y la empresa ha cambiado
    # (S146: ARANDA REYES pasó de GR a Transgrual), se cambia el código;
    # variantes como "(PTE TR)" o "(TR AUX)" no se tocan.
    code = _company_code(person)
    if current and code:
        match = _CODE_SUFFIX.search(name)
        if match and match.group(1) != code:
            name = "%s(%s)" % (name[:match.start(1) - 1], code)
        elif category != ASISTENCIA and "(" not in name:
            name = "%s (%s)" % (name.rstrip(), code)
    return "%s/%s/%s" % (LOCAL_ROOT, container, name)


def snapshot_paths(person):
    """
    Kept for the callers: the local folder before a move.
    ---
    La carpeta local de la persona ANTES de moverla (baja,
    reactivación): de dónde la tiene que mover el agente.
    """
    return current_local_folder(person)


OBSOLETE_FOLDER = "OBSOLETOS"


def obsolete_moves(entries, current, target, panel_prefixes):
    """
    Local moves of superseded documents into OBSOLETOS (H31, S148).

    ---

    Movimientos en local de documentos sustituidos a la subcarpeta
    OBSOLETOS de la carpeta de su persona o máquina. Ruta local de cada
    uno: si se subió desde el panel, la que tiene en su carpeta (donde
    lo bajó el agente); si vino de local, su ruta original, solo si está
    dentro de la carpeta conocida (`current`, trasladada a `target` si
    la carpeta se mueve). Nunca fuera de la carpeta.
    """
    moves = []
    for blob, name in entries:
        if blob.startswith(panel_prefixes):
            path = "%s/%s" % (target, name)
        elif current and blob.startswith(current + "/"):
            path = target + blob[len(current):]
        else:
            continue
        dest = "%s/%s/%s" % (target, OBSOLETE_FOLDER,
                             path.rsplit("/", 1)[-1])
        if "/%s/" % OBSOLETE_FOLDER not in path[len(target):] + "/":
            moves.append({"path": path, "dest": dest})
    return moves


def create_for_person(person, requested_by=None, previous=None,
                      obsolete=(), always=False):
    """
    Create the job that leaves the person's local folder in place.
    ---
    Crea el trabajo que deja la carpeta local de la persona donde le
    toca. `previous` es su carpeta local antes del cambio
    (snapshot_paths); sin él, la de ahora. Archivos: solo lo subido
    desde el panel, que no está en local, a la raíz de su carpeta.
    `obsolete` (S148): pares (blob_name, name) de documentos sustituidos,
    que pasan a OBSOLETOS en local. None si no hay nada que hacer (ni
    carpeta conocida ni descargas), salvo con `always` (S148: alta sin
    documentos, el agente crea su carpeta vacía igualmente).
    """
    current = previous if previous is not None else current_local_folder(
        person)
    target = target_local_folder(person, current)
    files = [
        {"blob": blob, "path": "%s/%s" % (target, name)}
        for blob, name in _person_entries(person).values_list(
            "blob_name", "name")
        if blob.startswith(PANEL_PREFIXES)
    ]
    # S146 (Miguel Ángel, alta de ARANDA REYES): la carpeta de antes se
    # manda SIEMPRE que se conozca, aunque coincida con el destino. La
    # que dice el cubo es la de cuando se subió: si en local la movieron
    # a mano (p. ej. a TRABAJADORES INACTIVOS tras la baja), el agente
    # la busca por su nombre en las categorías conocidas.
    if not files and not current and not always:
        return None
    return LocalDownloadJob.objects.create(
        person=person, requested_by=requested_by, files=files,
        folder=target, previous_folder=current,
        obsolete_files=obsolete_moves(
            obsolete, current, target, PANEL_PREFIXES),
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
    return [
        {"id": job.pk, "files": job.files, "folder": job.folder,
         "previous_folder": job.previous_folder,
         "obsolete": job.obsolete_files}
        for job in jobs
    ]


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
        "folder": job.folder,
        "agent_minutes_since_beat": minutes,
    }
