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

# Atributos de Windows usados por OneDrive Files On-Demand.
#
# Verificados en linea el 2026-07-28 (directriz 4.4) contra varias
# fuentes independientes, y coincidentes con lo medido en produccion
# en S035. Solo `RECALL_ON_DATA_ACCESS` esta documentado formalmente
# por Microsoft; `PINNED` y `UNPINNED` no aparecen en la tabla oficial
# de atributos pero son los que usa OneDrive y los que expone
# `attrib.exe` como `+P` / `+U`.
#
# Estado de un archivo solo-en-nube (marcador de posicion, sin
# contenido en disco): PINNED=0, UNPINNED=1, RECALL_ON_DATA_ACCESS=1.
# De ahi que anclar NO sea solo encender PINNED: hay que apagar
# UNPINNED en la misma llamada, o OneDrive mantiene la intencion
# contraria. Este matiz no estaba registrado en el anexo tras S035.
#
# Cuidado, no confundir con `FILE_ATTRIBUTE_RECALL_ON_OPEN`
# (0x00040000), que es un atributo distinto: el que se midio en
# produccion sobre los 17 archivos reales de `DOC. PERSONAL` fue
# RECALL_ON_DATA_ACCESS.
# ---
# Windows attributes used by OneDrive Files On-Demand, verified
# online on 2026-07-28 against several independent sources and
# matching what was measured in production in S035. A cloud-only
# placeholder has PINNED=0, UNPINNED=1, RECALL_ON_DATA_ACCESS=1, so
# pinning means turning UNPINNED off in the same call, not just
# turning PINNED on.
FILE_ATTRIBUTE_PINNED = 0x00080000
FILE_ATTRIBUTE_UNPINNED = 0x00100000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000


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


def get_file_attributes(path):
    """Return the Windows attribute bitmask of a file, or None.

    ---
    Devuelve la mascara de atributos de Windows de un archivo, o None.

    Barata a proposito: lee metadatos del directorio, **nunca abre el
    archivo**. Medido en S035 sobre el arbol real -- de un marcador de
    posicion de OneDrive, `os.path.getsize` funciona perfectamente
    (metadatos si) y lo que falla es `open()` (contenido no). Detectar
    es, por tanto, gratis; leer no.

    Devuelve None fuera de Windows y ante cualquier error de lectura,
    para que quien llama pueda seguir sin caso especial.
    ---
    Deliberately cheap: reads directory metadata, it **never opens the
    file**. Measured in S035 against the real tree -- for a OneDrive
    placeholder `os.path.getsize` works fine (metadata yes) and
    `open()` is what fails (content no). Detection is free; reading is
    not.
    """
    if os.name != "nt":
        return None
    try:
        return os.stat(to_long_path(path)).st_file_attributes
    except OSError as error:
        logger.warning(
            "No se pudieron leer los atributos de %s: %s", path, error,
        )
        return None


def is_cloud_only(path, attributes=None):
    """Return True if the file is a OneDrive placeholder with no local
    content.

    ---
    Devuelve True si el archivo es un marcador de posicion de OneDrive
    sin contenido en disco.

    Origen real (anexo H28, S035): la auditoria de `DOC. PERSONAL`
    arrojo 23 errores de lectura, 17 de ellos `[Errno 22] Invalid
    argument` sobre archivos de un mismo operario. Se descarto por
    datos que fuera longitud de ruta (con 268 caracteres
    `os.path.getsize` funciona) y que fuera el prefijo `\\\\?\\` (falla
    igual con el y sin el). La causa era esta: marcadores de posicion
    sincronizados desde otro puesto. Filtrar por este bit dio
    exactamente 17, el mismo numero que los errores, por una via
    independiente.

    `attributes` permite reutilizar una mascara ya leida y ahorrarse
    la llamada a `os.stat`.
    ---
    Real origin (H28 annex, S035): the `DOC. PERSONAL` audit produced
    23 read errors, 17 of them `[Errno 22]` on one worker's files.
    Path length was ruled out with data, as was the `\\\\?\\` prefix.
    The cause was placeholders synced from another workstation.
    Filtering by this bit gave exactly 17 -- the same count as the
    errors, by an independent route.
    """
    if attributes is None:
        attributes = get_file_attributes(path)
    if attributes is None:
        return False
    return bool(attributes & FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS)


def compute_pinned_attributes(attributes):
    """Return the attribute mask that pins a file for local download.

    ---
    Devuelve la mascara de atributos que ancla un archivo para que se
    descargue en local.

    Enciende `PINNED` y apaga `UNPINNED` en la misma mascara. Un
    archivo solo-en-nube llega con `UNPINNED` encendido, que es la
    intencion contraria: dejarlo puesto seria darle a OneDrive dos
    ordenes opuestas a la vez. El resto de atributos del archivo
    (archivo, oculto, solo lectura...) se preservan intactos.

    Vive aparte de `request_hydration` a proposito: asi la aritmetica
    de bits se puede comprobar en cualquier sistema operativo y lo
    unico que queda sin probar fuera de Windows es la propia llamada
    al sistema.

    Nota de implementacion: en dos sentencias y no en una sola
    expresion, porque `&` liga mas fuerte que `|` en Python y
    `a | P & ~U` no significa lo que parece.
    ---
    Turns `PINNED` on and `UNPINNED` off in the same mask; a
    cloud-only file arrives with `UNPINNED` set, the opposite intent.
    Every other attribute is preserved. Kept apart from
    `request_hydration` so the bit arithmetic is testable on any OS.
    """
    pinned_attributes = attributes | FILE_ATTRIBUTE_PINNED
    pinned_attributes &= ~FILE_ATTRIBUTE_UNPINNED
    return pinned_attributes


def request_hydration(path):
    """Pin a cloud-only file so OneDrive downloads its content.

    ---
    Ancla un archivo solo-en-nube para que OneDrive descargue su
    contenido.

    Mecanismo validado en produccion en S035 sobre los 17 archivos
    reales: con `PINNED` puesto por esta via, los 17 se anclaron sin
    un solo fallo, `RECALL` paso de 17 a 0 y el PDF de prueba se abrio
    devolviendo `%PDF-`.

    **`attrib.exe` NO sirve para este arbol** y no debe usarse como
    alternativa: devuelve `Formato de parametros incorrecto` sobre
    rutas de 268 caracteres, por ser una herramienta heredada sujeta
    al limite clasico de 260 -- el bit no llega a ponerse. Hay que
    llamar directamente a la API de Windows con el prefijo `\\\\?\\`.

    La descarga que dispara OneDrive es **asincrona**: esta funcion
    pide la rehidratacion, no la espera. Quien llama no debe asumir
    que el contenido esta disponible al volver.

    Returns
    -------
    bool
        True si la peticion se curso, False si no aplica (no Windows)
        o si la llamada al sistema fallo.
        ---
        True if the request went through, False if not applicable or
        the system call failed.
    ---
    Mechanism validated in production in S035 over the 17 real files.
    `attrib.exe` is NOT a valid alternative for this tree: it is a
    legacy tool bound by the classic 260-character limit and fails on
    268-character paths without setting the bit. The download OneDrive
    triggers is asynchronous: this function requests hydration, it
    does not wait for it.
    """
    if os.name != "nt":
        return False

    attributes = get_file_attributes(path)
    if attributes is None:
        return False

    # Encender PINNED y apagar UNPINNED en la misma llamada -- ver
    # `compute_pinned_attributes` para el porque y para la prueba.
    # ---
    # Turn PINNED on and UNPINNED off in the same call.
    new_attributes = compute_pinned_attributes(attributes)

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetFileAttributesW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD,
    )
    kernel32.SetFileAttributesW.restype = wintypes.BOOL

    if not kernel32.SetFileAttributesW(
        to_long_path(path), new_attributes,
    ):
        error_code = ctypes.get_last_error()
        logger.error(
            "No se pudo anclar %s para su descarga (codigo %d)",
            path, error_code,
        )
        return False

    logger.info(
        "Anclado para descarga (solo estaba en la nube): %s", path,
    )
    return True
