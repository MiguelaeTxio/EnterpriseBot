# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/local_download.py
"""Keep a worker's folder in the local tree (onboarding, leave) (S144).
---
La carpeta de un trabajador en el arbol local (alta, baja,
reactivacion) (H24, S144).

Miguel Angel: "se da de alta, se clasifica en el cubo y descargamos a
su carpeta de personal [...] no quiero estar vigilando todas las
carpetas del cubo y bajarlas. No, quiero solamente el que se de de alta
en ese momento [...] si hay un error en la descarga, se termine esa
descarga y cuando este finalizada, termina el pipeline"; "poner
inactivo a una persona en el panel y que [...] en el local tambien la
ponga en inactivos".

Como funciona (corregido tras la prueba con Cruces Gomez, S144):

- El servidor apunta un trabajo por persona con la carpeta local donde
  tiene que estar (`folder`, con vuestra organizacion: OPERARIOS,
  TALLER, GUARDA...), la de antes si cambia de sitio
  (`previous_folder`) y los archivos subidos desde el panel que hay que
  descargar (`files`). El agente no mira nada mas del cubo.
- En cada ciclo, ANTES de barrer, el agente pide los trabajos sin
  terminar; descarga y barrido nunca coinciden.
- Si la persona cambia de sitio, se mueve la carpeta ENTERA, tal cual,
  con todo lo que tenga ("tal cual"). Si ya existe la de destino, se
  pasa dentro lo que no este y la de antes se borra solo si queda
  vacia. Nunca se mueve un archivo suelto de ningun otro sitio: la
  primera version movia archivos de cualquier carpeta del arbol
  (ENTREGA EPIS, ENTREGA INFORMACION...) y partio la carpeta de Cruces
  Gomez en dos.
- Solo carpetas de persona: `DOC. PERSONAL/PERSONAL/<categoria>/<nombre>`
  con una categoria de PERSON_CONTAINERS. Cualquier otra ruta se
  rechaza y se avisa.
- Cada archivo se baja a un `.partial` (el barrido lo ignora), se
  comprueba el MD5 con el del objeto y se renombra a su sitio; uno que
  ya esta con el mismo MD5 no se vuelve a bajar. Se anota en el indice
  de la puesta al dia y en el mapa de contenido ya en GCS para que no
  se vuelva a subir.
- Un error se comunica y el trabajo sigue abierto: el ciclo siguiente
  lo reintenta hasta completarlo. Solo entonces se cierra.
---
The server sends, per person, the local folder where it must be, the
previous one when it moves, and the panel uploads to download. The
whole folder is moved as is; nothing outside a person folder is ever
touched. Files are downloaded to a `.partial`, MD5-checked and renamed;
errors are reported and retried next cycle.
"""
import base64
import hashlib
import json
import logging
import os
import socket
import unicodedata
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
PERSON_ROOT = "DOC. PERSONAL/PERSONAL"
# Carpetas de trabajadores (mismo listado que
# document_explorer/local_download_service.KNOWN_CONTAINERS).
PERSON_CONTAINERS = (
    "OPERARIOS/TRABAJADORES INACTIVOS",
    "OPERARIOS",
    "TALLER/BAJAS",
    "TALLER",
    "ADMINISTRACION/BAJAS",
    "ADMINISTRACION",
    "GUARDA/OBSOLETOS",
    "GUARDA",
    "PERSONAL ASISTENCIA GRANADA/TRABAJADORES TRANSGRUAL",
    "PERSONAL ASISTENCIA GRANADA/EX TRABAJADORES",
    "BAJAS/OPERARIOS BAJAS",
    "BAJAS/BAJA PERSONAL",
)


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


def is_person_folder(path):
    """True only for DOC. PERSONAL/PERSONAL/<container>/<name>.
    ---
    Solo una carpeta de persona: una categoria conocida y el nombre de
    la persona, nada por encima ni por debajo.
    """
    prefix = PERSON_ROOT + "/"
    if not path or not path.startswith(prefix):
        return False
    rest = path[len(prefix):]
    for container in PERSON_CONTAINERS:
        if rest.startswith(container + "/"):
            name = rest[len(container) + 1:]
            return bool(name) and "/" not in name and name not in (
                ".", "..")
    return False


def _watched_root(watched_folders, virtual_path):
    """Watched folder whose name is the first segment of the path.
    ---
    Carpeta vigilada cuyo nombre es el primer tramo de la ruta (la raiz
    del cubo es el nombre de la carpeta elegida, igual que en
    `uploader.build_blob_name`), y la ruta relativa dentro de ella.
    """
    first, _sep, relative = virtual_path.partition("/")
    for folder in watched_folders:
        if os.path.basename(os.path.normpath(folder)) == first:
            return folder, relative
    return None, relative


def _local(watched_folders, path):
    folder, relative = _watched_root(watched_folders, path)
    if folder is None:
        raise RuntimeError(
            "La carpeta «%s» no esta vigilada por el agente."
            % path.split("/", 1)[0])
    return folder, relative, os.path.join(folder, *relative.split("/"))


def _reindex_moved(folder, old_relative, new_relative):
    """Move the sweep index entries of a moved folder to its new path.
    ---
    Pasa al nuevo sitio las entradas del indice de la puesta al dia de
    una carpeta movida, para que el barrido no la tome por nueva.
    """
    entries = load_index(folder)
    if entries is None:
        return
    old_prefix = old_relative.rstrip("/") + "/"
    new_prefix = new_relative.rstrip("/") + "/"
    changed = False
    for key in list(entries):
        if key.startswith(old_prefix):
            entries[new_prefix + key[len(old_prefix):]] = entries.pop(key)
            changed = True
    if changed:
        save_index(folder, entries)


def _plain(text):
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(
        c for c in text if not unicodedata.combining(c)).upper().strip()


def find_person_folder(watched_folders, previous):
    """Find a person folder by name in every known category.
    ---
    Busca la carpeta de la persona por su nombre (sin tildes ni
    mayusculas) en todas las categorias conocidas. Devuelve su ruta
    virtual si hay exactamente una; "" si no hay ninguna o hay varias
    (con dos iguales no se adivina: se avisa en el log).
    """
    wanted = _plain(previous.rsplit("/", 1)[-1])
    found = []
    for container in PERSON_CONTAINERS:
        virtual = "%s/%s" % (PERSON_ROOT, container)
        try:
            _folder, _rel, local = _local(watched_folders, virtual + "/x")
        except RuntimeError:
            return ""
        base = os.path.dirname(local)
        if not os.path.isdir(to_long_path(base)):
            continue
        for name in os.listdir(to_long_path(base)):
            if _plain(name) == wanted and os.path.isdir(
                    to_long_path(os.path.join(base, name))):
                found.append("%s/%s" % (virtual, name))
    if len(found) == 1:
        logger.info("Descarga a local: %s no esta; encontrada en %s",
                    previous, found[0])
        return found[0]
    if found:
        logger.warning("Descarga a local: %s no esta y hay %d carpetas "
                       "con su nombre: %s", previous, len(found), found)
    return ""


def move_person_folder(watched_folders, previous, target):
    """Move the whole person folder, as is.
    ---
    Mueve la carpeta de la persona entera, tal cual. Si el destino no
    existe, se renombra la carpeta; si existe, se pasa dentro lo que no
    este y la de antes se borra solo si queda vacia. Devuelve un texto
    para el historial, o "" si no habia nada que mover.
    """
    if not (is_person_folder(previous) and is_person_folder(target)):
        raise RuntimeError(
            "Ruta que no es una carpeta de persona: %s -> %s"
            % (previous, target))
    folder, old_rel, source = _local(watched_folders, previous)
    _folder2, new_rel, dest = _local(watched_folders, target)
    if not os.path.isdir(to_long_path(source)):
        # S146: la carpeta que dice el servidor es la de cuando se
        # subieron sus documentos; si en local la movieron a mano (p. ej.
        # a TRABAJADORES INACTIVOS tras la baja), se busca por su nombre.
        found = find_person_folder(watched_folders, previous)
        if not found:
            return ""
        previous = found
        folder, old_rel, source = _local(watched_folders, previous)
    if os.path.normcase(os.path.abspath(source)) == os.path.normcase(
            os.path.abspath(dest)):
        return ""
    if not os.path.exists(to_long_path(dest)):
        os.makedirs(to_long_path(os.path.dirname(dest)), exist_ok=True)
        os.replace(to_long_path(source), to_long_path(dest))
        _reindex_moved(folder, old_rel, new_rel)
        return "carpeta movida de %s a %s" % (previous, target)
    kept = []
    for name in os.listdir(to_long_path(source)):
        src = os.path.join(source, name)
        dst = os.path.join(dest, name)
        if os.path.exists(to_long_path(dst)):
            kept.append(name)
            continue
        os.replace(to_long_path(src), to_long_path(dst))
        _reindex_moved(folder, old_rel + "/" + name, new_rel + "/" + name)
    if not kept:
        os.rmdir(to_long_path(source))
        return "contenido pasado de %s a %s" % (previous, target)
    return ("contenido pasado a %s; se quedan en %s %d elemento(s) que "
            "ya estaban en el destino" % (target, previous, len(kept)))


def _download_file(bucket, blob_name, target):
    """Download one object to target, MD5-checked. Returns its size.
    ---
    Baja un objeto a su sitio comprobando el MD5; si ya esta con el
    mismo contenido, no hace nada. Devuelve el tamano.
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
    indice de la puesta al dia (si ya esta sembrado) y en el mapa de
    contenido ya en GCS.
    """
    entries = load_index(folder)
    if entries is not None:
        stat_result = os.stat(to_long_path(target))
        entries[relative] = [stat_result.st_size, int(stat_result.st_mtime)]
        save_index(folder, entries)
    remember_upload(target, size)


def _run_job(bucket, job, watched_folders, events):
    """One job: move the folder if needed, then download what is missing.
    ---
    Un trabajo: mueve la carpeta si toca y descarga lo que falte.
    Devuelve (descargados, texto de error o "").
    """
    job_id = job["id"]
    target = job.get("folder") or ""
    previous = job.get("previous_folder") or ""
    files = job.get("files") or []
    if target and not is_person_folder(target):
        return 0, "la carpeta destino no es una carpeta de persona: %s" % (
            target)
    if previous:
        try:
            text = move_person_folder(watched_folders, previous, target)
        except Exception as error:  # noqa: BLE001
            logger.exception("Descarga a local: fallo moviendo %s: %s",
                             previous, error)
            return 0, "moviendo la carpeta: %s" % error
        if text:
            events.append("Trabajo %s: %s" % (job_id, text))
    done = 0
    for item in files:
        path = item["path"]
        if target and not path.startswith(target + "/"):
            return done, "archivo fuera de la carpeta de la persona: %s" % (
                path)
        try:
            folder, relative, local_path = _local(watched_folders, path)
            size = _download_file(bucket, item["blob"], local_path)
            _remember_local(folder, relative, local_path, size)
        except Exception as error:  # noqa: BLE001
            logger.exception(
                "Descarga a local: fallo con %s: %s", item["blob"], error,
            )
            return done, "%s: %s" % (path.rsplit("/", 1)[-1], error)
        done += 1
        _report(job_id, downloaded=done, error="")
    return done, ""


def process_jobs(client, watched_folders):
    """Run every unfinished local job once.
    ---
    Ejecuta una vez cada trabajo sin terminar. Devuelve textos para el
    historial. Nunca lanza: un fallo queda comunicado al servidor y el
    trabajo se reintenta en el ciclo siguiente.
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
        total = len(job.get("files") or [])
        done, error_text = _run_job(bucket, job, watched_folders, events)
        if error_text:
            _report(job_id, downloaded=done, error=error_text)
            events.append("Trabajo %s: %d/%d, se reintenta (%s)" % (
                job_id, done, total, error_text))
            continue
        _report(job_id, done="1")
        logger.info("Descarga a local: trabajo %s terminado en %s.",
                    job_id, job.get("folder") or "")
        events.append("Trabajo %s terminado: %s (%d archivo(s))" % (
            job_id, job.get("folder") or "", total))
    return events
