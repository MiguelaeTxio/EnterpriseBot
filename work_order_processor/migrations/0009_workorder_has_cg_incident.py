# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/migrations/0009_workorder_has_cg_incident.py

"""
Migration: add has_cg_incident BooleanField to WorkOrder.

Adds the has_cg_incident flag that marks work orders where the operator
assigned a spare part to a cost centre not found in MachineAsset (via the
'Otro' option in the spare-part block selector). Requires SUPERVISOR/ADMIN
review to create the missing cost centre in the database.

---

Migración: añade el campo BooleanField has_cg_incident a WorkOrder.

Añade el flag has_cg_incident que marca los partes en los que el operario
asignó un repuesto a un centro de gasto que no existe en MachineAsset (a
través de la opción 'Otro' del selector de bloque de repuesto). Requiere
revisión de SUPERVISOR/ADMIN para crear el centro de gasto correspondiente.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("work_order_processor", "0008_workorder_has_overlap_incident"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="has_cg_incident",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    "El operario ha asignado un repuesto a un centro de gasto que no "
                    "existe en el catálogo de MachineAsset mediante la opción 'Otro'. "
                    "Requiere revisión por parte de un SUPERVISOR o ADMIN para crear "
                    "el centro de gasto correspondiente en la base de datos."
                ),
                verbose_name="Incidencia de CdG",
            ),
        ),
    ]
