# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/migrations/0016_workorder_source_pdf_name.py

"""
Migration: add WorkOrder.source_pdf_name field.

Adds a CharField(max_length=255, blank=True, default="") to WorkOrder.
Persists the original PDF filename at upload time so that pdf_display_name
remains accurate after the Celery pipeline deletes the physical file.

---

Migración: añade el campo WorkOrder.source_pdf_name.

Añade un CharField(max_length=255, blank=True, default="") a WorkOrder.
Persiste el nombre original del fichero PDF en el momento de la carga para
que pdf_display_name siga siendo correcto tras el borrado del fichero físico
por el pipeline Celery.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("work_order_processor", "0015_workorderentryline_fault_fields_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="source_pdf_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Nombre del fichero PDF original tal como fue subido por el usuario. "
                    "Se persiste en el momento de la carga y sobrevive al borrado del "
                    "fichero físico ejecutado por el pipeline Celery (Paso 5). "
                    "Vacío en partes de origen DIGITAL o GENERATED."
                ),
                max_length=255,
                verbose_name="Nombre original del PDF",
            ),
        ),
    ]
