# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/migrations/0006_workorder_unique_pdf_hash_per_company.py

"""
Migration 0006 — Add partial UniqueConstraint on (company, source_pdf_hash)
for WorkOrder, excluding rows with an empty hash (synthetic work orders created
via the operator Upload view / Via C).

---

Migración 0006 — Añade UniqueConstraint parcial sobre (company, source_pdf_hash)
en WorkOrder, excluyendo las filas con hash vacío (partes sintéticos creados
desde la vista Upload del operario / Vía C).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("work_order_processor", "0005_add_spare_part_line"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="workorder",
            constraint=models.UniqueConstraint(
                fields    = ["company", "source_pdf_hash"],
                condition = ~models.Q(source_pdf_hash=""),
                name      = "unique_pdf_hash_per_company",
            ),
        ),
    ]
