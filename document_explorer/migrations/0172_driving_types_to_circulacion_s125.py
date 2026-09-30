# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0172_driving_types_to_circulacion_s125.py
# H30 (S125), opción 2 de Miguel Ángel: todo lo que habilita a un
# trabajador para conducir va a la misma familia (Circulación, que en la
# ficha de persona se llama "Conducción"). Antes estaba partido: permiso,
# autorización temporal y certificado CAP en "Identidad y personal
# (base)"; tarjeta CAP y tarjeta de conductor en "Circulación".
# Identidad se queda con lo que identifica a la persona.

from django.db import migrations

DRIVING_CODES = ["CARNET_CONDUCIR", "AUTORIZACION_TEMPORAL_CONDUCIR", "CAP"]


def move_to_circulacion(apps, schema_editor):
    Catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    updated = Catalog.objects.filter(code__in=DRIVING_CODES).update(
        family="CIRCULACION",
    )
    print("0172: %d tipo(s) de conducción a Circulación." % updated)


def move_back(apps, schema_editor):
    Catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    Catalog.objects.filter(code__in=DRIVING_CODES).update(
        family="IDENTIDAD_PERSONAL",
    )


class Migration(migrations.Migration):

    dependencies = [
        ('document_explorer', '0171_worker_submission_duplicates_restore_s125'),
    ]

    operations = [
        migrations.RunPython(move_to_circulacion, move_back),
    ]
