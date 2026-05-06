# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/migrations/0008_workorder_has_overlap_incident.py
#
# Migration: add has_overlap_incident BooleanField to WorkOrder.
# Generated manually — Hito 7 / Validaciones (2026-05-06).
#
# Migración: añade el campo has_overlap_incident BooleanField a WorkOrder.
# Generada manualmente — Hito 7 / Validaciones (2026-05-06).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("work_order_processor", "0007_rename_fields_english"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="has_overlap_incident",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    "Indica que este parte presenta solapamiento de franjas horarias "
                    "con otro parte del mismo operario y misma fecha. Se activa "
                    "automáticamente al guardar y debe resolverse editando los "
                    "partes en conflicto hasta eliminar el solapamiento."
                ),
                verbose_name="Incidencia de solapamiento",
            ),
        ),
    ]
