# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/friendly_names.py
"""
Human-friendly display names for indexed files backed by a domain
model (H29 explorer, S039).

Decision of Miguel Ángel, verbatim: "esto realmente no es un
explorador de archivos, es a base de base de datos, realmente podemos
presentar lo que queramos" -- in front of an opaque camera-generated
filename like `AC A26 0200005698_2026-06-25_ALBARAN_AC-A26-
0200005698.jpg.jpg` or `A9081572_albaran-camara_Yrn2qNI.jpg`, the
explorer should show what the delivery note or task photo actually
is: proveedor, máquina, fecha -- built from the already-linked
`DeliveryNote`/`TaskPhoto` row, not the blob name GCS happens to
store.

Bulk-resolved, never per row: `DocumentIndexEntry.domain_object`'s own
docstring warns that dereferencing it while browsing is exactly the
N+1 the whole index exists to avoid. This module resolves one query
per domain model per page (at most a couple hundred ids, bounded by
`PAGE_SIZE`), not one query per row.

Only buckets with a `DOMAIN_MODEL_BY_BUCKET` entry can ever produce a
`domain_object_id` -- the historical bucket (`cgs_grupo_alvarez`) has
none by design (that absence is the very reason the index exists), so
this module never touches it.

---

Nombres de archivo legibles para archivos indexados respaldados por un
modelo de dominio (explorador H29, S039).

Decisión de Miguel Ángel, verbatim: "esto realmente no es un
explorador de archivos, es a base de base de datos, realmente podemos
presentar lo que queramos" -- delante de un nombre de archivo opaco
generado por cámara como `AC A26 0200005698_2026-06-25_ALBARAN_AC-A26-
0200005698.jpg.jpg` o `A9081572_albaran-camara_Yrn2qNI.jpg`, el
explorador debe mostrar lo que el albarán o la foto de tarea realmente
es: proveedor, máquina, fecha -- construido a partir de la fila de
`DeliveryNote`/`TaskPhoto` ya vinculada, no del nombre de blob que GCS
almacena.

Resuelto en bloque, nunca fila a fila: el propio docstring de
`DocumentIndexEntry.domain_object` avisa de que dereferenciarlo al
navegar es justo el N+1 que todo el índice existe para evitar. Este
módulo resuelve una consulta por modelo de dominio y página (como
mucho un par de cientos de ids, acotado por `PAGE_SIZE`), no una
consulta por fila.

Solo los cubos con entrada en `DOMAIN_MODEL_BY_BUCKET` pueden llegar a
tener `domain_object_id` -- el cubo histórico (`cgs_grupo_alvarez`) no
tiene ninguno por diseño (esa ausencia es la razón de ser del índice),
así que este módulo nunca lo toca.
"""
from django.contrib.contenttypes.models import ContentType

from spare_parts.models import DeliveryNote
from work_order_processor.models import TaskPhoto


def resolve_display_names(entries):
    """
    Set `.friendly_name` on every FILE entry in `entries` whose domain
    object this module knows how to name. Folders and files with no
    domain link (or whose linked row is missing/deleted) are left
    untouched -- callers fall back to `.name`, the real blob name,
    exactly as before this module existed.

    ---

    Fija `.friendly_name` en cada entrada FILE de `entries` cuyo objeto
    de dominio este módulo sabe nombrar. Las carpetas y los archivos
    sin vínculo de dominio (o cuya fila vinculada falta/se borró)
    quedan sin tocar -- quien llame recurre a `.name`, el nombre real
    del blob, exactamente igual que antes de que existiera este
    módulo.
    """
    by_content_type = {}
    for entry in entries:
        if entry.is_folder or not entry.domain_object_id:
            continue
        by_content_type.setdefault(
            entry.domain_content_type_id, [],
        ).append(entry)
    if not by_content_type:
        return

    delivery_note_ct_id = ContentType.objects.get_for_model(
        DeliveryNote,
    ).id
    task_photo_ct_id = ContentType.objects.get_for_model(TaskPhoto).id

    if delivery_note_ct_id in by_content_type:
        _resolve_delivery_notes(by_content_type[delivery_note_ct_id])
    if task_photo_ct_id in by_content_type:
        _resolve_task_photos(by_content_type[task_photo_ct_id])


def _joined(*parts):
    return " — ".join(p for p in parts if p)


def _resolve_delivery_notes(entries):
    ids = [entry.domain_object_id for entry in entries]
    notes = (
        DeliveryNote.objects
        .filter(pk__in=ids)
        .select_related("supplier")
        .only(
            "id", "supplier__name", "supplier_name",
            "general_machine_code_raw", "delivery_date",
        )
    )
    by_id = {note.id: note for note in notes}
    for entry in entries:
        note = by_id.get(entry.domain_object_id)
        if note is None:
            continue
        supplier = note.supplier.name if note.supplier_id \
            else note.supplier_name
        name = _joined(
            supplier,
            note.general_machine_code_raw,
            note.delivery_date.strftime("%d-%m-%Y")
            if note.delivery_date else "",
        )
        if name:
            entry.friendly_name = name


def _resolve_task_photos(entries):
    ids = [entry.domain_object_id for entry in entries]
    photos = (
        TaskPhoto.objects
        .filter(pk__in=ids)
        .select_related("machine_asset")
        .only(
            "id", "machine_asset__code", "created_at", "caption",
        )
    )
    by_id = {photo.id: photo for photo in photos}
    for entry in entries:
        photo = by_id.get(entry.domain_object_id)
        if photo is None:
            continue
        name = _joined(
            photo.machine_asset.code if photo.machine_asset_id else "",
            photo.caption,
            photo.created_at.strftime("%d-%m-%Y %H:%M")
            if photo.created_at else "",
        )
        if name:
            entry.friendly_name = name
