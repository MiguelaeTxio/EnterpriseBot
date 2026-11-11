# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/invoice_folder.py
"""Local FACTURACION folder of the inbox, kept in step with the server (S151).
---
Carpeta local FACTURACION de la bandeja de entrada, al dia con el
servidor (H28, S151, sesion invasora).

Miguel Angel, al ver que en su OneDrive no habia nada: la carpeta
FACTURACION de la bandeja tiene que estar tambien en local, en
`ACCESO_BUZON_DOCUMENTACION`, con sus subcarpetas `FACTURAS NUEVAS` y
`FACTURAS PROCESADAS`.

Como funciona, en cada ciclo del barrido (mismo hilo, antes de barrer):

- Crea las carpetas si no existen:
  `<OneDrive de la empresa>/ACCESO_BUZON_DOCUMENTACION/FACTURACIÓN/
  FACTURAS NUEVAS` y `.../FACTURAS PROCESADAS`. Si hace falta otra
  ubicacion, su ruta (la de FACTURACIÓN) va en `invoice_folder.txt`
  dentro de agent_data.
- Manda al servidor la huella SHA-256 de cada archivo de las dos
  subcarpetas (`/panel/documentacion/bandeja/facturacion/agente/
  sincronizar/`) y el servidor contesta:
  - `upload`: facturas nuevas que no tiene -> se suben. El servidor
    las guarda en el cubo (FACTURACION/FACTURAS NUEVAS) y las procesa.
  - `move_to_processed`: ya procesadas -> se pasan a FACTURAS
    PROCESADAS.
  - `download`: entraron por la bandeja del panel o el explorador ->
    se bajan (a un `.partial`, SHA-256 comprobado) a la subcarpeta que
    les toca.
- La carpeta FACTURACIÓN nunca la sube el barrido de cuarentena aunque
  cuelgue de una carpeta vigilada (`uploader.iter_relative_file_paths`
  la salta): las facturas solo van por aqui.
- Nunca borra nada. Un nombre ya ocupado por otro archivo se resuelve
  con " (2)", " (3)"...
---
Each cycle: create the folders, send the SHA-256 of every local file,
then upload new invoices the server does not have, move processed ones
to FACTURAS PROCESADAS and download the ones that came in through the
panel. The catch-up sweep never uploads this folder to quarantine.
Nothing is ever deleted.
"""
import hashlib
import json
import logging
import os
import socket
import urllib.parse
import urllib.request

from config import (
    HASH_CHUNK_SIZE_BYTES, SERVER_BASE_URL, SERVER_NOTIFY_TIMEOUT_SECONDS,
    get_agent_data_dir, get_server_api_token,
)
from fs_utils import is_transient_file, to_long_path

logger = logging.getLogger(__name__)

API_PATH = "/panel/documentacion/bandeja/facturacion/agente/"
BUZON_FOLDER_NAME = "ACCESO_BUZON_DOCUMENTACION"
ROOT_FOLDER_NAME = "FACTURACIÓN"
NEW_FOLDER_NAME = "FACTURAS NUEVAS"
PROCESSED_FOLDER_NAME = "FACTURAS PROCESADAS"
FOLDER_OVERRIDE_FILE_NAME = "invoice_folder.txt"
PARTIAL_SUFFIX = ".partial"
UPLOAD_TIMEOUT_SECONDS = 120
ALLOWED_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic")

# Huella por (ruta, tamano, fecha): no se vuelve a leer un archivo que
# no ha cambiado.
_sha_cache = {}


def resolve_root():
    """Absolute path of the local FACTURACIÓN folder ("" if unknown).
    ---
    Ruta de la carpeta local FACTURACIÓN: la de `invoice_folder.txt` si
    existe; si no, `<OneDrive de la empresa>/ACCESO_BUZON_DOCUMENTACION/
    FACTURACIÓN`. Cadena vacia si no se encuentra OneDrive.
    """
    override = os.path.join(get_agent_data_dir(), FOLDER_OVERRIDE_FILE_NAME)
    if os.path.isfile(override):
        with open(override, "r", encoding="utf-8") as handle:
            folder = handle.read().strip()
        if folder:
            return os.path.normpath(folder)
    root = (os.environ.get("OneDriveCommercial")
            or os.environ.get("OneDrive") or "")
    if not root or not os.path.isdir(root):
        return ""
    return os.path.normpath(
        os.path.join(root, BUZON_FOLDER_NAME, ROOT_FOLDER_NAME),
    )


def is_invoice_folder(path):
    """Whether `path` is the local FACTURACIÓN folder (or inside it).
    ---
    Si `path` es la carpeta local FACTURACIÓN o esta dentro: el barrido
    de cuarentena la salta.
    """
    root = resolve_root()
    if not root:
        return False
    path = os.path.normcase(os.path.normpath(path))
    root = os.path.normcase(root)
    return path == root or path.startswith(root + os.sep)


def _headers(extra=None):
    token = get_server_api_token()
    if not token:
        raise RuntimeError("sin token de API configurado")
    headers = {"Authorization": "Bearer " + token}
    headers.update(extra or {})
    return headers


def _call(path, data=None, headers=None, method=None,
          timeout=SERVER_NOTIFY_TIMEOUT_SECONDS):
    request = urllib.request.Request(
        SERVER_BASE_URL + API_PATH + path, data=data,
        method=method or ("POST" if data is not None else "GET"),
        headers=_headers(headers),
    )
    return urllib.request.urlopen(request, timeout=timeout)


def _post_json(path, payload):
    with _call(path, json.dumps(payload).encode("utf-8"),
               {"Content-Type": "application/json"}) as response:
        return json.loads(response.read().decode("utf-8"))


def _sha256(path):
    stat = os.stat(to_long_path(path))
    key = (path, stat.st_size, stat.st_mtime)
    cached = _sha_cache.get(key)
    if cached:
        return cached
    digest = hashlib.sha256()
    with open(to_long_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE_BYTES), b""):
            digest.update(chunk)
    _sha_cache[key] = digest.hexdigest()
    return _sha_cache[key]


def _local_files(folder):
    """Invoice files directly inside `folder` (no subfolders).
    ---
    Archivos de factura de la subcarpeta (sin entrar en subcarpetas,
    sin temporales ni `.partial`).
    """
    files = []
    for name in sorted(os.listdir(to_long_path(folder))):
        path = os.path.join(folder, name)
        if not os.path.isfile(to_long_path(path)) or is_transient_file(name):
            continue
        if not name.lower().endswith(ALLOWED_EXTENSIONS):
            continue
        files.append(path)
    return files


def _free_path(folder, name):
    """`folder/name`, or `name (2)`, `name (3)`... if already taken.
    ---
    Ruta libre para `name` en `folder`: nunca pisa un archivo.
    """
    stem, ext = os.path.splitext(name)
    candidate = os.path.join(folder, name)
    number = 2
    while os.path.exists(to_long_path(candidate)):
        candidate = os.path.join(folder, "%s (%d)%s" % (stem, number, ext))
        number += 1
    return candidate


def _upload(path):
    with open(to_long_path(path), "rb") as handle:
        data = handle.read()
    name = os.path.basename(path)
    with _call("subir/", data, {
        "Content-Type": "application/octet-stream",
        "X-File-Name": urllib.parse.quote(name),
    }, timeout=UPLOAD_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(item, folder):
    """Download one invoice to `folder`, SHA-256 checked.
    ---
    Baja una factura a un `.partial`, comprueba la huella y la deja con
    su nombre (libre) en la subcarpeta.
    """
    name = os.path.basename(item["name"].replace("\\", "/")) or "factura"
    target = _free_path(folder, name)
    partial = target + PARTIAL_SUFFIX
    try:
        with _call("%d/archivo/" % item["id"],
                   timeout=UPLOAD_TIMEOUT_SECONDS) as response, \
                open(to_long_path(partial), "wb") as out:
            for chunk in iter(
                    lambda: response.read(HASH_CHUNK_SIZE_BYTES), b""):
                out.write(chunk)
        got = _sha256(partial)
        if got != item["sha256"]:
            raise RuntimeError("huella distinta: bajada %s, esperada %s"
                               % (got, item["sha256"]))
        os.replace(to_long_path(partial), to_long_path(target))
    finally:
        if os.path.exists(to_long_path(partial)):
            try:
                os.remove(to_long_path(partial))
            except OSError:
                pass
    with _call("%d/local/" % item["id"], b"") as response:
        response.read()
    return target


def process_invoices():
    """One sync cycle of the local FACTURACIÓN folder.
    ---
    Un ciclo de la carpeta local FACTURACIÓN (ver docstring del
    modulo). Devuelve textos para el historial. Nunca lanza: los
    errores se registran y se reintenta en el ciclo siguiente.
    """
    root = resolve_root()
    if not root:
        logger.warning("Facturas: no se encuentra la carpeta de OneDrive "
                       "(OneDriveCommercial / OneDrive).")
        return []
    new_folder = os.path.join(root, NEW_FOLDER_NAME)
    processed_folder = os.path.join(root, PROCESSED_FOLDER_NAME)
    events = []
    try:
        for folder in (new_folder, processed_folder):
            os.makedirs(to_long_path(folder), exist_ok=True)
        local = {}
        for folder, key in ((new_folder, "nuevas"),
                            (processed_folder, "procesadas")):
            for path in _local_files(folder):
                local.setdefault(_sha256(path), []).append((path, key))
        plan = _post_json("sincronizar/", {
            "host": socket.gethostname(),
            "local": [
                {"sha256": sha, "folder": key}
                for sha, places in local.items() for _path, key in places
            ],
        })
    except Exception as error:  # noqa: BLE001
        logger.warning("Facturas: no se pudo sincronizar: %s", error)
        return []

    for sha in plan.get("upload") or []:
        for path, key in local.get(sha, []):
            if key != "nuevas":
                continue
            try:
                answer = _upload(path)
            except Exception as error:  # noqa: BLE001
                logger.warning("Facturas: no se pudo subir %s: %s",
                               path, error)
                continue
            if answer.get("ok"):
                logger.info("Facturas: subida %s", path)
                events.append("Factura subida para procesar: %s"
                              % os.path.basename(path))
            else:
                logger.warning("Facturas: %s", answer.get("error"))
            break

    for sha in plan.get("move_to_processed") or []:
        for path, key in local.get(sha, []):
            if key != "nuevas":
                continue
            target = _free_path(processed_folder, os.path.basename(path))
            try:
                os.replace(to_long_path(path), to_long_path(target))
            except OSError as error:
                logger.warning("Facturas: no se pudo mover %s: %s",
                               path, error)
                continue
            logger.info("Facturas: procesada, a %s", target)
            events.append("Factura procesada: %s" % os.path.basename(target))

    for item in plan.get("download") or []:
        folder = (processed_folder if item.get("folder") == "procesadas"
                  else new_folder)
        try:
            target = _download(item, folder)
        except Exception as error:  # noqa: BLE001
            logger.warning("Facturas: no se pudo bajar %s: %s",
                           item.get("name"), error)
            continue
        logger.info("Facturas: bajada %s", target)
        events.append("Factura bajada a local: %s"
                      % os.path.basename(target))
    return events
