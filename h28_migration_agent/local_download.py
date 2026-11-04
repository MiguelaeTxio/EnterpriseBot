# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/local_download.py
"""Download a just-onboarded worker's files to the local tree (S144).
---
Descarga a la carpeta local de los documentos de un trabajador recien
dado de alta (H24, S144).

Miguel Angel: "meto los documentos en una carpeta temporal. Lo subo.
Se da de alta, se clasifica en el cubo y descargamos a su carpeta de
personal, a la carpeta creada que creamos para la persona en cuestion
con el formato que tenemos y pare usted de contar. Por una parte no
quiero que eso se vuelva a subir y por otra parte no quiero estar
vigilando todas las carpetas del cubo y bajarlas. No, quiero solamente
el que se de de alta en ese momento. Y ademas quiero que si hay un
error en la descarga, se termine esa descarga y cuando este
finalizada, termina el pipeline."

Como funciona:

- El servidor apunta un trabajo por cada alta, con los objetos de esa
  persona y su ruta en la carpeta virtual (`DOC. PERSONAL/PERSONAL/
  ACTIVOS/<EMPRESA>/<APELLIDOS NOMBRE>/...`). Nada mas: el agente no
  mira el resto del cubo.
- En cada ciclo del barrido, ANTES de barrer, el agente pide los
  trabajos sin terminar (`/panel/explorador/agente/descargas/`). Asi
  descarga y barrido nunca coinciden en el tiempo.
- Cada archivo se baja a un temporal `.partial` (el barrido ignora ese
  sufijo, `fs_utils.TRANSIENT_FILE_SUFFIXES`), se comprueba su MD5
  contra el del objeto y se renombra a su sitio.
- Para que no vuelva a subirse: se anota en el indice de la puesta al
  dia de esa carpeta (tamano y fecha, el barrido no lo ve como nuevo)
  y en el mapa de contenido ya en GCS (`known_contents`), por si
  OneDrive le cambiara la fecha al sincronizarlo.
- Un archivo que ya esta en local con el mismo MD5 no se vuelve a
  bajar: reintentar un trabajo a medias solo baja lo que falta.
- Un error se comunica al servidor y el trabajo sigue abierto: el
  ciclo siguiente lo reintenta, hasta completarlo. Solo entonces se
  cierra, y con el se cierra el alta en el panel.
---
The server records one job per onboarding with that person's objects
and their virtual folder path. Before each sweep the agent asks for
unfinished jobs, downloads each file to a `.partial` temp (ignored by
the sweep), checks its MD5 against the object's and renames it into
place, then records it in the sweep index and in the known-contents
map so it is never uploaded again. An error is reported and the job
stays open; the next cycle retries until it completes, and only then
is it closed.
"""
import base64
import hashlib
import json
import logging
import os
import socket
import urllib.parse
import urllib.request

from catchup import load_index, save_index
from config import (
    DIRTY_BUCKET_NAME, HASH_CHUNK_SIZE_BYTES, SERVER_BASE_URL,
    SERVER_NOTIFY_TIMEOUT_SECONDS, get_server_api_token,
)
from fs_utils import to_long_path
from known_contents import remember_upload

logger = logging.getLogger(__name__)

JOBS_PATH = "/panel/explorador/agente/descargas/"
PARTIAL_SUFFIX = ".partial"


def _post(path, fields):
    token = get_server_api_token()
    if not token:
        raise RuntimeError("sin token de API configurado")
    body = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        SERVER_BASE_URL + path, data=body, method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(
        request, timeout=SERVER_NOTIFY_TIMEOUT_SECONDS,
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def _report(job_id, **fields):
    try:
        _post("%s%d/" % (JOBS_PATH, job_id), fields)
    except Exception as error:  # noqa: BLE001 -- nunca fatal
        logger.warning(
            "Descarga a local: no se pudo avisar al servidor del "
            "trabajo %s: %s", job_id, error,
        )


def _md5_base64(path):
    digest = hashlib.md5()
    with open(to_long_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE_BYTES), b""):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


def _watched_root(watched_folders, virtual_path):
    """Watched folder whose name is the first segment of the path.
    ---
    Carpeta vigilada cuyo nombre es el primer tramo de la ruta (la
    raiz del cubo es el nombre de la carpeta elegida, igual que en
    `uploader.build_blob_name`), y la ruta relativa dentro de ella.
    """
    first, _sep, relative = virtual_path.partition("/")
    for folder in watched_folders:
        if os.path.basename(os.path.normpath(folder)) == first:
            return folder, relative
    return None, relative


def _download_file(bucket, blob_name, target):
    """Download one object to target, MD5-checked. Returns its size.
    ---
    Baja un objeto a su sitio, comprobando el MD5. Devuelve el tamano.
    """
    blob = bucket.get_blob(blob_name)
    if blob is None:
        raise RuntimeError("el objeto %s no existe en el cubo" % blob_name)
    if os.path.isfile(to_long_path(target)) and blob.md5_hash:
        if _md5_base64(target) == blob.md5_hash:
            return os.path.getsize(to_long_path(target))
    os.makedirs(to_long_path(os.path.dirname(target)), exist_ok=True)
    partial = target + PARTIAL_SUFFIX
    try:
        blob.download_to_filename(to_long_path(partial))
        if blob.md5_hash and _md5_base64(partial) != blob.md5_hash:
            raise RuntimeError(
                "el MD5 de %s no coincide con el del cubo" % blob_name
            )
        os.replace(to_long_path(partial), to_long_path(target))
    finally:
        if os.path.exists(to_long_path(partial)):
            try:
                os.remove(to_long_path(partial))
            except OSError:
                pass
    return os.path.getsize(to_long_path(target))


def _remember_local(folder, relative, target, size):
    """Record the file so the sweep never uploads it again.
    ---
    Anota el archivo para que el barrido no lo vuelva a subir: en el
    indice de la puesta al dia (si ya esta sembrado; si no, la siembra
    lo recoge tal cual) y en el mapa de contenido ya en GCS.
    """
    entries = load_index(folder)
    if entries is not None:
        stat_result = os.stat(to_long_path(target))
        entries[relative] = [stat_result.st_size, int(stat_result.st_mtime)]
        save_index(folder, entries)
    remember_upload(target, size)


def process_jobs(client, watched_folders):
    """Run every unfinished local download once.
    ---
    Ejecuta una vez cada descarga sin terminar. Devuelve una lista de
    textos para el historial (vacia si no habia nada que hacer).
    Nunca lanza: un fallo queda comunicado al servidor y el trabajo se
    reintenta en el ciclo siguiente.
    """
    try:
        payload = _post(JOBS_PATH, {"host": socket.gethostname()})
    except Exception as error:  # noqa: BLE001
        logger.warning("Descarga a local: no se pudo pedir trabajos: %s",
                       error)
        return []
    events = []
    bucket = client.bucket(DIRTY_BUCKET_NAME)
    for job in payload.get("jobs") or []:
        job_id = job["id"]
        files = job.get("files") or []
        done = 0
        error_text = ""
        for item in files:
            folder, relative = _watched_root(watched_folders, item["path"])
            if folder is None:
                error_text = (
                    "La carpeta «%s» no esta vigilada por el agente."
                    % item["path"].split("/", 1)[0]
                )
                break
            target = os.path.join(folder, *relative.split("/"))
            try:
                size = _download_file(bucket, item["blob"], target)
                _remember_local(folder, relative, target, size)
            except Exception as error:  # noqa: BLE001
                logger.exception(
                    "Descarga a local: fallo con %s: %s", item["blob"], error,
                )
                error_text = "%s: %s" % (os.path.basename(target), error)
                break
            done += 1
            _report(job_id, downloaded=done, error="")
        if error_text:
            _report(job_id, downloaded=done, error=error_text)
            events.append("Trabajo %s: %d/%d, se reintenta (%s)" % (
                job_id, done, len(files), error_text))
            continue
        _report(job_id, done="1")
        logger.info("Descarga a local: trabajo %s terminado (%d archivos).",
                    job_id, len(files))
        events.append("Trabajo %s: %d archivo(s) descargados" % (
            job_id, len(files)))
    return events
