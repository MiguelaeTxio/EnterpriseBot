# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0148_document_subtypes_permit_label_s120.py
"""
H30 (S120). Subtipos de tipo documental + etiqueta del permiso.

- AddField `DocumentTypeCatalog.parent_type` (FK a sí mismo, null):
  concepto general de subtipo (opción 2 de Miguel Ángel).
- `CARNET_CONDUCIR` pasa a mostrarse como "Permiso de conducción"
  (antes "Carnet / tarjeta de conductor"): quita la duplicidad con
  `TACOGRAFO` ("Tarjeta de Conductor"), origen de 34 documentos mal
  tipados. Solo cambia el texto visible; el código sigue igual.
- Tipo nuevo `AUTORIZACION_TEMPORAL_CONDUCIR`, subtipo del permiso:
  misma familia que `CARNET_CONDUCIR` (leída de la BD, nunca fijada
  aquí), dominio Personal, sin control de caducidad. Primer caso real:
  la hoja provisional de la DGT de Paraschiv (id=36710).
"""
import django.db.models.deletion
from django.db import migrations, models

PERMIT_CODE = "CARNET_CONDUCIR"
PERMIT_NEW_LABEL = "Permiso de conducción"
PERMIT_OLD_LABEL = "Carnet / tarjeta de conductor"
SUBTYPE_CODE = "AUTORIZACION_TEMPORAL_CONDUCIR"
SUBTYPE_LABEL = "Autorización temporal / trámite DGT del permiso"


def forwards(apps, schema_editor):
    """
    Relabel the permit type and create its temporary-authorization subtype.
    ---
    Cambia la etiqueta del permiso y crea su subtipo de autorización
    temporal, idempotente.
    """
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    permit = catalog.objects.get(code=PERMIT_CODE)
    permit.label = PERMIT_NEW_LABEL
    permit.save(update_fields=["label"])
    catalog.objects.update_or_create(
        code=SUBTYPE_CODE,
        defaults={
            "label": SUBTYPE_LABEL,
            "domain": "PERSONAL",
            "family": permit.family,
            "parent_type": permit,
            "tracks_expiry": False,
            "is_active": True,
        },
    )


def backwards(apps, schema_editor):
    """
    Restore the old label and remove the subtype (only if unused).
    ---
    Restaura la etiqueta anterior y borra el subtipo (solo si ningún
    documento lo usa -- PROTECT en DocumentIndexEntry lo impediría).
    """
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.filter(code=PERMIT_CODE).update(label=PERMIT_OLD_LABEL)
    catalog.objects.filter(code=SUBTYPE_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0147_driving_licence_matrix_s120"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypecatalog",
            name="parent_type",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "H30 (S120). Si se rellena, este tipo es un SUBTIPO "
                    "del padre: un documento auxiliar que pertenece a él "
                    "(p. ej. la autorización temporal de la DGT pertenece "
                    "al permiso de conducción). En la ficha, sus "
                    "documentos se pintan DENTRO de la fila del documento "
                    "vigente del padre, nunca como fila propia; y como es "
                    "un tipo distinto, nunca cuenta para los avisos de "
                    "falta/caducidad del padre. Vacío (defecto): tipo "
                    "normal. Decisión de Miguel Ángel (S120, opción 2): "
                    "concepto general, reutilizable para cualquier "
                    "documento auxiliar de otro tipo."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subtypes",
                to="document_explorer.documenttypecatalog",
                verbose_name="Tipo padre (subtipo de)",
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
