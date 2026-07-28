# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/fs_utils.py
"""Shared filesystem helpers for the H28 migration agent.
---
Utilidades de sistema de archivos compartidas del agente de
migracion H28.

Este modulo no depende de google-cloud-storage a proposito. Lo usan
por igual el auditor -- estrictamente local y de solo lectura, sin
tocar GCS ni la cuenta de servicio (S034) -- y los modulos que si
hablan con el cubo. Manteniendolo libre de dependencias de red, el
auditor conserva esa frontera sin obligar a duplicar el mismo
blindaje en dos sitios, que es justo el patron que el proyecto evita
desde la taxonomia de averias repetida en cuatro modulos.
---
This module deliberately does not depend on google-cloud-storage. It
is used alike by the auditor -- strictly local and read-only, never
touching GCS nor the service account (S034) -- and by the modules
that do talk to the bucket. Keeping it free of network dependencies
preserves that boundary without duplicating the same hardening in
two places.
"""

import logging
import os

logger = logging.getLogger(__name__)


def to_long_path(path):
    """Return a Windows long-path-safe version of an absolute path.

    ---
    Devuelve una version de la ruta absoluta segura frente al limite
    clasico de 260 caracteres de Windows.

    Origen real (anexo H28, S033): un archivo de `DOC. PERSONAL` con
    una ruta de 256 caracteres fallo la subida con
    `[Errno 22] Invalid argument` y solo se pudo tratar anteponiendo
    el prefijo `\\\\?\\`.

    Matiz medido en S035, importante para no sacar la conclusion
    equivocada: el prefijo resuelve el limite de longitud de ruta,
    pero NO resuelve un archivo marcador de posicion de OneDrive sin
    contenido en disco. Ahi `os.path.getsize` funciona y lo que falla
    es `open()`, con el mismo `[Errno 22]` -- son dos causas
    distintas con el mismo sintoma, y esta funcion solo cubre la
    primera.

    No se aplica fuera de Windows ni a rutas UNC/ya prefijadas.
    ---
    Real origin (H28 annex, S033): a `DOC. PERSONAL` file with a
    256-character path failed to upload with
    `[Errno 22] Invalid argument` and could only be handled with the
    `\\\\?\\` prefix.

    Nuance measured in S035: the prefix fixes the path-length limit
    but NOT a OneDrive placeholder file with no content on disk,
    where `os.path.getsize` works and `open()` is what fails, with
    the very same `[Errno 22]`. Two different causes, one symptom;
    this helper covers only the first.
    """
    if os.name != "nt":
        return path
    absolute_path = os.path.abspath(path)
    if absolute_path.startswith("\\\\"):
        return absolute_path
    return "\\\\?\\" + absolute_path


def make_walk_error_handler(context_label):
    """Build an `onerror` handler for `os.walk` that never stays mute.

    ---
    Construye un manejador `onerror` para `os.walk` que nunca se
    calla.

    `os.walk` descarta por defecto cualquier error de lectura de
    directorio sin decir absolutamente nada: el recorrido simplemente
    no baja por esa rama y devuelve menos archivos, sin que nada lo
    delate. Sobre un arbol de decenas de miles de archivos eso es
    indistinguible de una carpeta que de verdad esta vacia.

    Origen real (anexo H28, S032-S033): 4 archivos de
    `DOC. PERSONAL` nunca llegaron al cubo y no figuraban como fallo
    en ningun sitio -- el propio recuento inicial del agente ya no
    los incluia. El hueco ocurrio durante el escaneo, no durante la
    subida. Y lo que el recorrido no ve, la reconciliacion tampoco
    puede repararlo despues, porque parte del mismo recorrido.

    El label identifica que operacion estaba recorriendo el arbol
    (copia inicial, reconciliacion, auditoria), porque las tres usan
    el mismo escaneo y sin el no se sabe cual dejo el hueco.

    Parameters
    ----------
    context_label : str
        Operacion que esta recorriendo el arbol, para el log.
        ---
        Operation walking the tree, used in the log line.

    Returns
    -------
    callable
        Handler apto para `os.walk(..., onerror=...)`.
        ---
        Handler suitable for `os.walk(..., onerror=...)`.
    ---
    `os.walk` silently discards any directory read error by default:
    the walk simply does not descend into that branch and returns
    fewer files, with nothing giving it away.

    Real origin (H28 annex, S032-S033): 4 `DOC. PERSONAL` files never
    reached the bucket and were never reported as a failure. The gap
    happened during the scan, not the upload. And what the walk never
    sees, reconciliation cannot repair afterwards either, because it
    starts from that same walk.
    """

    def _on_walk_error(error):
        logger.error(
            "%s: no se pudo leer el directorio %s: %s",
            context_label,
            getattr(error, "filename", "?"),
            error,
        )

    return _on_walk_error
