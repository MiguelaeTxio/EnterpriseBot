# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/archive_service.py
"""
Shared `.zip`/`.rar` handling (H29, S042) -- listing entries,
extracting one entry's bytes, and computing its real CRC32C. Lives on
its own, imported by both `views.py` (the interactive preview/viewer
Miguel Ángel asked for first) and `classification_service.py` (the
automatic redundancy check built right after, once he made clear he
didn't want a human deciding file by file: "no podemos nosotros
borrar nada... dotar al sistema de las herramientas pertinentes para
que lo haga de forma automática"). Neither module should duplicate
this logic or import it from the other -- `classification_service.py`
must never depend on `views.py`.

`.zip` via stdlib `zipfile` -- no new package. `.rar` via the `unrar`
binary, confirmed installed on this real server (`/usr/bin/unrar`
5.61) with a direct test before a single line of this was written,
same discipline as `soffice`/`fitz` elsewhere in this project: never
assumed.

CRC32C via `google-crc32c` (`google_crc32c.Checksum`) -- already a
transitive dependency of `google-cloud-storage`, no new package
either. Confirmed to match `DocumentIndexEntry.crc32c` exactly (the
same base64-encoded value GCS itself computes on upload) with a real
test against a real file before writing `compute_crc32c()`: the same
photo, once read straight from its own GCS object and once extracted
from inside a `.zip`, produced the identical string.

---

Manejo compartido de `.zip`/`.rar` (H29, S042) -- listar entradas,
extraer los bytes de una, y calcular su CRC32C real. Vive aparte,
importado tanto por `views.py` (el visor interactivo que pidió Miguel
Ángel primero) como por `classification_service.py` (la comprobación
automática de redundancia construida justo después, en cuanto dejó
claro que no quería a un humano decidiendo archivo a archivo: "no
podemos nosotros borrar nada... dotar al sistema de las herramientas
pertinentes para que lo haga de forma automática"). Ninguno de los dos
módulos debe duplicar esta lógica ni importarla del otro --
`classification_service.py` nunca debe depender de `views.py`.

`.zip` vía `zipfile` de la librería estándar -- ningún paquete nuevo.
`.rar` vía el binario `unrar`, confirmado instalado en este servidor
real (`/usr/bin/unrar` 5.61) con una prueba directa antes de escribir
una sola línea de esto, misma disciplina que `soffice`/`fitz` en el
resto del proyecto: nunca supuesto.

CRC32C vía `google-crc32c` (`google_crc32c.Checksum`) -- ya
dependencia transitiva de `google-cloud-storage`, tampoco ningún
paquete nuevo. Confirmado que coincide exactamente con
`DocumentIndexEntry.crc32c` (el mismo valor codificado en base64 que
GCS calcula al subir) con una prueba real antes de escribir
`compute_crc32c()`: la misma foto, leída una vez directamente de su
propio objeto GCS y otra extraída de dentro de un `.zip`, dio la
cadena idéntica.
"""
import base64
import io
import logging
import os
import subprocess
import tempfile
import zipfile

import google_crc32c

logger = logging.getLogger(__name__)

ARCHIVE_EXTENSIONS = {"zip", "rar"}

INLINE_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}

_RAR_TIMEOUT_SECONDS = 60


def inner_extension(inner_path: str) -> str:
    """
    Lowercased extension (with leading dot) of the last path segment
    of `inner_path` -- `""` when there is none. Public (no leading
    underscore) on purpose: both `views.py` and `classification_
    service.py` need it to decide what to do with an archive entry.

    ---

    Extensión en minúsculas (con punto delante) del último segmento
    de ruta de `inner_path` -- `""` cuando no hay ninguna. Pública (sin
    guion bajo delante) a propósito: tanto `views.py` como
    `classification_service.py` la necesitan para decidir qué hacer
    con una entrada de un archivo comprimido.
    """
    last_segment = inner_path.rsplit("/", 1)[-1]
    if "." not in last_segment:
        return ""
    return "." + last_segment.rsplit(".", 1)[-1].lower()


def list_zip_entries(content_bytes: bytes) -> list[dict] | None:
    """
    Lists every real file inside a `.zip` (path + size, directories
    skipped) via stdlib `zipfile`. Returns None on any failure
    (corrupt archive) -- callers must fall back to an error path,
    never guess.

    ---

    Lista cada archivo real de dentro de un `.zip` (ruta + tamaño,
    carpetas omitidas) vía `zipfile` de la librería estándar. Devuelve
    None ante cualquier fallo (archivo dañado) -- quien llama debe
    caer a un camino de error, nunca adivinar.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content_bytes)) as archive:
            return [
                {"path": info.filename, "size": info.file_size}
                for info in archive.infolist() if not info.is_dir()
            ]
    except zipfile.BadZipFile:
        return None


def list_rar_entries(content_bytes: bytes) -> list[dict] | None:
    """
    Lists every real file inside a `.rar` via the `unrar` binary
    (`lb` -- "list, bare": one path per line, no size). Same
    throwaway-tempfile pattern as `_convert_to_pdf()` in
    `classification_service.py` -- `unrar` needs a real file on disk,
    not bytes in memory. `size` always comes back `None` (`unrar lb`
    genuinely does not report it); callers needing a real size must
    extract the entry and measure the bytes themselves.

    Returns None on any failure (corrupt archive, `unrar` missing,
    timeout) -- callers must fall back to an error path, never guess.

    ---

    Lista cada archivo real de dentro de un `.rar` vía el binario
    `unrar` (`lb` -- "list, bare": una ruta por línea, sin tamaño).
    Mismo patrón de directorio temporal desechable que
    `_convert_to_pdf()` en `classification_service.py` -- `unrar`
    necesita un archivo real en disco, no bytes en memoria. `size`
    siempre vuelve `None` (`unrar lb` de verdad no lo da); quien
    necesite un tamaño real debe extraer la entrada y medir los bytes
    él mismo.

    Devuelve None ante cualquier fallo (archivo dañado, falta
    `unrar`, timeout) -- quien llama debe caer a un camino de error,
    nunca adivinar.
    """
    with tempfile.TemporaryDirectory() as workdir:
        input_path = os.path.join(workdir, "input.rar")
        with open(input_path, "wb") as f:
            f.write(content_bytes)
        try:
            result = subprocess.run(
                ["unrar", "lb", input_path],
                check=True, timeout=_RAR_TIMEOUT_SECONDS,
                capture_output=True, text=True,
            )
        except Exception as exc:
            logger.warning(
                "# [list_rar_entries] Fallo listando: %s", exc,
                exc_info=True,
            )
            return None
        return [
            {"path": line, "size": None}
            for line in result.stdout.splitlines() if line
        ]


def extract_zip_entry(content_bytes: bytes, inner_path: str) -> bytes | None:
    """
    Extracts ONE named entry from a `.zip`, in memory only. Returns
    None on any failure (entry not found, corrupt archive).

    ---

    Extrae UNA entrada concreta de un `.zip`, solo en memoria.
    Devuelve None ante cualquier fallo (entrada no encontrada, archivo
    dañado).
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content_bytes)) as archive:
            return archive.read(inner_path)
    except (zipfile.BadZipFile, KeyError):
        return None


def extract_rar_entry(content_bytes: bytes, inner_path: str) -> bytes | None:
    """
    Extracts ONE named entry from a `.rar` straight to stdout
    (`unrar p -inul`) -- never writes the extracted file to disk.
    Confirmed with a real archive before this was written: a
    346 280-byte PDF extracted byte-for-byte, correct header, real
    return code 0. Returns None on any failure.

    ---

    Extrae UNA entrada concreta de un `.rar` directamente a stdout
    (`unrar p -inul`) -- nunca escribe el archivo extraído a disco.
    Confirmado con un archivo real antes de escribir esto: un PDF de
    346.280 bytes extraído byte a byte, cabecera correcta, código de
    retorno real 0. Devuelve None ante cualquier fallo.
    """
    with tempfile.TemporaryDirectory() as workdir:
        input_path = os.path.join(workdir, "input.rar")
        with open(input_path, "wb") as f:
            f.write(content_bytes)
        try:
            result = subprocess.run(
                ["unrar", "p", "-inul", input_path, inner_path],
                check=True, timeout=_RAR_TIMEOUT_SECONDS,
                capture_output=True,
            )
        except Exception as exc:
            logger.warning(
                "# [extract_rar_entry] Fallo extrayendo %r: %s",
                inner_path, exc, exc_info=True,
            )
            return None
        return result.stdout


def list_entries(content_bytes: bytes, extension: str) -> list[dict] | None:
    """
    Dispatches to `list_zip_entries()`/`list_rar_entries()` by
    `extension` ("zip"/"rar", lowercase, no dot). None for anything
    else -- callers must never guess a format from the extension
    alone.

    ---

    Reparte a `list_zip_entries()`/`list_rar_entries()` según
    `extension` ("zip"/"rar", minúscula, sin punto). None para
    cualquier otra cosa -- quien llama nunca debe adivinar un formato
    solo por la extensión.
    """
    if extension == "zip":
        return list_zip_entries(content_bytes)
    if extension == "rar":
        return list_rar_entries(content_bytes)
    return None


def extract_entry(
    content_bytes: bytes, extension: str, inner_path: str,
) -> bytes | None:
    """
    Dispatches to `extract_zip_entry()`/`extract_rar_entry()` by
    `extension`. None for anything else.

    ---

    Reparte a `extract_zip_entry()`/`extract_rar_entry()` según
    `extension`. None para cualquier otra cosa.
    """
    if extension == "zip":
        return extract_zip_entry(content_bytes, inner_path)
    if extension == "rar":
        return extract_rar_entry(content_bytes, inner_path)
    return None


def compute_crc32c(data: bytes) -> str:
    """
    Real CRC32C (Castagnoli) of `data`, base64-encoded exactly like
    `DocumentIndexEntry.crc32c`/GCS's own `blob.crc32c` -- confirmed
    with a real test before writing this (never assumed): the same
    photo, read once from its own live GCS object and once extracted
    from inside a `.zip`, produced the identical string
    (`nE/Fsg==`). Never `zlib.crc32`/`binascii.crc32` -- those
    implement plain CRC-32 (IEEE 802.3), a different polynomial that
    would never match a real GCS checksum no matter how carefully
    encoded.

    ---

    CRC32C real (Castagnoli) de `data`, codificado en base64
    exactamente igual que `DocumentIndexEntry.crc32c`/el propio
    `blob.crc32c` de GCS -- confirmado con una prueba real antes de
    escribir esto (nunca supuesto): la misma foto, leída una vez de
    su propio objeto GCS en vivo y otra extraída de dentro de un
    `.zip`, dio la cadena idéntica (`nE/Fsg==`). Nunca `zlib.crc32`/
    `binascii.crc32` -- esos implementan el CRC-32 normal (IEEE
    802.3), un polinomio distinto que nunca coincidiría con un
    checksum real de GCS por mucho cuidado que se ponga al
    codificarlo.
    """
    checksum = google_crc32c.Checksum()
    checksum.update(data)
    return base64.b64encode(checksum.digest()).decode("ascii")
