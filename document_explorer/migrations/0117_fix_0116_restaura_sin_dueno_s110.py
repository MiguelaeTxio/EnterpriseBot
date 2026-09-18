# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0117_fix_0116_restaura_sin_dueno_s110.py
"""
H36 (S110). CORRECCION DE EMERGENCIA de un error real en 0116: el paso
4 de esa migracion (papelera para "resto de FORMACION/CURSO en
activos") no llevaba el filtro domain_content_type_id=PersonIdentity
que si llevaba el resto de la sesion -- toco TODAS las filas con esos
dos tipos en toda la tabla, incluidas 888 FORMACION + 53 CURSO con
domain_content_type_id IS NULL (sin persona ni empresa vinculada,
nunca deberian haberse tocado por un paso pensado solo para activos).

Esta migracion restaura (deleted_at=NULL) exactamente esas filas sin
dueno, dejando intactos los otros 3 efectos reales y correctos de 0116
(ITC_MINERA/PRL_MAQUINARIA, inactivos reales, reasignacion a
TRANSGRUAL). No se restauran las filas de personas activas/inactivas
reales -- esas si estaban dentro del alcance correcto de 0116.
"""
from django.db import migrations


def restore_orphan_rows(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )

    type_id_by_code = dict(
        DocumentTypeCatalog.objects.filter(
            code__in=["FORMACION", "CURSO"],
        ).values_list("code", "id"),
    )

    n = (
        DocumentIndexEntry.objects.filter(
            document_type_id__in=list(type_id_by_code.values()),
            domain_content_type_id__isnull=True,
            deleted_at__isnull=False,
        )
        .update(deleted_at=None)
    )

    print(
        "=== CORRECCION 0116 (S110) ===\n"
        "    restaurados_sin_dueno: %d" % n
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0116_h36_cierre_papelera_y_empresa_s110"),
    ]

    operations = [
        migrations.RunPython(restore_orphan_rows, noop_reverse),
    ]
