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
import re
import socket
import unicodedata
import urllib.parse
import urllib.request

from catchup import load_index, save_index
from config import (
    DIRTY_BUCKET_NAME, HASH_CHUNK_SIZE_BYTES, SERVER_BASE_URL,
    SERVER_NOTIFY_TIMEOUT_SECONDS, get_server_api_token,
)
from fs_utils import mirror_name, to_long_path
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
# H31 (S148): carpetas de maquinas, mismo listado que
# document_explorer/machine_local_folder_service.LOCAL_CONTAINERS
# (activas y bajas de cada familia), las mas largas primero.
MACHINE_ROOT = "DOC. MAQUINAS"
_RG = "REMOLQUES Y GONDOLAS (R y G)"
MACHINE_CONTAINERS = tuple(sorted((
    "GRUAS MOVILES (A)", "GRUAS MOVILES (A)/VEHICULOS BAJA",
    "CAMIONES BRAZO (B)", "CAMIONES BRAZO (B)/VEHICULOS DE BAJA",
    "PLATAFORMAS (Z)", "PLATAFORMAS (Z)/BAJAS",
    "CABEZAS TRACTORAS (P)", "CABEZAS TRACTORAS (P)/BAJA",
    _RG + "/REMOLQUES", _RG + "/REMOLQUES/BAJAS",
    _RG + "/GONDOLAS", _RG + "/GONDOLAS/BAJAS",
    "CARRETILLAS (T)", "CARRETILLAS (T)/BAJAS",
    "VEHICULOS DE EMPRESA", "VEHICULOS DE EMPRESA/BAJA DEFINITIVA",
    "VARIOS", "VARIOS/BAJAS",
), key=len, reverse=True))
OBSOLETE_FOLDER = "OBSOLETOS"


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


def is_machine_folder(path):
    """True only for DOC. MAQUINAS/<container>/<name> (S148).
    ---
    Solo una carpeta de maquina donde el servidor la quiere: una de las
    carpetas de familia (activas o bajas) y el nombre de la maquina.
    """
    prefix = MACHINE_ROOT + "/"
    if not path or not path.startswith(prefix):
        return False
    rest = path[len(prefix):]
    for container in MACHINE_CONTAINERS:
        if rest.startswith(container + "/"):
            name = rest[len(container) + 1:]
            return bool(name) and "/" not in name and name not in (
                ".", "..")
    return False


def is_machine_previous(path):
    """True for a machine folder where it is now (S148).
    ---
    La carpeta de una maquina donde esta ahora: puede estar en una
    carpeta antigua (OBSOLETO, VENTA...), asi que basta con que este
    dentro de DOC. MAQUINAS, por debajo de una familia, y que no sea
    ninguna de las carpetas de familia. El servidor solo manda carpetas
    que llevan el codigo o la matricula de la maquina.
    """
    parts = (path or "").split("/")
    if len(parts) < 3 or parts[0] != MACHINE_ROOT:
        return False
    if any(not part or part in (".", "..") for part in parts):
        return False
    rest = "/".join(parts[1:])
    return rest not in MACHINE_CONTAINERS


def is_subject_folder(path):
    """Person or machine folder (S148).
    ---
    Carpeta de persona o de maquina.
    """
    return is_person_folder(path) or is_machine_folder(path)


def _watched_root(watched_folders, virtual_path):
    """Watched folder whose name is the first segment of the path.
    ---
    Carpeta vigilada cuyo nombre en el cubo es el principio de la ruta
    (igual que en `uploader.build_blob_name`), y la ruta relativa
    dentro de ella.
    """
    # S152: el nombre en el cubo puede tener varios tramos ("DOC.
    # GRUALDI/POLIZA RC", `fs_utils.mirror_name`); gana el mas largo.
    best = None
    for folder in watched_folders:
        name = mirror_name(folder)
        if virtual_path == name or virtual_path.startswith(name + "/"):
            if best is None or len(name) > len(best[1]):
                best = (folder, name)
    if best is None:
        return None, virtual_path.partition("/")[2]
    return best[0], virtual_path[len(best[1]) + 1:]


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


def _stem(name):
    """Folder name before its first bracket, letters and digits only.
    ---
    El nombre de la carpeta hasta su primer parentesis, solo letras y
    numeros: "DOCUMENT 2030JVK PEUGEOT 208 (TR)" y "DOCUMENT 2030JVK
    PEUGEOT 208" dan lo mismo.
    """
    return re.sub(r"[^A-Z0-9]", "", _plain(name.split("(", 1)[0]))


def find_person_folder(watched_folders, previous):
    """Find a person or machine folder by name in every known category.
    ---
    Busca la carpeta de la persona por su nombre (sin tildes ni
    mayusculas) en todas las categorias conocidas. Devuelve su ruta
    virtual si hay exactamente una; "" si no hay ninguna o hay varias
    (con dos iguales no se adivina: se avisa en el log).
    S150: las carpetas vacias no cuentan (no hay nada que mover; las
    deja un trabajo anterior que no encontro la de verdad). En maquinas,
    si no hay ninguna con el nombre exacto, vale la que tiene el mismo
    nombre hasta el primer parentesis: en local muchas llevan la empresa
    al final ("DOCUMENT 2030JVK PEUGEOT 208 (TR)") o el estado ("R-12
    B-10513-R FC (VENDIDA)") y el servidor no lo sabe.
    """
    wanted = _plain(previous.rsplit("/", 1)[-1])
    machine = previous.startswith(MACHINE_ROOT + "/")
    stem = _stem(previous.rsplit("/", 1)[-1]) if machine else ""
    found, similar = [], []
    if machine:
        root, containers = MACHINE_ROOT, MACHINE_CONTAINERS
    else:
        root, containers = PERSON_ROOT, PERSON_CONTAINERS
    for container in containers:
        virtual = "%s/%s" % (root, container)
        try:
            _folder, _rel, local = _local(watched_folders, virtual + "/x")
        except RuntimeError:
            return ""
        base = os.path.dirname(local)
        if not os.path.isdir(to_long_path(base)):
            continue
        for name in os.listdir(to_long_path(base)):
            path = to_long_path(os.path.join(base, name))
            if not os.path.isdir(path) or not os.listdir(path):
                continue
            if _plain(name) == wanted:
                found.append("%s/%s" % (virtual, name))
            elif len(stem) >= 5 and _stem(name) == stem:
                similar.append("%s/%s" % (virtual, name))
    found = found or similar
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
    este y la de antes se borra solo si queda vacia. Devuelve (texto
    para el historial o "" si no habia nada que mover, carpeta destino).
    S150: texto None si la carpeta no esta en local; y si se encontro
    con otro nombre (una maquina con la empresa al final), el destino
    conserva ese nombre: en local no se renombra nada.
    """
    person = is_person_folder(previous) and is_person_folder(target)
    machine = is_machine_previous(previous) and is_machine_folder(target)
    if not (person or machine):
        raise RuntimeError(
            "Ruta que no es una carpeta de persona ni de maquina: %s -> %s"
            % (previous, target))
    folder, old_rel, source = _local(watched_folders, previous)
    _folder2, new_rel, dest = _local(watched_folders, target)
    if os.path.isdir(to_long_path(source)) and not os.listdir(
            to_long_path(source)):
        # S150: vacia, la dejo un trabajo anterior; la buena puede tener
        # otro nombre.
        os.rmdir(to_long_path(source))
    if not os.path.isdir(to_long_path(source)):
        # S146: la carpeta que dice el servidor es la de cuando se
        # subieron sus documentos; si en local la movieron a mano (p. ej.
        # a TRABAJADORES INACTIVOS tras la baja), se busca por su nombre.
        found = find_person_folder(watched_folders, previous)
        if not found:
            return None, target
        if machine:
            target = "%s/%s" % (target.rsplit("/", 1)[0],
                                found.rsplit("/", 1)[-1])
            _folder2, new_rel, dest = _local(watched_folders, target)
        previous = found
        folder, old_rel, source = _local(watched_folders, previous)
    if os.path.normcase(os.path.abspath(source)) == os.path.normcase(
            os.path.abspath(dest)):
        return "", target
    if os.path.isdir(to_long_path(dest)) and not os.listdir(
            to_long_path(dest)):
        # S150: una carpeta vacia que dejo un trabajo anterior.
        os.rmdir(to_long_path(dest))
    if not os.path.exists(to_long_path(dest)):
        os.makedirs(to_long_path(os.path.dirname(dest)), exist_ok=True)
        os.replace(to_long_path(source), to_long_path(dest))
        _reindex_moved(folder, old_rel, new_rel)
        return "carpeta movida de %s a %s" % (previous, target), target
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
        return "contenido pasado de %s a %s" % (previous, target), target
    return ("contenido pasado a %s; se quedan en %s %d elemento(s) que "
            "ya estaban en el destino" % (target, previous, len(kept)),
            target)


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
    if target and not is_subject_folder(target):
        return 0, ("la carpeta destino no es una carpeta de persona ni de "
                   "maquina: %s" % target)
    missing = False
    if previous:
        try:
            text, moved_to = move_person_folder(
                watched_folders, previous, target)
        except Exception as error:  # noqa: BLE001
            logger.exception("Descarga a local: fallo moviendo %s: %s",
                             previous, error)
            return 0, "moviendo la carpeta: %s" % error
        if text is None:
            # S150: sin carpeta en local no se crea una vacia (antes
            # quedaban carpetas vacias con el nombre del servidor).
            missing = True
            events.append("Trabajo %s: no encuentro en local %s" % (
                job_id, previous))
        elif text:
            events.append("Trabajo %s: %s" % (job_id, text))
        if moved_to != target:
            # Los archivos del panel van a la carpeta con su nombre real.
            files = [dict(item, path=moved_to + item["path"][len(target):])
                     for item in files]
            target = moved_to
    if target and not (missing and not files):
        # S148: en el alta de una maquina (o de una persona sin
        # documentos) la carpeta se crea aunque no haya nada que bajar.
        try:
            _folder, _rel, local_target = _local(watched_folders, target)
            os.makedirs(to_long_path(local_target), exist_ok=True)
        except Exception as error:  # noqa: BLE001
            return 0, "creando la carpeta: %s" % error
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
    error_text = _move_obsolete(watched_folders, target,
                                job.get("obsolete") or [], events, job_id)
    return done, error_text


def _move_obsolete(watched_folders, target, moves, events, job_id):
    """Move superseded documents into OBSOLETOS (S148).
    ---
    Pasa los documentos sustituidos a la subcarpeta OBSOLETOS de la
    carpeta (Miguel Angel: "nuevo DNI lo subes y te olvidas"). Solo
    dentro de la carpeta de la persona o maquina; si el archivo ya no
    esta (lo movieron a mano) se salta; si en OBSOLETOS ya hay uno con
    ese nombre, se deja donde esta. Devuelve un texto de error o "".
    """
    for item in moves:
        path, dest = item.get("path", ""), item.get("dest", "")
        inside = target and path.startswith(target + "/") and (
            dest.startswith("%s/%s/" % (target, OBSOLETE_FOLDER)))
        if not inside:
            return "obsoleto fuera de la carpeta: %s" % path
        try:
            folder, old_rel, source = _local(watched_folders, path)
            _folder2, new_rel, destination = _local(watched_folders, dest)
            if not os.path.isfile(to_long_path(source)):
                continue
            if os.path.exists(to_long_path(destination)):
                logger.warning("Descarga a local: %s ya esta en OBSOLETOS; "
                               "no se mueve", dest)
                continue
            os.makedirs(to_long_path(os.path.dirname(destination)),
                        exist_ok=True)
            os.replace(to_long_path(source), to_long_path(destination))
            _reindex_file(folder, old_rel, new_rel)
        except Exception as error:  # noqa: BLE001
            logger.exception("Descarga a local: fallo pasando %s a "
                             "obsoletos: %s", path, error)
            return "pasando a obsoletos %s: %s" % (
                path.rsplit("/", 1)[-1], error)
        events.append("Trabajo %s: %s pasa a OBSOLETOS" % (
            job_id, path.rsplit("/", 1)[-1]))
    return ""


def _reindex_file(folder, old_relative, new_relative):
    """Move one file entry of the sweep index (S148).
    ---
    Pasa la entrada de un archivo movido en el indice de la puesta al
    dia, para que el barrido no lo tome por nuevo.
    """
    entries = load_index(folder)
    if entries is None or old_relative not in entries:
        return
    entries[new_relative] = entries.pop(old_relative)
    save_index(folder, entries)


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
