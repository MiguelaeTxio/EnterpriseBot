# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/find_duplicate_documents.py
"""
Django management command: find_duplicate_documents.

Second concrete step of the H28 Fase 2 / H29 merge decided in S039.
The same finding kept surfacing across every search Miguel Angel ran
while curating the type vocabulary (ITV, TACOGRAFO, CONDUCIR...): the
same file living under two or more different folders -- a
reclassification copy-instead-of-move, an internal duplicate inside
the same machine's own tree, or an inconsistent state folder. Five
searches in a row hit the same pattern without adding much new
vocabulary, so this command exists to quantify it directly instead of
discovering it one search at a time.

Two sections, both read-only, both grouping ALREADY-INDEXED metadata
-- no GCS access, no hashing done here:

1. Exact duplicates: same `crc32c` + same `size_bytes` within a
   bucket. GCS computes and returns CRC32C for every object at listing
   time (`index_writer.file_row`), so this is a plain GROUP BY over
   DocumentIndexEntry, not a new computation. Ranked by recoverable
   bytes (size times extra copies), not by copy count, because a
   handful of large duplicated manuals matters more than hundreds of
   small duplicated receipts.
2. Possible compression variants: same base name (extension and known
   compression/state suffixes stripped -- `-comp`, `-opt`, `-opt2`,
   `_compressed`, `_unlocked`, etc., the exact families S035 found by
   hand in Hallazgo 1 of the H28 annex) but DIFFERENT crc32c and size.
   This is a weaker signal than section 1 -- it cannot be confirmed
   without opening the files -- so it is reported separately, never
   merged into the exact-duplicate counts.

This command never decides what to do with a duplicate. Deletion in
this project is always through the explorer's own two-tier trash (H29
design, `document_explorer/views.py`), triggered by a human looking at
a specific file, never by a batch script.

Uso:
    python -m dotenv run python manage.py find_duplicate_documents --bucket cgs_grupo_alvarez
    python -m dotenv run python manage.py find_duplicate_documents --bucket cgs_grupo_alvarez --top 40

---

Comando de gestión Django: find_duplicate_documents.

Segundo paso concreto de la fusión Fase 2 de H28 / H29 decidida en
S039. El mismo hallazgo se repitió en todas las búsquedas que hizo
Miguel Ángel mientras curaba el vocabulario de tipos (ITV, TACOGRAFO,
CONDUCIR...): el mismo archivo viviendo bajo dos o más carpetas
distintas -- una copia por reclasificación en vez de un movimiento, un
duplicado interno dentro del propio árbol de una máquina, o una
carpeta de estado inconsistente. Cinco búsquedas seguidas dieron con
el mismo patrón sin aportar apenas vocabulario nuevo, así que este
comando existe para cuantificarlo directamente en vez de seguir
descubriéndolo búsqueda a búsqueda.

Dos secciones, ambas de solo lectura, ambas agrupando metadatos YA
INDEXADOS -- sin acceso a GCS, sin calcular ningún hash aquí:

1. Duplicados exactos: mismo `crc32c` + mismo `size_bytes` dentro de un
   cubo. GCS calcula y devuelve el CRC32C de cada objeto al listar
   (`index_writer.file_row`), así que esto es un GROUP BY normal sobre
   DocumentIndexEntry, no un cálculo nuevo. Ordenado por bytes
   recuperables (tamaño por copias de más), no por número de copias,
   porque un puñado de manuales grandes duplicados pesa más que
   cientos de recibos pequeños duplicados.
2. Posibles variantes de compresión: mismo nombre base (quitando
   extensión y los sufijos conocidos de compresión/estado -- `-comp`,
   `-opt`, `-opt2`, `_compressed`, `_unlocked`, etc., las mismas
   familias que encontró S035 a mano en el Hallazgo 1 del anexo H28)
   pero `crc32c` y tamaño DISTINTOS. Es una señal más débil que la de
   la sección 1 -- no se puede confirmar sin abrir los archivos --, así
   que se informa aparte, nunca mezclada con los recuentos de
   duplicados exactos.

Este comando nunca decide qué hacer con un duplicado. El borrado en
este proyecto siempre pasa por la papelera de dos niveles del propio
explorador (diseño de H29, `document_explorer/views.py`), disparado
por una persona mirando un archivo concreto, nunca por un script en
lote.
"""
import re

from django.core.management.base import BaseCommand, CommandError

from document_explorer.buckets import INDEXED_BUCKETS, QUARANTINE_PREFIX
from document_explorer.models import DocumentIndexEntry

# Sufijos de variante conocidos, catalogados a mano por S035 (Hallazgo
# 1 del anexo H28: familia de compresión "-comp"/"-opt"/"-opt2", y
# familia de desbloqueo "_unlocked") más los que han ido apareciendo en
# las búsquedas de S039 ("comprimido", " comp"). Se quitan del final
# del nombre base, en cualquier combinación, antes de comparar.
#
# NO se incluye "(N)" -- falso positivo real confirmado con datos de
# producción (S039, 2026-07-30): "libro familia (001).jpg" / "(002)" /
# "(004)" son tres páginas distintas de un mismo documento escaneado,
# no copias ni versiones del mismo archivo. Un número entre paréntesis
# al final del nombre es ambiguo entre "página N" y "copia N" y no se
# puede resolver por el nombre solo -- se deja fuera del stripping
# automático para no generar candidatos falsos en una sección que ya
# es, por diseño, la más débil y menos confirmable de las dos.
_VARIANT_SUFFIX_RE = re.compile(
    r"[\s_-]*(?:comp|opt2|opt|unlocked|comprimido|copia)+$",
    re.IGNORECASE,
)


class Command(BaseCommand):
    help = (
        "Audita duplicados exactos (CRC32C+tamaño, ya indexado) y "
        "posibles variantes de compresion (mismo nombre base, tamano "
        "distinto) sobre un cubo indexado. Solo lectura."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bucket",
            required=True,
            help="Cubo indexado a auditar (obligatorio).",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=40,
            help=(
                "Cuántos grupos mostrar por sección, de más a menos "
                "bytes recuperables. Por defecto 40."
            ),
        )

    def handle(self, *args, **options):
        bucket = options["bucket"]
        if bucket not in INDEXED_BUCKETS:
            raise CommandError(
                "Cubo no indexado: %s (indexados: %s)"
                % (bucket, ", ".join(INDEXED_BUCKETS))
            )
        top_n = options["top"]

        entries = list(
            DocumentIndexEntry.objects
            .filter(
                bucket=bucket,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True,
                purged_at__isnull=True,
            )
            .exclude(blob_name__startswith=QUARANTINE_PREFIX)
            .values_list(
                "blob_name", "size_bytes", "crc32c", "name",
            )
        )
        if not entries:
            self.stdout.write(self.style.WARNING(
                "Sin archivos indexados en %s (¿falta sembrar el "
                "índice con seed_document_index?)." % bucket
            ))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %s -- %d archivo(s) vivos ===" % (bucket, len(entries))
        ))
        self._exact_duplicates(entries, top_n)
        self._compression_variants(entries, top_n)

    # -- Sección 1 ----------------------------------------------------

    def _exact_duplicates(self, entries, top_n):
        groups = {}
        for blob_name, size_bytes, crc32c, _name in entries:
            if not crc32c or not size_bytes:
                continue
            key = (crc32c, size_bytes)
            groups.setdefault(key, []).append(blob_name)

        duplicate_groups = [
            (key, paths) for key, paths in groups.items()
            if len(paths) > 1
        ]
        total_wasted = sum(
            size_bytes * (len(paths) - 1)
            for (crc32c, size_bytes), paths in duplicate_groups
        )
        total_copies = sum(len(paths) - 1 for _key, paths in duplicate_groups)

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n--- Duplicados exactos (CRC32C + tamaño) ---"
        ))
        self.stdout.write(
            "  %d grupo(s) con copias de más, %d copia(s) sobrante(s), "
            "%s recuperables en total."
            % (
                len(duplicate_groups), total_copies,
                self._human_size(total_wasted),
            )
        )

        ranked = sorted(
            duplicate_groups,
            key=lambda item: item[0][1] * (len(item[1]) - 1),
            reverse=True,
        )
        for (crc32c, size_bytes), paths in ranked[:top_n]:
            wasted = size_bytes * (len(paths) - 1)
            self.stdout.write(
                "\n  %s recuperables -- %d copias de %s (crc32c=%s):"
                % (
                    self._human_size(wasted), len(paths),
                    self._human_size(size_bytes), crc32c,
                )
            )
            for path in sorted(paths):
                self.stdout.write("    %s" % path)

    # -- Sección 2 ----------------------------------------------------

    def _base_name(self, name):
        stem = name.rsplit(".", 1)[0] if "." in name else name
        return _VARIANT_SUFFIX_RE.sub("", stem).strip().upper()

    def _compression_variants(self, entries, top_n):
        groups = {}
        for blob_name, size_bytes, crc32c, name in entries:
            if not size_bytes:
                continue
            parent = blob_name.rsplit("/", 1)[0] if "/" in blob_name \
                else ""
            base = self._base_name(name)
            if not base:
                continue
            groups.setdefault((parent, base), []).append(
                (blob_name, size_bytes, crc32c),
            )

        candidates = []
        for (_parent, _base), members in groups.items():
            distinct = {
                (size_bytes, crc32c) for _bn, size_bytes, crc32c in members
            }
            if len(distinct) <= 1:
                continue
            savings = sum(size_bytes for _bn, size_bytes, _c in members) \
                - min(size_bytes for _bn, size_bytes, _c in members)
            candidates.append((savings, members))

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n--- Posibles variantes de compresión (mismo nombre "
            "base, tamaño distinto -- SIN CONFIRMAR) ---"
        ))
        self.stdout.write(
            "  %d grupo(s) candidato(s), hasta %s recuperables si se "
            "confirman y se deja solo la copia menor."
            % (
                len(candidates),
                self._human_size(sum(s for s, _m in candidates)),
            )
        )

        ranked = sorted(candidates, key=lambda item: item[0], reverse=True)
        for savings, members in ranked[:top_n]:
            self.stdout.write(
                "\n  hasta %s recuperables:" % self._human_size(savings)
            )
            for blob_name, size_bytes, _crc32c in sorted(members):
                self.stdout.write(
                    "    %s  (%s)"
                    % (self._human_size(size_bytes), blob_name)
                )

    def _human_size(self, num_bytes):
        value = float(num_bytes)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return "%.1f %s" % (value, unit)
            value /= 1024
        return "%.1f TB" % value
