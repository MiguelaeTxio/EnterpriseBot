# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/migrations/0004_cae_machine_requirement_fix_s156.py
"""
S156. «CAE · Máquina» exigía a la vez el certificado de mantenimiento y
el libro de mantenimiento (ORDEN_TRABAJO_MANTENIMIENTO): las plataformas
piden uno de los dos y se archiva como certificado (16 de 17 máquinas lo
tienen; el libro, ninguna). Se quita el libro.
"""
from django.db import migrations


def fix(apps, schema_editor):
    JobPosition = apps.get_model("document_explorer", "JobPosition")
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog")
    position = JobPosition.objects.filter(name="CAE · Máquina").first()
    if position is not None:
        position.required_document_types.remove(
            *DocumentTypeCatalog.objects.filter(
                code="ORDEN_TRABAJO_MANTENIMIENTO"))


class Migration(migrations.Migration):

    dependencies = [
        ("cae_mail", "0003_seed_cae_requirements_s156"),
    ]

    operations = [
        migrations.RunPython(fix, migrations.RunPython.noop),
    ]
