# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/catchup.py
"""Periodic catch-up sweep for the H28 migration agent.
---
Barrido periodico de puesta al dia del agente de migracion H28.

Punto 2 de la hoja de ruta de S035, habilitado por los tres defectos
corregidos antes que el. Resuelve un agujero real y medido: el
vigilante de eventos NO basta.

Origen (anexo H28, S035): los 22 archivos de `LAVADO NAVARRO`
llegaron al arbol local por sincronizacion de OneDrive a las
11:01:30 y watchdog no reacciono. Nadie se entero hasta que la
auditoria los encontro, hora y media despues. Un archivo que aparece
por sincronizacion desde otro puesto no genera necesariamente los
eventos de sistema de archivos que watchdog vigila.

Reparto real de responsabilidades, corregido por Miguel Angel el
29-07-2026. Verbatim: *"el 99% de los archivos van a entrar por
sincronizacion de Drive y nunca, nunca a mano en este equipo. Por
tanto, es fundamental esos 30 segundos."*

- **Barrido de puesta al dia** (este modulo): la VIA PRINCIPAL de
  entrada. Cada 30 segundos, solo metadatos. Es lo unico que ve los
  archivos que llegan por sincronizacion de OneDrive desde otro
  puesto, que son el 99% del flujo real y no generan evento de
  sistema de archivos alguno.
- **Vigilante** (`watcher.py`): SECUNDARIO. Reacciona en el acto a
  archivos soltados localmente en esta maquina, que segun Miguel
  Angel son el 1% restante. No se retira porque no cuesta nada
  estando parado y cubre ese caso con latencia cero, pero no es el
  mecanismo del que depende el sistema.
- **Reconciliacion** (`reconciler.py`): comparacion completa contra
  el cubo, con MD5. Cara -- 11,5 minutos por carpeta, medido en S035
  -- y por eso se reserva al arranque del agente y a peticion
  manual, nunca en cada barrido.

Este reparto invierte el que se escribio al disenar el modulo, que
daba por primario al vigilante y por red de seguridad al barrido.
Era al reves, y la consecuencia practica es que la cadencia del
barrido gobierna la latencia percibida de TODO el sistema.

Latencia real que cabe esperar, para no prometer de mas: un archivo
que llega sincronizado CON contenido en disco entra en cuarentena en
30 segundos como mucho. Uno que llega como marcador de posicion
necesita ademas que OneDrive lo descargue, asi que seran 30 segundos
mas lo que tarde la hidratacion, resolviendose sola en barridos
sucesivos. Ambos casos se han observado en produccion el 28-07-2026.

Decision de Miguel Angel (S036) sobre el mecanismo de subida: los
archivos detectados se suben **dirigidos y directamente a
cuarentena**, por la misma via que usa el vigilante. Sustituye a la
letra de la hoja de ruta de S035 ("dejar que la reconciliacion los
suba"), que habria significado 23 minutos de hash entre las dos
carpetas cada vez que se hidrata un PDF. El destino -- cuarentena --
nunca estuvo en discusion: viene de la decision 3 de la seccion 3
(S031).
---
Point 2 of the S035 roadmap. Solves a real, measured gap: the event
watcher is NOT enough, because files arriving by OneDrive sync from
another workstation do not necessarily raise the filesystem events
watchdog listens for.

Miguel Angel's decision (S036) on the upload mechanism: detected
files are uploaded **directly and targeted to quarantine**, the same
route the watcher uses, superseding the S035 roadmap wording ("let
reconciliation upload them") which would have meant 23 minutes of
hashing every time a single PDF is hydrated.
"""

import json
import logging
import os

from config import (
    DIRTY_BUCKET_NAME,
    get_catchup_index_dir,
)
from fs_utils import (
    is_cloud_only,
    request_hydration,
    to_long_path,
    to_safe_name,
)
from uploader import (
    iter_relative_file_paths,
    upload_single_file_to_quarantine,
)

logger = logging.getLogger(__name__)


def get_index_path(selected_folder):
    """Return the index file path for a watched folder.
    ---
    Devuelve la ruta del archivo de indice de una carpeta vigilada.

    Un archivo por carpeta y no uno comun, por el mismo criterio que
    ya aplica `_resume_watched_folders`: que una carpeta falle no
    puede arrastrar a las demas.
    ---
    One file per folder rather than a shared one, by the same
    criterion `_resume_watched_folders` already applies.
    """
    return os.path.join(
        get_catchup_index_dir(),
        f"{to_safe_name(selected_folder)}.json",
    )


def load_index(selected_folder):
    """Load the known-files index of a folder.
    ---
    Carga el indice de archivos ya conocidos de una carpeta.

    Returns
    -------
    dict[str, list[int]] | None
        `{ruta_relativa: [tamano, mtime]}`, o None si todavia no hay
        indice -- que no es lo mismo que un indice vacio, y quien
        llama debe distinguirlo (ver `sweep_folder`).
        ---
        `{relative_path: [size, mtime]}`, or None when no index
        exists yet -- which is NOT the same as an empty index.
    """
    index_path = get_index_path(selected_folder)
    if not os.path.isfile(index_path):
        return None
    try:
        with open(index_path, "r", encoding="utf-8") as index_file:
            data = json.load(index_file)
        entries = data.get("entries")
        if not isinstance(entries, dict):
            raise ValueError("entries no es un diccionario")
        return entries
    except (OSError, ValueError, json.JSONDecodeError) as error:
        # Mismo criterio que `state.py`: un indice corrupto no puede
        # tumbar el agente. Se descarta y se reconstruye, lo que como
        # mucho cuesta un barrido sin subidas.
        # ---
        # Same criterion as `state.py`: a corrupt index must not
        # bring the agent down. It is discarded and rebuilt.
        logger.warning(
            "Indice de puesta al dia ilegible (%s): %s. Se "
            "reconstruye desde cero.", index_path, error,
        )
        return None


def save_index(selected_folder, entries):
    """Persist the known-files index of a folder.
    ---
    Persiste el indice de archivos conocidos de una carpeta.
    """
    index_path = get_index_path(selected_folder)
    try:
        with open(index_path, "w", encoding="utf-8") as index_file:
            json.dump(
                {"folder": selected_folder, "entries": entries},
                index_file,
                ensure_ascii=False,
            )
    except OSError as error:
        # Perder el indice no es fatal: el siguiente barrido lo
        # reconstruye. Lo unico que se pierde es una ventana de
        # deteccion.
        # ---
        # Losing the index is not fatal: the next sweep rebuilds it.
        logger.error(
            "No se pudo guardar el indice de puesta al dia de %s: %s",
            selected_folder, error,
        )


def scan_folder(selected_folder):
    """Walk a folder and return its current metadata fingerprint.
    ---
    Recorre una carpeta y devuelve su huella de metadatos actual.

    Solo metadatos: nunca abre ningun archivo. Por eso el barrido
    puede permitirse ser periodico.

    Returns
    -------
    tuple[dict[str, list[int]], list[str]]
        (huella, rutas_solo_en_nube), donde la huella es
        `{ruta_relativa: [tamano, mtime]}`.
        ---
        (fingerprint, cloud_only_relative_paths).
    """
    fingerprint = {}
    cloud_only_paths = []
    for relative_path in iter_relative_file_paths(
        selected_folder, "Puesta al dia"
    ):
        absolute_path = os.path.join(selected_folder, relative_path)
        # UN SOLO `os.stat` por archivo. `st_file_attributes` ya viene
        # en el resultado, asi que la deteccion de solo-en-nube se
        # resuelve con el mismo dato y no hace falta una segunda
        # llamada. A cadencia de 30 minutos daba igual; a cadencia de
        # un minuto sobre ~37.500 archivos son 37.500 llamadas al
        # sistema por barrido en vez de 75.000, y ese barrido corre en
        # la maquina en la que Miguel Angel esta trabajando.
        # ---
        # A SINGLE `os.stat` per file. `st_file_attributes` already
        # comes in the result, so the cloud-only check reuses it. At a
        # 30-minute cadence this was irrelevant; at one minute over
        # ~37,500 files it halves the syscalls per sweep, on the very
        # machine the user is working on.
        try:
            stat_result = os.stat(to_long_path(absolute_path))
        except OSError as error:
            logger.warning(
                "Puesta al dia: no se pudo leer %s: %s",
                absolute_path, error,
            )
            continue
        attributes = getattr(stat_result, "st_file_attributes", None)
        if is_cloud_only(absolute_path, attributes):
            cloud_only_paths.append(relative_path)
            continue
        fingerprint[relative_path] = [
            stat_result.st_size, int(stat_result.st_mtime),
        ]
    return fingerprint, cloud_only_paths


def find_changes(previous_entries, fingerprint):
    """Return the paths that are new or changed since last sweep.
    ---
    Devuelve las rutas nuevas o cambiadas desde el barrido anterior.

    Se compara por ruta, no por fecha. Es deliberado y viene de un
    caso real: en S035, Rocio movio `Z-42 ... ITV 02-08-2026` a
    `OBSOLETOS/`. Mover un archivo **conserva sus fechas**, asi que
    un criterio basado solo en "modificado despues del ultimo
    barrido" no lo habria visto nunca -- y sin embargo en su ruta
    nueva es un archivo que el cubo no tiene.
    ---
    Compared by path, not by date. Deliberate, from a real case: in
    S035 a file was moved to `OBSOLETOS/`. Moving preserves its
    timestamps, so a "modified since last sweep" criterion would
    never have caught it, yet at its new path it is a file the
    bucket does not have.
    """
    changed_paths = []
    for relative_path, current in fingerprint.items():
        previous = previous_entries.get(relative_path)
        if previous is None or list(previous) != list(current):
            changed_paths.append(relative_path)
    return changed_paths


def sweep_folder(client, selected_folder):
    """Run one catch-up sweep over a folder.
    ---
    Ejecuta un barrido de puesta al dia sobre una carpeta.

    **Primer barrido sin indice previo: no sube nada.** Se limita a
    sembrar el indice con lo que hay en disco. Lo contrario --
    tratar los 37.500 archivos ya migrados como "nuevos" -- volcaria
    el arbol entero a cuarentena y, con la decision de Miguel Angel
    de que todo lo que entre en cuarentena genera una llamada a
    Gemini, ademas costaria dinero real.

    El hueco que deja esa siembra lo cubre la reconciliacion
    automatica de arranque, que compara contra el cubo de verdad y
    no depende de ningun indice local. Division limpia: la
    reconciliacion establece la verdad al arrancar, el barrido
    mantiene el delta despues.

    Returns
    -------
    dict
        Resumen con `seeded`, `hydration_requested`, `uploaded`,
        `failed` y `total`.
    ---
    **First sweep with no previous index uploads nothing**: it just
    seeds the index from disk. Treating the 37,500 already-migrated
    files as new would dump the whole tree into quarantine and, given
    every quarantined file triggers a Gemini call, would cost real
    money. The startup reconciliation covers that gap, comparing
    against the bucket itself rather than any local index.
    """
    fingerprint, cloud_only_paths = scan_folder(selected_folder)

    hydration_requested = 0
    for relative_path in cloud_only_paths:
        absolute_path = os.path.join(selected_folder, relative_path)
        if request_hydration(absolute_path):
            hydration_requested += 1

    previous_entries = load_index(selected_folder)
    if previous_entries is None:
        save_index(selected_folder, fingerprint)
        logger.info(
            "Puesta al dia: primer barrido de %s. Indice sembrado "
            "con %d archivo(s); no se sube nada en esta pasada. La "
            "reconciliacion de arranque es la que compara contra el "
            "cubo.", selected_folder, len(fingerprint),
        )
        return {
            "seeded": True,
            "hydration_requested": hydration_requested,
            "uploaded": 0,
            "failed": 0,
            "total": len(fingerprint),
        }

    changed_paths = find_changes(previous_entries, fingerprint)
    if not changed_paths and not hydration_requested:
        # A DEBUG y no a INFO: con cadencia de un minuto, esta linea
        # en INFO serian 1.440 entradas diarias de ruido. El latido
        # periodico que emite `main` es lo que prueba que el hilo
        # sigue vivo.
        # ---
        # DEBUG rather than INFO: at a one-minute cadence this line
        # would be 1,440 daily entries of noise.
        logger.debug(
            "Puesta al dia: sin novedades en %s (%d archivos).",
            selected_folder, len(fingerprint),
        )
        return {
            "seeded": False,
            "hydration_requested": 0,
            "uploaded": 0,
            "failed": 0,
            "total": len(fingerprint),
        }

    uploaded_count = 0
    failed_paths = []
    for relative_path in changed_paths:
        absolute_path = os.path.join(selected_folder, relative_path)
        try:
            upload_single_file_to_quarantine(
                client,
                DIRTY_BUCKET_NAME,
                selected_folder,
                absolute_path,
            )
        except Exception as error:  # noqa: BLE001
            # Mismo criterio que el vigilante tras S036: cualquier
            # excepcion queda registrada con su traza, y el archivo
            # NO se apunta en el indice, para que el barrido
            # siguiente vuelva a intentarlo.
            # ---
            # Same criterion as the watcher after S036: any exception
            # is logged with its traceback, and the file is NOT
            # recorded in the index so the next sweep retries it.
            failed_paths.append(relative_path)
            fingerprint.pop(relative_path, None)
            logger.exception(
                "Puesta al dia: fallo al subir %s a cuarentena: %s",
                absolute_path, error,
            )
        else:
            uploaded_count += 1

    save_index(selected_folder, fingerprint)
    logger.info(
        "Puesta al dia completada en %s: %d subido(s) a cuarentena, "
        "%d fallido(s), %d anclado(s) para descarga, sobre %d "
        "archivo(s).",
        selected_folder, uploaded_count, len(failed_paths),
        hydration_requested, len(fingerprint),
    )
    return {
        "seeded": False,
        "hydration_requested": hydration_requested,
        "uploaded": uploaded_count,
        "failed": len(failed_paths),
        "total": len(fingerprint),
    }
