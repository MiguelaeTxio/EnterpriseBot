# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0129_restaura_plantillas_papelera_s114.py
"""
H31 (S114). Miguel Ángel, tras la migración 0128: "el error lo
tenemos en todas las plantillas pq están todas en la papelera [...]
ninguna de las vigentes ha funcionado". Verificado con consulta real:
de las 4 plantillas vigentes que quedaban (tras 0128) entre las 12
plantillas de comunicación, 3 tienen su `DocumentIndexEntry` con
`deleted_at` no nulo, las 3 exactamente el mismo instante
(2026-08-27 10:19:55, mismo `deleted_by_id=1`) -- un borrado en lote
accidental, no casos aislados:

- INFORMACION_MEDIDAS_PROTECCION -> id=42922
- NOMBRAMIENTO_JEFE_MANIOBRAS -> id=42921
- NOMBRAMIENTO_RESPONSABLE_SEGURIDAD -> id=42919

El cuarto (`PLAN_ACTUACION_CALOR`, id=40356) no está en papelera --
no se toca.

El id=42920 ("PLANTILLA_RECURSO_PREVENTIVO.docx") entra también en
este mismo borrado en lote (mismo instante, mismo deleted_by) -- la
migración 0128 le había puesto `current_template=NULL` a
RECURSO_PREVENTIVO creyendo (a falta de este dato) que el archivo
podía estar mal atribuido como CIRCULAR_INFORMATIVA/Leave Letter.
Con esta consulta queda claro que NO es el mismo caso: el archivo es
un "PLANTILLA_RECURSO_PREVENTIVO.docx" real, en su propia carpeta
("DOC. PERSONAL/NOMBRAMIENTO RECURSO PREVENTIVO/") -- solo estaba en
papelera, nunca mal atribuido. Esta migración lo restaura Y vuelve a
apuntar `RECURSO_PREVENTIVO.current_template` a él.

CIRCULAR_INFORMATIVA sigue sin plantilla (a propósito, sin cambios
aquí) -- ese caso era una mala atribución de contenido (documento
real de ANAGRUAL), no un problema de papelera.

Ningún archivo real se toca en GCS -- solo se limpia `deleted_at`/
`deleted_by` de las filas de índice, igual que haría
`RestoreFromTrashView` a mano, una por una.
"""
from django.db import migrations


_RESTORE_IDS = [42919, 42920, 42921, 42922]

_ORIGINAL_DELETED_AT = {
    42919: "2026-08-27 10:19:55.934625",
    42920: "2026-08-27 10:19:56.162524",
    42921: "2026-08-27 10:19:55.917551",
    42922: "2026-08-27 10:19:55.709973",
}


def restore_from_trash(apps, schema_editor):
    DocumentIndexEntry = apps.get_model("document_explorer", "DocumentIndexEntry")
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")

    DocumentIndexEntry.objects.filter(id__in=_RESTORE_IDS).update(
        deleted_at=None, deleted_by=None,
    )
    DocumentTypeCatalog.objects.filter(code="RECURSO_PREVENTIVO").update(
        current_template_id=42920,
    )


def resend_to_trash(apps, schema_editor):
    DocumentIndexEntry = apps.get_model("document_explorer", "DocumentIndexEntry")
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")

    DocumentTypeCatalog.objects.filter(code="RECURSO_PREVENTIVO").update(
        current_template=None,
    )
    for entry_id in _RESTORE_IDS:
        DocumentIndexEntry.objects.filter(id=entry_id).update(
            deleted_at=_ORIGINAL_DELETED_AT[entry_id], deleted_by_id=1,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0128_corrige_plantillas_rotas_s114"),
    ]

    operations = [
        migrations.RunPython(
            restore_from_trash, resend_to_trash,
        ),
    ]
