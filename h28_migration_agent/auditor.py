# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/auditor.py
"""Read-only local audit of a migrated folder (H28 Fase 2, paso 1).
---
Auditoria local de solo lectura de una carpeta ya migrada (H28 Fase
2, paso 1).

Decision verbatim de Miguel Angel (S034): "Podemos integrarlo en el
agente" -- la auditoria vive como un item mas del menu de bandeja,
nunca como un script suelto que haya que lanzar desde consola.
Coherente con su criterio de S033: "no tener que estar echando mano
de consola para una cosa que debe hacerse desde la plataforma".

La copia local NUNCA se modifica: este modulo solo lee (paso 2 de la
secuencia de la seccion 8 del anexo H28). Produce el dataset con el
que se calibran, con datos reales delante, las tres reglas de
limpieza de la Fase 2: deduplicacion por hash SHA-256, heuristica de
deteccion de dosieres (peso y numero de paginas contra la media de
su carpeta) y catalogo de patrones de nombre por tipo de documento.
---
Read-only local audit of an already-migrated folder (H28 Phase 2,
step 1).

Miguel Angel's verbatim decision (S034): the audit lives as one more
tray menu item, never as a loose script launched from a console.

The local copy is NEVER modified: this module only reads. It
produces the dataset used to calibrate Phase 2's three cleanup
rules against real data.
"""

import csv
import hashlib
import logging
import os
from datetime import datetime

from config import (
    AUDIT_HASH_CHUNK_SIZE_BYTES,
    AUDIT_PROGRESS_EVERY_FILES,
    get_audit_output_dir,
)

logger = logging.getLogger(__name__)

# Column order of the audit CSV. English identifiers, consistent
# with the rest of the codebase -- this is a machine-consumed
# dataset (pandas), not human-facing prose.
# ---
# Orden de columnas del CSV de auditoria. Identificadores en ingles,
# coherente con el resto del codigo -- es un dataset consumido por
# maquina (pandas), no texto para persona.
CSV_COLUMNS = (
    "relative_path",
    "parent_folder",
    "file_name",
    "extension",
    "size_bytes",
    "sha256",
    "page_count",
    "read_error",
)


def to_long_path(path):
    """Return a Windows long-path-safe version of an absolute path.

    ---
    Devuelve una version de la ruta absoluta segura frente al limite
    clasico de 260 caracteres de Windows.

    Origen real (anexo H28, S033): un archivo de `DOC. PERSONAL` con
    una ruta de 256 caracteres fallo la subida con
    `[Errno 22] Invalid argument` y solo se pudo tratar anteponiendo
    el prefijo `\\\\?\\`. La auditoria recorre exactamente el mismo
    arbol, asi que se blinda de entrada en vez de esperar a que
    vuelva a fallar.

    No se aplica fuera de Windows ni a rutas UNC/ya prefijadas.
    ---
    Real origin (H28 annex, S033): a `DOC. PERSONAL` file with a
    256-character path failed to upload with
    `[Errno 22] Invalid argument` and could only be handled with the
    `\\\\?\\` prefix. The audit walks that very same tree, so it is
    hardened up front rather than waiting for the failure to repeat.
    """
    if os.name != "nt":
        return path
    absolute_path = os.path.abspath(path)
    if absolute_path.startswith("\\\\"):
        return absolute_path
    return "\\\\?\\" + absolute_path


def compute_sha256(absolute_path):
    """Return the SHA-256 hex digest of a file, read in chunks.

    ---
    Devuelve el hash SHA-256 en hexadecimal de un archivo, leido por
    trozos.

    Se lee por trozos y no de golpe porque el arbol real contiene
    archivos de varios cientos de MB (manuales escaneados): cargar
    uno entero en memoria no aporta nada y penaliza sin motivo.
    ---
    Read in chunks rather than at once because the real tree holds
    files of several hundred MB (scanned manuals).
    """
    digest = hashlib.sha256()
    with open(to_long_path(absolute_path), "rb") as file_handle:
        while True:
            chunk = file_handle.read(AUDIT_HASH_CHUNK_SIZE_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def count_pdf_pages(absolute_path):
    """Return the number of pages of a PDF, or None if unreadable.

    ---
    Devuelve el numero de paginas de un PDF, o None si no se puede
    leer.

    Verificado en linea el 2026-07-27 (directriz 4.4 del documento
    maestro) contra la documentacion oficial de `pypdf` 6.14.2: la
    API vigente es `PdfReader(ruta)` + `len(reader.pages)`. Se elige
    `pypdf` (BSD-3-Clause, Python puro, wheel `py3-none-any`) y no
    PyMuPDF (AGPL, con extension compilada) porque el agente corre
    empaquetado en Windows sobre Python 3.14 y no debe depender de
    que exista wheel compilada para esa version.

    Un PDF corrupto o cifrado no debe abortar la auditoria completa:
    devuelve None y quien llama registra el motivo en la columna
    `read_error`.
    ---
    Verified online on 2026-07-27 (master document directive 4.4)
    against the official `pypdf` 6.14.2 documentation. A corrupt or
    encrypted PDF must never abort the whole audit: returns None and
    the caller records the reason in the `read_error` column.
    """
    from pypdf import PdfReader

    reader = PdfReader(to_long_path(absolute_path))
    return len(reader.pages)


def _on_walk_error(error):
    """Log a directory that os.walk could not read, never swallow it.

    ---
    Registra un directorio que os.walk no ha podido leer, sin
    tragarselo en silencio.

    Origen real (anexo H28, S033): 4 archivos de `DOC. PERSONAL` no
    llegaron nunca al cubo y no aparecian como fallo en el log --
    el hueco ocurrio en el momento del escaneo (`os.walk`), no en el
    de la subida, y `os.walk` descarta los errores por defecto sin
    decir nada. Aqui se registran explicitamente para que un hueco
    equivalente sea visible de inmediato en vez de detectarse
    semanas despues comparando cifras.
    ---
    Real origin (H28 annex, S033): 4 files never reached the bucket
    and never showed up as a failure -- the gap happened during the
    scan, and `os.walk` silently discards errors by default. Logged
    explicitly here so an equivalent gap is visible immediately.
    """
    logger.error(
        "Auditoria: no se pudo leer el directorio %s: %s",
        getattr(error, "filename", "?"), error,
    )


def build_audit_output_path(root_folder):
    """Build the timestamped CSV path for this audit run.

    ---
    Construye la ruta del CSV con marca de tiempo de esta auditoria.

    Vive bajo `agent_data/` (nunca versionada, ver .gitignore), asi
    que el inventario -- que contiene la estructura documental real
    de la empresa -- nunca puede acabar en un commit por descuido.
    ---
    Lives under `agent_data/` (never versioned), so the inventory --
    which holds the company's real document structure -- can never
    end up in a commit by accident.
    """
    folder_name = os.path.basename(os.path.normpath(root_folder))
    safe_name = "".join(
        character if character.isalnum() else "_"
        for character in folder_name
    ).strip("_") or "carpeta"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(
        get_audit_output_dir(),
        f"auditoria_{safe_name}_{timestamp}.csv",
    )


def audit_folder(root_folder, csv_path, progress_callback=None):
    """Walk root_folder read-only and write the per-file inventory.

    ---
    Recorre root_folder en solo lectura y escribe el inventario por
    archivo.

    Escribe el CSV en streaming (fila a fila) en vez de acumular
    todo en memoria: son ~37.500 archivos entre las dos carpetas ya
    migradas, y no hay ninguna razon para tenerlos todos en RAM.

    Parameters
    ----------
    root_folder : str
        Carpeta local elegida por Miguel Angel en el dialogo.
    csv_path : str
        Ruta de salida del inventario.
    progress_callback : callable, optional
        Se llama con (procesados, bytes_procesados) cada
        AUDIT_PROGRESS_EVERY_FILES archivos.

    Returns
    -------
    dict
        Agregados de la pasada, listos para el informe resumen.
    """
    stats = {
        "file_count": 0,
        "total_bytes": 0,
        "error_count": 0,
        "pdf_count": 0,
        "pdf_with_page_count": 0,
        "total_page_count": 0,
        "hash_counts": {},
        "hash_sizes": {},
        "extension_counts": {},
    }

    with open(
        csv_path, "w", encoding="utf-8-sig", newline="",
    ) as csv_file:
        writer = csv.writer(csv_file, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)

        for current_dir, _dirs, file_names in os.walk(
            root_folder, onerror=_on_walk_error,
        ):
            for file_name in file_names:
                absolute_path = os.path.join(current_dir, file_name)
                relative_path = os.path.relpath(
                    absolute_path, root_folder,
                ).replace(os.sep, "/")
                parent_folder = os.path.dirname(relative_path)
                extension = os.path.splitext(file_name)[1].lower()

                size_bytes = ""
                sha256 = ""
                page_count = ""
                read_error = ""

                try:
                    size_bytes = os.path.getsize(
                        to_long_path(absolute_path),
                    )
                    sha256 = compute_sha256(absolute_path)
                except OSError as error:
                    read_error = f"lectura: {error}"
                    logger.error(
                        "Auditoria: fallo al leer %s: %s",
                        relative_path, error,
                    )

                if extension == ".pdf":
                    stats["pdf_count"] += 1
                    if not read_error:
                        try:
                            page_count = count_pdf_pages(absolute_path)
                            stats["pdf_with_page_count"] += 1
                            stats["total_page_count"] += page_count
                        except Exception as error:
                            # Un PDF corrupto, cifrado o truncado no
                            # puede abortar el inventario completo:
                            # se anota el motivo y se sigue.
                            # ---
                            # A corrupt, encrypted or truncated PDF
                            # must not abort the whole inventory.
                            read_error = f"paginas: {error}"
                            logger.warning(
                                "Auditoria: no se pudieron contar "
                                "las paginas de %s: %s",
                                relative_path, error,
                            )

                writer.writerow((
                    relative_path,
                    parent_folder,
                    file_name,
                    extension,
                    size_bytes,
                    sha256,
                    page_count,
                    read_error,
                ))

                stats["file_count"] += 1
                if read_error:
                    stats["error_count"] += 1
                if isinstance(size_bytes, int):
                    stats["total_bytes"] += size_bytes
                if sha256:
                    stats["hash_counts"][sha256] = (
                        stats["hash_counts"].get(sha256, 0) + 1
                    )
                    stats["hash_sizes"][sha256] = size_bytes
                stats["extension_counts"][extension] = (
                    stats["extension_counts"].get(extension, 0) + 1
                )

                if (
                    progress_callback is not None
                    and stats["file_count"]
                    % AUDIT_PROGRESS_EVERY_FILES == 0
                ):
                    progress_callback(
                        stats["file_count"], stats["total_bytes"],
                    )

    logger.info(
        "Auditoria completada: %d archivos, %d bytes, %d errores. "
        "Inventario en %s",
        stats["file_count"], stats["total_bytes"],
        stats["error_count"], csv_path,
    )
    return stats


def summarise_duplicates(stats):
    """Return duplicate aggregates derived from the hash counts.

    ---
    Devuelve los agregados de duplicados derivados del recuento de
    hashes.

    Un grupo de duplicados son N archivos con el mismo SHA-256. Los
    bytes recuperables son los de las N-1 copias sobrantes: la
    Fase 2 conserva una sola copia de cada contenido, y cual se
    conserva da igual porque el paso de renombrado la renombra de
    todos modos (decision verbatim de Miguel Angel, S033).
    ---
    A duplicate group is N files sharing the same SHA-256.
    Recoverable bytes are those of the N-1 surplus copies.
    """
    duplicate_group_count = 0
    duplicate_file_count = 0
    recoverable_bytes = 0

    for sha256, count in stats["hash_counts"].items():
        if count < 2:
            continue
        duplicate_group_count += 1
        duplicate_file_count += count
        size_bytes = stats["hash_sizes"].get(sha256)
        if isinstance(size_bytes, int):
            recoverable_bytes += size_bytes * (count - 1)

    return {
        "duplicate_group_count": duplicate_group_count,
        "duplicate_file_count": duplicate_file_count,
        "recoverable_bytes": recoverable_bytes,
    }


def build_summary_text(root_folder, csv_path, stats):
    """Build the human-readable Spanish summary of an audit run.

    ---
    Construye el resumen en castellano, legible por una persona, de
    una pasada de auditoria.

    Sirve para dos cosas: comprobar de un vistazo que las cifras
    cuadran con lo ya verificado en S032/S033, y tener delante el
    orden de magnitud de la duplicidad antes de disenar nada.
    ---
    Serves two purposes: checking at a glance that the figures match
    what was already verified in S032/S033, and having the order of
    magnitude of duplication in view before designing anything.
    """
    duplicates = summarise_duplicates(stats)
    top_extensions = sorted(
        stats["extension_counts"].items(),
        key=lambda item: item[1],
        reverse=True,
    )[:15]

    lines = [
        f"Auditoría H28 — Fase 2, paso 1 (solo lectura)",
        f"Carpeta auditada: {root_folder}",
        f"Fecha: {datetime.now().isoformat(timespec='seconds')}",
        f"Inventario: {csv_path}",
        "",
        "== Totales ==",
        f"Archivos: {stats['file_count']:,}".replace(",", "."),
        f"Bytes: {stats['total_bytes']:,}".replace(",", "."),
        f"Errores de lectura: {stats['error_count']:,}".replace(
            ",", ".",
        ),
        "",
        "== Duplicados exactos (mismo SHA-256) ==",
        f"Grupos de duplicados: "
        f"{duplicates['duplicate_group_count']:,}".replace(",", "."),
        f"Archivos implicados: "
        f"{duplicates['duplicate_file_count']:,}".replace(",", "."),
        f"Bytes recuperables al dejar una sola copia: "
        f"{duplicates['recoverable_bytes']:,}".replace(",", "."),
        "",
        "== PDF ==",
        f"Archivos .pdf: {stats['pdf_count']:,}".replace(",", "."),
        f"Con número de páginas leído: "
        f"{stats['pdf_with_page_count']:,}".replace(",", "."),
        f"Páginas totales: "
        f"{stats['total_page_count']:,}".replace(",", "."),
        "",
        "== Extensiones más frecuentes ==",
    ]
    for extension, count in top_extensions:
        label = extension or "(sin extensión)"
        lines.append(f"{label}: {count:,}".replace(",", "."))

    lines.append("")
    lines.append(
        "La copia local no se ha modificado en ningún momento: "
        "esta pasada es exclusivamente de lectura."
    )
    return "\n".join(lines)


def write_summary(summary_text, csv_path):
    """Write the summary next to the CSV and return its path.

    ---
    Escribe el resumen junto al CSV y devuelve su ruta.
    """
    summary_path = os.path.splitext(csv_path)[0] + "_resumen.txt"
    with open(
        summary_path, "w", encoding="utf-8", newline="",
    ) as summary_file:
        summary_file.write(summary_text)
    return summary_path
