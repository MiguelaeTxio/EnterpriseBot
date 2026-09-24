# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0012_fix_default_machine_photo_s118.py
"""
H30 (S118). Corrige el barrido de fotos de fleet 0011.

Incidente real (Miguel Ángel, captura de la Z92): 0011 cogía la imagen
de id MÁS BAJO, pero la ficha lista los documentos del más reciente al
más antiguo (order_by("-id")), así que "la primera" que se ve en la
ficha es la de id MÁS ALTO. En la Z92 quedó de foto la placa de
características (`foto placa BRONTO.JPG`, id 14680, la última de la
lista) en vez del camión (`fotos Z-92-3.jpeg`, id 14685, la primera).

Criterio corregido, igual que 0011 salvo el orden:
1. Archivos vivos de la máquina con extensión .jpg/.jpeg/.png/.webp.
2. Primero las de tipo IMAGEN; si no hay, cualquier otra imagen.
3. Dentro de cada grupo, la de id MÁS ALTO (la primera en la ficha).

Solo se corrige la foto de una máquina activa si sigue siendo
exactamente la que eligió 0011 -- una foto cambiada a mano después no
se toca. Reverse: no-op.
"""
from django.db import migrations

BUCKET = "cgs_grupo_alvarez"
RENDERABLE_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def fix_default_machine_photos(apps, schema_editor):
    """
    Re-pick the default photo as the first image shown in the file.
    ---
    Vuelve a elegir la foto por defecto como la primera imagen que
    muestra la ficha, solo donde sigue la que puso fleet 0011.
    """
    MachineAsset = apps.get_model("fleet", "MachineAsset")
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    ContentType = apps.get_model("contenttypes", "ContentType")

    machine_ct = ContentType.objects.filter(
        app_label="fleet", model="machineasset",
    ).first()
    if machine_ct is None:
        print("\n  [fleet 0012] Sin ContentType de MachineAsset: nada que hacer.")
        return

    current_avatar = dict(MachineAsset.objects.filter(
        is_active=True, avatar_document__isnull=False,
    ).values_list("pk", "avatar_document_id"))
    print("\n  [fleet 0012] Máquinas activas con foto: %d" % len(current_avatar))

    # machine pk -> lista de (prioridad, entry pk); 0 = IMAGEN, 1 = resto.
    candidates = {}
    rows = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, entry_kind="FILE",
        domain_content_type=machine_ct,
        domain_object_id__in=list(current_avatar.keys()),
        deleted_at__isnull=True, purged_at__isnull=True,
    ).values_list(
        "domain_object_id", "pk", "name", "document_type__code",
    ).order_by("pk")
    for machine_pk, entry_pk, name, type_code in rows.iterator():
        if not (name or "").lower().endswith(RENDERABLE_IMAGE_EXTENSIONS):
            continue
        candidates.setdefault(machine_pk, []).append(
            (0 if type_code == "IMAGEN" else 1, entry_pk),
        )

    fixed = kept_manual = unchanged = 0
    for machine_pk, avatar_pk in current_avatar.items():
        items = candidates.get(machine_pk)
        if not items:
            kept_manual += 1
            continue
        old_pick = min(items)[1]
        best_priority = min(priority for priority, _pk in items)
        new_pick = max(
            entry_pk for priority, entry_pk in items
            if priority == best_priority
        )
        if avatar_pk != old_pick:
            kept_manual += 1
            continue
        if new_pick == old_pick:
            unchanged += 1
            continue
        MachineAsset.objects.filter(pk=machine_pk).update(
            avatar_document_id=new_pick,
        )
        fixed += 1
        print("  [fleet 0012] Máquina pk=%d: foto %d -> %d" % (
            machine_pk, old_pick, new_pick,
        ))

    print("  [fleet 0012] Fotos corregidas: %d" % fixed)
    print("  [fleet 0012] Ya eran la primera de la ficha: %d" % unchanged)
    print("  [fleet 0012] Elegidas a mano después de 0011 (sin tocar): %d" % (
        kept_manual,
    ))


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0011_default_machine_photo_s118"),
    ]

    operations = [
        migrations.RunPython(
            fix_default_machine_photos, migrations.RunPython.noop,
        ),
    ]
