# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0104_fix_diaz_quintero_grua_hidraulica_s110.py
"""
H36 (S110). Corrige un documento real mal archivado en el momento de
subirlo: `DIAZ_QUINTERO_ANTONIO_JESUS_CARNET_GRUISTA_20221020.pdf`
(pk=35075) lleva el codigo CARNET_GRUISTA en el nombre y en el tipo,
pero su contenido real es el "CERTIFICADO DE OPERADOR DE GRUA
HIDRAULICA ARTICULADA - NORMA UNE 58161" de ANAGRUAL (confirmado por
Miguel Angel, que lo encontro manualmente en el explorador de
archivos al no aparecer en la ficha bajo el tipo correcto). Nunca
paso por ninguna campana de retipado de esta sesion porque esas solo
recorrieron FORMACION y CURSO, nunca CARNET_GRUISTA.

Fix puntual por pk, no una regla de contenido -- es un unico
documento mal clasificado al subirlo, no un patron sistematico.
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
        target_type = DocumentTypeCatalog.objects.get(
            code="FORMACION_GRUA_HIDRAULICA_ARTICULADA",
        )
    except DocumentTypeCatalog.DoesNotExist:
        return
    DocumentIndexEntry.objects.filter(
        name="DIAZ_QUINTERO_ANTONIO_JESUS_CARNET_GRUISTA_20221020.pdf",
    ).update(document_type=target_type)


def revert_document_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    try:
        carnet_gruista = DocumentTypeCatalog.objects.get(code="CARNET_GRUISTA")
    except DocumentTypeCatalog.DoesNotExist:
        return
    DocumentIndexEntry.objects.filter(
        name="DIAZ_QUINTERO_ANTONIO_JESUS_CARNET_GRUISTA_20221020.pdf",
    ).update(document_type=carnet_gruista)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0103_curso_skip_light_ocr_engines_s110"),
    ]

    operations = [
        migrations.RunPython(fix_document_type, revert_document_type),
    ]
