# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0107_fix_castilla_navarro_pacto_permanencia_s110.py
"""
H36 (S110). Cierre del ultimo ambiguo real de la sesion: pk=24671,
CASTILLA_NAVARRO_FRANCISCO_MIGUEL_FORMACION_20210930.pdf -- contenido
real confirmado "PACTO DE PERMANENCIA", no un curso. Ya con la senal
y las reglas CONTENT_WINS correspondientes (commit c7848c3), pero un
unico documento no necesita otra campana --apply completa, se retipa
por pk directamente.
"""
from django.db import migrations


def fix_document_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    try:
        target_type = DocumentTypeCatalog.objects.get(code="PACTO_PERMANENCIA")
    except DocumentTypeCatalog.DoesNotExist:
        return
    DocumentIndexEntry.objects.filter(pk=24671).update(document_type=target_type)


def revert_document_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    try:
        formacion = DocumentTypeCatalog.objects.get(code="FORMACION")
    except DocumentTypeCatalog.DoesNotExist:
        return
    DocumentIndexEntry.objects.filter(pk=24671).update(document_type=formacion)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0106_seed_formacion_prl_grua_movil_autopropulsada_s110"),
    ]

    operations = [
        migrations.RunPython(fix_document_type, revert_document_type),
    ]
