# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/migrations/0015_workorderentryline_fault_fields_default.py
"""
Corrective migration: ensures fault_category and fault_subcategory columns on
WorkOrderEntryLine have DEFAULT '' at the MySQL DDL level.

Django's AddField with default="" and blank=True does not emit a DEFAULT clause
in the generated MySQL DDL, causing IntegrityError on INSERT when the columns
are omitted from the statement (e.g. the PDF processing pipeline in tasks.py).

The fix was applied manually via ALTER TABLE in the MySQL console on 2026-05-13.
This migration makes that fix permanent and records it in Django's migration
history so the schema is reproducible from scratch on any fresh environment.

---

Migración correctiva: garantiza que las columnas fault_category y
fault_subcategory de WorkOrderEntryLine tienen DEFAULT '' a nivel de DDL MySQL.

El AddField de Django con default="" y blank=True no emite cláusula DEFAULT en
el DDL MySQL generado, causando IntegrityError en INSERT cuando las columnas
se omiten del statement (p. ej. el pipeline de procesamiento PDF en tasks.py).

El fix se aplicó manualmente via ALTER TABLE en la consola MySQL el 2026-05-13.
Esta migración hace el fix permanente y lo registra en el historial de
migraciones de Django para que el esquema sea reproducible en cualquier
entorno limpio.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("work_order_processor", "0014_workorderentryline_fault_category_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE work_order_processor_workorderentryline "
                "ALTER COLUMN fault_category SET DEFAULT '';"
            ),
            reverse_sql=(
                "ALTER TABLE work_order_processor_workorderentryline "
                "ALTER COLUMN fault_category DROP DEFAULT;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE work_order_processor_workorderentryline "
                "ALTER COLUMN fault_subcategory SET DEFAULT '';"
            ),
            reverse_sql=(
                "ALTER TABLE work_order_processor_workorderentryline "
                "ALTER COLUMN fault_subcategory DROP DEFAULT;"
            ),
        ),
    ]
