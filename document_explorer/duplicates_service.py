# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/duplicates_service.py
"""
Duplicate detection for H29 (S040) -- hash-based, per Miguel Angel's
explicit call in S040 ("Hash de momento").

No new field, no new migration: `DocumentIndexEntry.crc32c` is already
populated at indexing time and is authoritative -- Google Cloud
Storage guarantees it on every object, unlike `md5_hash`, which is
absent on composite/multipart uploads. Two live rows sharing the same
`(crc32c, size_bytes)` pair inside the same bucket are treated as
duplicates. Size is included alongside the checksum only to cut the
already-small chance of a CRC32C collision even further -- it adds no
extra query cost, since `size_bytes` is already indexed inline on the
same row.

Deletion of a duplicate always goes through the two-tier trash already
built for the explorer (3.6/3.10 of the H29 annex) -- this module only
finds groups, it never deletes anything itself.

---

Detección de duplicados para H29 (S040) -- por hash, según la decisión
explícita de Miguel Ángel en S040 ("Hash de momento").

Sin campo nuevo, sin migración nueva: `DocumentIndexEntry.crc32c` ya
se rellena al indexar y es autoritativo -- Google Cloud Storage lo
garantiza en todos los objetos, a diferencia de `md5_hash`, ausente en
subidas compuestas/multipart. Dos filas vivas que comparten el mismo
par `(crc32c, size_bytes)` dentro del mismo cubo se tratan como
duplicados. El tamaño se añade junto al checksum solo para reducir aún
más la ya pequeña probabilidad de colisión de CRC32C -- no añade coste
de consulta extra, porque `size_bytes` ya va en la misma fila.

El borrado de un duplicado siempre pasa por la papelera de dos niveles
ya construida para el explorador (3.6/3.10 del anexo H29) -- este
módulo solo encuentra grupos, nunca borra nada por sí mismo.
"""
from django.db.models import Count, Q

from .models import DocumentIndexEntry


def _live_files_qs(bucket: str, path_prefix: str = ""):
    """
    Live (not deleted, not purged) FILE rows of a bucket, optionally
    scoped to a folder prefix, with a non-empty crc32c.

    ---

    Filas FILE vivas (ni borradas ni vaciadas) de un cubo, opcionalmente
    acotadas a un prefijo de carpeta, con crc32c no vacío.
    """
    qs = DocumentIndexEntry.objects.filter(
        bucket=bucket,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True,
        purged_at__isnull=True,
    ).exclude(crc32c="")
    if path_prefix:
        qs = qs.filter(blob_name__startswith=path_prefix)
    return qs


def find_duplicate_groups(bucket: str, path_prefix: str = ""):
    """
    Return a list of duplicate groups within a bucket (optionally under
    a folder prefix), each group being the list of `DocumentIndexEntry`
    rows sharing the same `(crc32c, size_bytes)`.

    Two queries total, regardless of how many duplicates exist: one to
    find which `(crc32c, size_bytes)` pairs repeat, one to fetch every
    row belonging to those pairs -- never one query per candidate group.

    ---

    Devuelve una lista de grupos de duplicados dentro de un cubo
    (opcionalmente bajo un prefijo de carpeta), siendo cada grupo la
    lista de filas `DocumentIndexEntry` que comparten el mismo
    `(crc32c, size_bytes)`.

    Dos consultas en total, sea cual sea el número de duplicados: una
    para encontrar qué pares `(crc32c, size_bytes)` se repiten, otra
    para traer todas las filas de esos pares -- nunca una consulta por
    grupo candidato.
    """
    base_qs = _live_files_qs(bucket, path_prefix)

    repeated_pairs = (
        base_qs.values("crc32c", "size_bytes")
        .annotate(dup_count=Count("id"))
        .filter(dup_count__gt=1)
    )

    if not repeated_pairs:
        return []

    pair_filter = Q()
    for pair in repeated_pairs:
        pair_filter |= Q(crc32c=pair["crc32c"], size_bytes=pair["size_bytes"])

    matching_rows = list(
        base_qs.filter(pair_filter).order_by(
            "crc32c", "size_bytes", "blob_name"
        )
    )

    groups: dict[tuple, list] = {}
    for row in matching_rows:
        key = (row.crc32c, row.size_bytes)
        groups.setdefault(key, []).append(row)

    return list(groups.values())
