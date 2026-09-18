# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0102_merge_prl_generica_en_art_18_19_s110.py
"""
H36 (S110). Fusiona FORMACION_PRL_GENERICA en FORMACION_PRL_ART_18_19
-- confirmado con el Excel real de Yolanda (RRHH, "CURSOS TRABAJADORES
GRUAS"): columna propia "ART.18 Y 19 PRL", sin ninguna columna
"generica" aparte. Son el mismo curso real, nunca dos tipos distintos
-- la senal de FORMACION_PRL_GENERICA era ademas un superconjunto
textual exacto de la de FORMACION_PRL_ART_18_19 (ver
personal_content_classification.py, misma sesion), asi que ya
disparaba el 53% de los "tipo ambiguo" de esta campana (120 de 228).

Retipa los DocumentIndexEntry existentes con document_type =
FORMACION_PRL_GENERICA hacia FORMACION_PRL_ART_18_19 -- sin fecha
limite ni filtro por is_active_employee, se corrige el dato para
cualquier persona, activa o no. FORMACION_PRL_GENERICA se deja en el
catalogo (no se borra, is_active pasa a False) por si algun documento
historico necesita revisarse contra el codigo antiguo.
"""
from django.db import migrations


def merge_into_art_18_19(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    try:
        generica = DocumentTypeCatalog.objects.get(code="FORMACION_PRL_GENERICA")
        art_18_19 = DocumentTypeCatalog.objects.get(code="FORMACION_PRL_ART_18_19")
    except DocumentTypeCatalog.DoesNotExist:
        return
    DocumentIndexEntry.objects.filter(document_type=generica).update(
        document_type=art_18_19,
    )
    generica.is_active = False
    generica.save(update_fields=["is_active"])


def revert_merge(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    try:
        generica = DocumentTypeCatalog.objects.get(code="FORMACION_PRL_GENERICA")
    except DocumentTypeCatalog.DoesNotExist:
        return
    generica.is_active = True
    generica.save(update_fields=["is_active"])
    # No se puede deshacer el retipado de los documentos individuales
    # sin conocer cuales eran -- reversion parcial, solo reactiva el
    # tipo. Documentado aqui para que quede constancia.


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0101_formacion_skip_light_ocr_engines_s110"),
    ]

    operations = [
        migrations.RunPython(merge_into_art_18_19, revert_merge),
    ]
