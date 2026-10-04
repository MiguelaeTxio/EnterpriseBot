# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0183_merge_subrogation_s127.py
"""
H30 (S127). Fusión: SUBROGACION_CONTRATO (0182) duplicaba el tipo que
ya existía desde S65, CAMBIO_EMPRESA_SUBROGACION (Miguel Ángel:
"Fusiona"). La auditoría de documentos ausentes lo destapó: las cartas
de subrogación de Álvarez Serrano (01/04/2024) y Graña (01/05/2021)
estaban archivadas con el tipo antiguo, que no cubría el alta, y su
"falta el contrato" era falso.

- Los documentos de SUBROGACION_CONTRATO pasan a CAMBIO_EMPRESA_
  SUBROGACION y el tipo duplicado se borra.
- CAMBIO_EMPRESA_SUBROGACION queda como subtipo de CONTRATO, con la
  pista de qué fecha leer en la etiqueta (la ve Gemini).
"""
from django.db import migrations


def forwards(apps, schema_editor):
    """Pasa los documentos al tipo antiguo y borra el duplicado."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    entries = apps.get_model("document_explorer", "DocumentIndexEntry")
    old = catalog.objects.get(code="CAMBIO_EMPRESA_SUBROGACION")
    contract = catalog.objects.get(code="CONTRATO")
    old.label = (
        "Cambio de empresa / subrogación de la relación laboral (fecha: "
        "la de efectos)"
    )
    old.parent_type = contract
    old.save(update_fields=["label", "parent_type"])
    duplicate = catalog.objects.filter(code="SUBROGACION_CONTRATO").first()
    if duplicate is not None:
        entries.objects.filter(document_type=duplicate).update(
            document_type=old,
        )
        duplicate.delete()


def backwards(apps, schema_editor):
    """No se recrea el duplicado."""


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0182_contract_cover_types_s127"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
