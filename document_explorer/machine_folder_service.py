# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/machine_folder_service.py
"""
H30 (S119), roadmap item 3. Keeps every document of a machine inside
its ACTIVAS/INACTIVAS folder.
---
H30 (S119), punto 3 de la hoja de ruta. Mantiene todos los documentos
vivos de una máquina dentro de su carpeta ACTIVAS/{FAMILIA}/{CÓDIGO} o
INACTIVAS/{CÓDIGO} (`naming_service.build_machine_folder_path`).

Solo virtual, igual que la reorganización de Personal (S99): cambia
`parent_path`/`name` en la base de datos con `move_service.
move_entries()` (lote eficiente, contadores de carpeta al día), nunca
`blob_name` ni GCS. La usan el comando de reorganización y el alta/
baja de una máquina desde el panel, para que la carpeta siga siempre
al estado real de la máquina.
"""
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from document_explorer.buckets import NO_CONFORMES_PREFIX, quarantine_scope_q
from document_explorer.models import DocumentIndexEntry
from document_explorer.move_service import move_entries
from document_explorer.naming_service import build_machine_folder_path

BUCKET = "cgs_grupo_alvarez"


def machine_folder_for(asset) -> str:
    """
    Return the virtual folder where this machine's documents live.
    ---
    Devuelve la carpeta virtual donde viven los documentos de la
    máquina, según su familia y su estado actual.
    """
    return build_machine_folder_path(
        asset.code, asset.family, asset.is_active,
    )


def outside_intake_q():
    """
    Q excluding files still in quarantine or NO CONFORMES.
    ---
    Excluye lo que sigue en `_CUARENTENA` o en `NO CONFORMES`: esos los
    reubica el propio flujo de clasificación, nunca esta vía.
    """
    no_conformes = NO_CONFORMES_PREFIX.rstrip("/")
    return ~quarantine_scope_q() & ~(
        Q(parent_path=no_conformes)
        | Q(parent_path__startswith=NO_CONFORMES_PREFIX)
    )


def machine_entries_to_move(asset):
    """
    Live files of this machine that are not yet in its folder.
    ---
    Archivos vivos de la máquina que todavía no están en su carpeta
    (fuera de cuarentena y de NO CONFORMES).
    """
    from fleet.models import MachineAsset

    target = machine_folder_for(asset)
    return target, list(DocumentIndexEntry.objects.filter(
        bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        domain_content_type=ContentType.objects.get_for_model(MachineAsset),
        domain_object_id=asset.pk,
    ).filter(outside_intake_q()).exclude(
        parent_path=target,
    ).order_by("id"))


def move_machine_documents(asset) -> int:
    """
    Move every live file of this machine into its folder; return how
    many moved.
    ---
    Mueve todos los archivos vivos de la máquina a su carpeta y
    devuelve cuántos se han movido.
    """
    target, entries = machine_entries_to_move(asset)
    if not entries:
        return 0
    return len(move_entries(entries, target))
