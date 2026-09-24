# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0011_default_machine_photo_s118.py
"""
H30 (S118). Barrido de fotos de máquina: a cada máquina ACTIVA sin foto
elegida se le fija como foto (`avatar_document`) su primera imagen ya
indexada. Miguel Ángel: "si hay fotos de una máquina, se coge la primera
y se coloca. Si luego no gusta, pues que se cambie. Pero si gusta, se
deja [...] nos ahorramos el trabajo cuando la foto sea de nuestro
agrado."

Criterio de "la primera":
1. Solo archivos vivos de esa máquina (no borrados ni purgados) con
   extensión de imagen que el navegador sabe pintar (.jpg, .jpeg, .png,
   .webp) -- un .heic no se vería ni en la ficha ni en el listado.
2. Primero las del tipo IMAGEN (fotos de verdad); si no hay, cualquier
   otra imagen de la máquina.
3. Dentro de cada grupo, la indexada antes (id más bajo).

Nunca pisa una foto ya elegida a mano, ni toca el tipo del documento.
Solo máquinas activas (regla de alcance de H30 desde S117). Reverse:
no-op -- deshacerlo borraría también fotos elegidas a mano después.
"""
from django.db import migrations

BUCKET = "cgs_grupo_alvarez"
RENDERABLE_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def set_default_machine_photos(apps, schema_editor):
    """
    Fill avatar_document with the first image of each active machine.
    ---
    Rellena avatar_document con la primera imagen de cada máquina activa.
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
        print("\n  [fleet 0011] Sin ContentType de MachineAsset: nada que hacer.")
        return

    pending_pks = set(MachineAsset.objects.filter(
        is_active=True, avatar_document__isnull=True,
    ).values_list("pk", flat=True))
    print("\n  [fleet 0011] Máquinas activas sin foto: %d" % len(pending_pks))

    # machine pk -> (prioridad, entry pk); prioridad 0 = IMAGEN, 1 = resto.
    best = {}
    rows = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, entry_kind="FILE",
        domain_content_type=machine_ct,
        domain_object_id__in=pending_pks,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).values_list(
        "domain_object_id", "pk", "name", "document_type__code",
    ).order_by("pk")
    for machine_pk, entry_pk, name, type_code in rows.iterator():
        if not (name or "").lower().endswith(RENDERABLE_IMAGE_EXTENSIONS):
            continue
        candidate = (0 if type_code == "IMAGEN" else 1, entry_pk)
        current = best.get(machine_pk)
        if current is None or candidate < current:
            best[machine_pk] = candidate

    by_imagen = 0
    for machine_pk, (priority, entry_pk) in best.items():
        MachineAsset.objects.filter(pk=machine_pk).update(
            avatar_document_id=entry_pk,
        )
        if priority == 0:
            by_imagen += 1

    print("  [fleet 0011] Fotos fijadas: %d (tipo IMAGEN: %d, otra imagen: %d)" % (
        len(best), by_imagen, len(best) - by_imagen,
    ))
    print("  [fleet 0011] Máquinas activas que siguen sin foto (sin ninguna imagen): %d" % (
        len(pending_pks) - len(best),
    ))


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0010_machineasset_avatar_document_s118"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(
            set_default_machine_photos, migrations.RunPython.noop,
        ),
    ]
