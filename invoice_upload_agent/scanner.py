# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/invoice_upload_agent/scanner.py
"""Scan the watched folder and upload new invoices to the bucket.
---
Revisa la carpeta vigilada y sube al cubo las facturas nuevas.

- Recorre la carpeta (y sus subcarpetas) buscando PDF e imagenes.
- Cada archivo se identifica por su huella SHA-256. El objeto del cubo
  se llama `<12 primeros de la huella>_<nombre>`: el mismo archivo
  nunca se sube dos veces, y dos archivos distintos con el mismo
  nombre nunca se pisan. El servidor le quita el prefijo al indexarlo
  (una copia con otro nombre sí se sube; el servidor la marca como
  factura repetida por proveedor y número, sin tocar el almacén).
- Antes de subir, comprueba si el objeto ya existe en el cubo.
- Lo ya visto se recuerda en `uploaded.json` (ruta, tamano, fecha y
  huella): un archivo que no cambia no se vuelve a leer.
- Nunca borra ni mueve nada de la carpeta local.
"""
import hashlib
import json
import logging
import mimetypes
import os

from config import (
    ALLOWED_EXTENSIONS, BUCKET_NAME, HASH_CHUNK_SIZE_BYTES,
    STATE_FILE_NAME, TRANSIENT_PREFIXES, TRANSIENT_SUFFIXES,
    UPLOAD_PREFIX, get_data_dir,
)

logger = logging.getLogger(__name__)

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/heic", ".heic")


def _state_path():
    return os.path.join(get_data_dir(), STATE_FILE_NAME)


def load_state():
    """Previously seen files: {path: {size, mtime, sha256}}.
    ---
    Archivos ya vistos: {ruta: {tamano, fecha, huella}}.
    """
    try:
        with open(_state_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    """Write the state atomically (temp file + replace).
    ---
    Guarda el estado de forma atomica (temporal + reemplazo).
    """
    temp_path = _state_path() + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=1)
    os.replace(temp_path, _state_path())


def _is_candidate(name):
    lower = name.lower()
    if lower.startswith(TRANSIENT_PREFIXES):
        return False
    if lower.endswith(TRANSIENT_SUFFIXES):
        return False
    return lower.endswith(ALLOWED_EXTENSIONS)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def blob_name_for(sha256, file_name):
    """Object name in the bucket for one local file.
    ---
    Nombre del objeto en el cubo para un archivo local.
    """
    return "%s/%s_%s" % (UPLOAD_PREFIX, sha256[:12], file_name)


def scan_and_upload(client, folder, log_event):
    """Upload every invoice of `folder` not yet in the bucket.
    ---
    Sube al cubo cada factura de `folder` que todavia no este. Escribe
    cada paso en el log (`log_event` para lo que se ve en el historial)
    y devuelve cuantas ha subido. Un fallo con un archivo no para el
    resto: se reintenta en la siguiente revision.
    """
    state = load_state()
    bucket = client.bucket(BUCKET_NAME)
    uploaded = checked = 0
    for current_dir, _dirs, names in os.walk(folder):
        for name in sorted(names):
            if not _is_candidate(name):
                continue
            path = os.path.join(current_dir, name)
            try:
                stat = os.stat(path)
            except OSError as error:
                logger.warning("No se puede leer %s: %s", path, error)
                continue
            known = state.get(path)
            if known and known.get("size") == stat.st_size and (
                known.get("mtime") == stat.st_mtime
            ) and known.get("in_bucket"):
                continue
            checked += 1
            try:
                sha256 = _sha256(path)
                blob = bucket.blob(blob_name_for(sha256, name))
                if blob.exists():
                    logger.info("Ya estaba en el cubo: %s", path)
                else:
                    content_type = (
                        mimetypes.guess_type(name)[0]
                        or "application/octet-stream"
                    )
                    logger.info("Subiendo %s -> %s", path, blob.name)
                    blob.upload_from_filename(
                        path, content_type=content_type,
                    )
                    uploaded += 1
                    log_event("Factura subida: %s" % name)
            except Exception as error:  # noqa: BLE001
                logger.exception("Fallo subiendo %s", path)
                log_event("Error con %s: %s (se reintenta)" % (name, error))
                continue
            state[path] = {
                "size": stat.st_size, "mtime": stat.st_mtime,
                "sha256": sha256, "in_bucket": True,
            }
            save_state(state)
    logger.info(
        "Revision de %s: %d archivo(s) comprobados, %d subidos.",
        folder, checked, uploaded,
    )
    return uploaded
