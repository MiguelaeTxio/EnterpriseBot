# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0192_recheck_id_photos_s136.py
"""
H31 (S136, sesión invasora). Vuelve a pasar por el pipeline de foto de
carné a todas las personas sin foto puesta a mano.

Motivo: en S136 se corrigió `id_photo_service` (vigentes antes que
obsoletos, páginas giradas, páginas demasiado grandes para Cloud
Vision). Con datos de producción, 50 de las 140 fotos salían de un
documento obsoleto. Basta con vaciar `photo_attempted_at`: la tarea
`extract_id_photos_task` (cada 15 min, 10 personas por pasada) las
vuelve a buscar y sustituye la foto. Las puestas a mano
(`PersonIdPhoto.is_manual`) no se tocan.

No se puede deshacer (no se guarda la fecha anterior); la vuelta atrás
no hace nada.
"""
from django.db import migrations


def recheck_photos(apps, schema_editor):
    PersonIdentity = apps.get_model("document_explorer", "PersonIdentity")
    PersonIdPhoto = apps.get_model("document_explorer", "PersonIdPhoto")
    manual = PersonIdPhoto.objects.filter(
        is_manual=True,
    ).values_list("person_id", flat=True)
    PersonIdentity.objects.exclude(pk__in=list(manual)).update(
        photo_attempted_at=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0191_seed_v16_catalog_item_s135"),
    ]

    operations = [
        migrations.RunPython(recheck_photos, migrations.RunPython.noop),
    ]
