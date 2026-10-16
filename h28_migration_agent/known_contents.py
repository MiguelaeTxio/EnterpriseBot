# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/known_contents.py
"""Content already present in Google Cloud Storage, by size and MD5.
---
Contenido que ya existe en Google Cloud Storage, por tamano y MD5.

S128 (H30, desvio a H28). Decision verbatim de Miguel Angel: *"si un
hash esta ya repetido, ni se sube, ni se clasifica, ni nada de nada,
este en la papelera, este en la carpeta [que sea] porque se haya
cambiado y se haya clasificado. Si el archivo esta en GCS, no podemos
volver a subirlo ni a clasificarlo."*

Origen real: tras 7-10 dias con OneDrive en pausa, la puesta al dia
del 16/10 encontro 3.478 rutas que su indice local no conocia en
`DOC. MAQUINAS` (carpetas de maquina con otro nombre, archivos que
vuelven a estar en local). El agente solo comparaba rutas, asi que
las habria subido todas a cuarentena, y el servidor las habria
clasificado otra vez con Gemini salvo que tuvieran un gemelo vivo
archivado (los gemelos en papelera no cuentan alli).

Este modulo cierra el paso en el origen: antes de subir nada, el
agente comprueba si el contenido (tamano + MD5) ya existe en
cualquier objeto del cubo -- arbol espejo, cuarentena, o lo que sea.
La papelera del panel es una marca en base de datos (directriz 4.12):
el objeto sigue en GCS, asi que tambien cuenta. Solo un objeto
borrado de verdad del cubo deja de contar.

El MD5 del listado llega gratis, en la misma pagina de
`list_blobs` (ver `reconciler._list_remote_info`). Lo unico que cuesta
es leer el archivo local, y solo se hace con los que se iban a subir.
Si el listado del cubo falla, la comprobacion falla con el: nunca se
sube a ciegas.
---
S128 (H30, detour to H28). Miguel Angel's verbatim decision: if the
content is already in GCS -- wherever it is, trash included -- it is
neither uploaded nor classified again. Before any upload the agent
checks whether the content (size + MD5) already exists in any object
of the bucket. The panel trash is a database flag (directive 4.12):
the object is still in GCS, so it counts too. If listing the bucket
fails, the check fails with it: nothing is ever uploaded blindly.
"""

import base64
import hashlib
import logging
import threading
import time

from config import (
    HASH_CHUNK_SIZE_BYTES,
    KNOWN_CONTENTS_REFRESH_SECONDS,
)
from fs_utils import to_long_path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_known_by_size = {}
_loaded_at = None
_loaded_bucket = None


def compute_md5_base64(local_path):
    """Return the base64-encoded MD5 of a local file, GCS style.
    ---
    Devuelve el MD5 en base64 de un archivo local, en el mismo
    formato que usa GCS.

    Verificado en linea el 2026-07-27 (directriz 4.4) contra la
    documentacion oficial de google-cloud-storage: `blob.md5_hash`
    viene codificado en BASE64, no en hexadecimal -- comparar contra
    un `hexdigest()` daria distinto siempre, aunque el contenido
    fuese identico. (Movido aqui desde `reconciler.py` en S128 para
    que lo compartan la reconciliacion y la puesta al dia.)
    ---
    Verified online on 2026-07-27 (directive 4.4): `blob.md5_hash` is
    BASE64-encoded, not hexadecimal. (Moved here from `reconciler.py`
    in S128 so reconciliation and catch-up share it.)
    """
    digest = hashlib.md5()
    with open(to_long_path(local_path), "rb") as file_handle:
        while True:
            chunk = file_handle.read(HASH_CHUNK_SIZE_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


def _refresh(client, bucket_name):
    """List the whole bucket and rebuild the size -> MD5s map.
    ---
    Lista el cubo entero y reconstruye el mapa tamano -> MD5s.

    Se llama con `_lock` tomado. Una excepcion del listado se propaga
    tal cual: quien llama no debe subir nada si no sabe que hay en el
    cubo.
    """
    global _known_by_size, _loaded_at, _loaded_bucket
    started_at = time.monotonic()
    known_by_size = {}
    object_count = 0
    without_md5 = 0
    for blob in client.bucket(bucket_name).list_blobs():
        object_count += 1
        if blob.md5_hash is None:
            # Objetos compuestos: GCS no da MD5 (documentacion
            # oficial). No se pueden comparar por contenido.
            # ---
            # Composite objects: GCS gives no MD5.
            without_md5 += 1
            continue
        known_by_size.setdefault(blob.size, set()).add(blob.md5_hash)
    _known_by_size = known_by_size
    _loaded_at = time.monotonic()
    _loaded_bucket = bucket_name
    logger.info(
        "Contenido ya en GCS: listados %d objeto(s) de %s en %.1f s "
        "(%d sin MD5, no comparables).",
        object_count, bucket_name, _loaded_at - started_at, without_md5,
    )


def _ensure_fresh(client, bucket_name):
    """Refresh the map when missing, stale, or from another bucket.
    ---
    Refresca el mapa si no existe, esta caducado o es de otro cubo.
    """
    stale = (
        _loaded_at is None
        or _loaded_bucket != bucket_name
        or time.monotonic() - _loaded_at > KNOWN_CONTENTS_REFRESH_SECONDS
    )
    if stale:
        _refresh(client, bucket_name)


def find_known_md5(client, bucket_name, local_path, local_size):
    """Return the file's MD5 if that content is already in the bucket.
    ---
    Devuelve el MD5 del archivo si ese contenido ya esta en el cubo.

    Returns
    -------
    str | None
        El MD5 en base64 si hay un objeto con el mismo tamano y el
        mismo MD5; None si el contenido no esta en GCS.
        ---
        The base64 MD5 when an object with the same size and MD5
        exists; None when the content is not in GCS.

    Raises
    ------
    Exception
        Si falla el listado del cubo o la lectura del archivo local.
        Quien llama lo trata como un fallo de subida: el archivo se
        reintenta despues, nunca se sube sin comprobar.
        ---
        If listing the bucket or reading the local file fails. The
        caller treats it as an upload failure and retries later.
    """
    with _lock:
        _ensure_fresh(client, bucket_name)
        candidates = _known_by_size.get(local_size)
        if not candidates:
            return None
        local_md5 = compute_md5_base64(local_path)
        if local_md5 in candidates:
            return local_md5
        return None


def remember_upload(local_path, local_size):
    """Add a file the agent has just uploaded to the known map.
    ---
    Anade al mapa un archivo que el agente acaba de subir.

    Asi, si el mismo contenido aparece dos veces en la misma pasada
    (dos carpetas con la misma copia), la segunda ya no se sube aunque
    el mapa no se haya vuelto a listar.
    ---
    So the same content appearing twice in one pass is uploaded only
    once, without relisting the bucket.
    """
    try:
        local_md5 = compute_md5_base64(local_path)
    except OSError as error:
        logger.warning(
            "Contenido ya en GCS: no se pudo anotar %s: %s",
            local_path, error,
        )
        return
    with _lock:
        _known_by_size.setdefault(local_size, set()).add(local_md5)
