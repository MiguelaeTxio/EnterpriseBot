# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/db_backup_download.py
"""Bring the database copies to a dedicated OneDrive folder (S146).
---
Copias de seguridad de la base de datos a una carpeta de OneDrive (H24,
S146).

Miguel Angel: "copiar todo lo que tenemos en base de datos [...] la
propia nube de Microsoft 365, en una carpeta dedicada que este fuera de
las que esta vigilando el H28."

Como funciona:

- El servidor vuelca la BD cada dia a las 3:00 a su propio cubo. El
  agente pregunta cada 10 minutos (`/panel/explorador/agente/copias-bd/`)
  que copias hay pendientes y cuales se quedan.
- Carpeta: `COPIAS DE SEGURIDAD BD` en la raiz del OneDrive de la
  empresa (`%OneDriveCommercial%`; si no existe, `%OneDrive%`). Si hace
  falta otra, su ruta va en `db_backup_folder.txt` dentro de
  agent_data. Nunca puede estar dentro de una carpeta vigilada ni
  contener una: si lo esta, no se baja nada y se avisa.
- Cada copia se baja del servidor a un `.partial`, se calcula su
  SHA-256 y, solo si coincide con el del volcado, se renombra y se deja
  al lado `<archivo>.sha256` (formato de sha256sum). El servidor la da
  por buena solo con ese SHA-256.
- Retencion (diaria y escalonada, la decide el servidor): se quitan las
  copias que ya no estan en la lista `keep`. Nunca con la lista vacia y
  nunca la copia mas reciente.
---
Downloads each pending copy from the server to a `.partial`, checks the
SHA-256, renames it and writes `<file>.sha256` next to it; then removes
the copies the server no longer keeps. The folder is never inside a
watched folder.
"""
import hashlib
import json
import logging
import os
import re
import socket
import time
import urllib.parse
import urllib.request

from config import (
    HASH_CHUNK_SIZE_BYTES, SERVER_BASE_URL, SERVER_NOTIFY_TIMEOUT_SECONDS,
    get_agent_data_dir, get_server_api_token,
)

logger = logging.getLogger(__name__)

BACKUPS_PATH = "/panel/explorador/agente/copias-bd/"
CHECK_EVERY_SECONDS = 10 * 60
DOWNLOAD_TIMEOUT_SECONDS = 300
FOLDER_OVERRIDE_FILE_NAME = "db_backup_folder.txt"
DEFAULT_FOLDER_NAME = "COPIAS DE SEGURIDAD BD"
PARTIAL_SUFFIX = ".partial"
FILE_NAME_RE = re.compile(r"^EnterpriseBot_BD_\d{8}_\d{4}\.sql\.gz$")

_last_check = 0.0
_removed_to_report = []


def _request(path, fields=None, timeout=SERVER_NOTIFY_TIMEOUT_SECONDS):
    token = get_server_api_token()
    if not token:
        raise RuntimeError("sin token de API configurado")
    data = None
    if fields is not None:
        data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        SERVER_BASE_URL + path, data=data,
        method="POST" if fields is not None else "GET",
        headers={"Authorization": "Bearer " + token},
    )
    return urllib.request.urlopen(request, timeout=timeout)


def _post_json(path, fields):
    with _request(path, fields) as response:
        return json.loads(response.read().decode("utf-8"))


def _inside(child, parent):
    child = os.path.normcase(os.path.abspath(child))
    parent = os.path.normcase(os.path.abspath(parent))
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:  # unidades distintas
        return False


def resolve_folder(watched_folders, folder_name):
    """Backup folder, or raise RuntimeError if it is not safe.
    ---
    Carpeta de las copias: la de `db_backup_folder.txt` si existe; si
    no, `<OneDrive de la empresa>/<folder_name>`. Error si queda dentro
    de una carpeta vigilada o contiene una.
    """
    override = os.path.join(get_agent_data_dir(), FOLDER_OVERRIDE_FILE_NAME)
    folder = ""
    if os.path.isfile(override):
        with open(override, "r", encoding="utf-8") as handle:
            folder = handle.read().strip()
    if not folder:
        root = (os.environ.get("OneDriveCommercial")
                or os.environ.get("OneDrive") or "")
        if not root or not os.path.isdir(root):
            raise RuntimeError(
                "no se encuentra la carpeta de OneDrive (OneDriveCommercial"
                " / OneDrive); ponga la ruta en %s" % override)
        folder = os.path.join(root, folder_name or DEFAULT_FOLDER_NAME)
    for watched in watched_folders:
        if _inside(folder, watched) or _inside(watched, folder):
            raise RuntimeError(
                "la carpeta de copias %s esta dentro de la carpeta "
                "vigilada %s (o la contiene)" % (folder, watched))
    os.makedirs(folder, exist_ok=True)
    return folder


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(copy, folder):
    """Download one copy, SHA-256 checked. Returns its local path.
    ---
    Baja una copia a un `.partial`, comprueba el SHA-256 y la deja en su
    sitio con su `.sha256` al lado. Si ya estaba con el mismo SHA-256,
    no la vuelve a bajar.
    """
    name = copy["file_name"]
    if not FILE_NAME_RE.match(name):
        raise RuntimeError("nombre de copia no valido: %s" % name)
    target = os.path.join(folder, name)
    if not (os.path.isfile(target) and _sha256(target) == copy["sha256"]):
        partial = target + PARTIAL_SUFFIX
        try:
            with _request("%s%d/archivo/" % (BACKUPS_PATH, copy["id"]),
                          timeout=DOWNLOAD_TIMEOUT_SECONDS) as response, \
                    open(partial, "wb") as out:
                for chunk in iter(
                        lambda: response.read(HASH_CHUNK_SIZE_BYTES), b""):
                    out.write(chunk)
            got = _sha256(partial)
            if got != copy["sha256"]:
                raise RuntimeError(
                    "SHA-256 distinto: bajado %s, esperado %s"
                    % (got, copy["sha256"]))
            os.replace(partial, target)
        finally:
            if os.path.exists(partial):
                try:
                    os.remove(partial)
                except OSError:
                    pass
    with open(target + ".sha256", "w", encoding="ascii",
              newline="\n") as handle:
        handle.write("%s  %s\n" % (copy["sha256"], name))
    return target


def _apply_retention(folder, keep):
    """Remove the copies the server no longer keeps.
    ---
    Quita de la carpeta las copias que no estan en `keep` (y su
    `.sha256`). Nunca con `keep` vacio y nunca la mas reciente.
    Devuelve los nombres quitados.
    """
    if not keep:
        return []
    keep = set(keep)
    local = sorted(n for n in os.listdir(folder) if FILE_NAME_RE.match(n))
    removed = []
    for name in local[:-1]:
        if name in keep:
            continue
        path = os.path.join(folder, name)
        os.remove(path)
        if os.path.isfile(path + ".sha256"):
            os.remove(path + ".sha256")
        removed.append(name)
        logger.info("Copias BD: quitada por la retencion %s", name)
    return removed


def process_backups(watched_folders):
    """Every 10 minutes: download pending copies and apply retention.
    ---
    Cada 10 minutos: baja las copias pendientes y aplica la retencion.
    Devuelve textos para el historial. Nunca lanza: los errores se
    registran, se comunican al servidor y se reintenta en el ciclo
    siguiente.
    """
    global _last_check, _removed_to_report
    if time.monotonic() - _last_check < CHECK_EVERY_SECONDS and _last_check:
        return []
    _last_check = time.monotonic()
    try:
        payload = _post_json(BACKUPS_PATH, {
            "host": socket.gethostname(),
            "removed": ",".join(_removed_to_report),
        })
    except Exception as error:  # noqa: BLE001
        logger.warning("Copias BD: no se pudo preguntar al servidor: %s",
                       error)
        return []
    _removed_to_report = []
    events = []
    try:
        folder = resolve_folder(watched_folders, payload.get("folder_name"))
    except Exception as error:  # noqa: BLE001
        logger.error("Copias BD: %s", error)
        return ["Copias BD: %s" % error]
    for copy in payload.get("pending") or []:
        try:
            path = _download(copy, folder)
        except Exception as error:  # noqa: BLE001
            logger.exception("Copias BD: fallo con %s", copy["file_name"])
            try:
                _post_json("%s%d/" % (BACKUPS_PATH, copy["id"]),
                           {"error": "%s" % error})
            except Exception:  # noqa: BLE001
                pass
            events.append("Copia %s: error, se reintenta (%s)" % (
                copy["file_name"], error))
            continue
        try:
            answer = _post_json("%s%d/" % (BACKUPS_PATH, copy["id"]), {
                "sha256": copy["sha256"], "local_path": path,
                "host": socket.gethostname(),
            })
        except Exception as error:  # noqa: BLE001
            logger.warning("Copias BD: no se pudo avisar de %s: %s",
                           copy["file_name"], error)
            continue
        if answer.get("ok"):
            logger.info("Copias BD: %s en %s", copy["file_name"], path)
            events.append("Copia de la BD en OneDrive: %s" % path)
    try:
        _removed_to_report = _apply_retention(folder, payload.get("keep"))
    except Exception as error:  # noqa: BLE001
        logger.exception("Copias BD: fallo aplicando la retencion")
        events.append("Copias BD: fallo en la retencion (%s)" % error)
    return events
