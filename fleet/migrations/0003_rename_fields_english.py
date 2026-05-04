# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0003_rename_fields_english.py

"""
Migration: rename all MachineAsset, MaintenanceLog and MaintenanceItem fields
to English identifiers in compliance with the Language Golden Rule.

No data is lost — RenameField only alters the column name in the DB schema.

---

Migración: renombrar todos los campos de MachineAsset, MaintenanceLog y
MaintenanceItem a identificadores en inglés según la Regla de Oro del Idioma.

No se pierde ningún dato — RenameField solo altera el nombre de columna en BD.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0002_maintenancelog_work_entry_line"),
    ]

    operations = [

        # ------------------------------------------------------------------
        # MachineAsset field renames / Renombrado de campos MachineAsset
        # ------------------------------------------------------------------
        migrations.RenameField(
            model_name="machineasset",
            old_name="empresa_codigo",
            new_name="company_code",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="empresa_nombre",
            new_name="company_name",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="familia",
            new_name="family",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="tipo_codigo",
            new_name="type_code",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="tipo_nombre",
            new_name="type_name",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="codigo",
            new_name="code",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="matricula",
            new_name="plate",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="num_bastidor",
            new_name="chassis_number",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="marca_modelo",
            new_name="brand_model",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="fecha_compra",
            new_name="purchase_date",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="kms",
            new_name="mileage",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="horas",
            new_name="hours",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="es_activo",
            new_name="is_active",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="importado_en",
            new_name="imported_at",
        ),
        migrations.RenameField(
            model_name="machineasset",
            old_name="actualizado_en",
            new_name="updated_at",
        ),

        # ------------------------------------------------------------------
        # MaintenanceLog field renames / Renombrado de campos MaintenanceLog
        # ------------------------------------------------------------------
        migrations.RenameField(
            model_name="maintenancelog",
            old_name="fecha",
            new_name="date",
        ),
        migrations.RenameField(
            model_name="maintenancelog",
            old_name="descripcion",
            new_name="description",
        ),
        migrations.RenameField(
            model_name="maintenancelog",
            old_name="operario",
            new_name="worker",
        ),
        migrations.RenameField(
            model_name="maintenancelog",
            old_name="horas_imputadas",
            new_name="charged_hours",
        ),
        migrations.RenameField(
            model_name="maintenancelog",
            old_name="observaciones",
            new_name="notes",
        ),
        migrations.RenameField(
            model_name="maintenancelog",
            old_name="creado_en",
            new_name="created_at",
        ),
        migrations.RenameField(
            model_name="maintenancelog",
            old_name="actualizado_en",
            new_name="updated_at",
        ),

        # ------------------------------------------------------------------
        # MaintenanceItem field renames / Renombrado de campos MaintenanceItem
        # ------------------------------------------------------------------
        migrations.RenameField(
            model_name="maintenanceitem",
            old_name="tipo",
            new_name="item_type",
        ),
        migrations.RenameField(
            model_name="maintenanceitem",
            old_name="descripcion",
            new_name="description",
        ),
        migrations.RenameField(
            model_name="maintenanceitem",
            old_name="referencia",
            new_name="reference",
        ),
        migrations.RenameField(
            model_name="maintenanceitem",
            old_name="cantidad",
            new_name="quantity",
        ),
        migrations.RenameField(
            model_name="maintenanceitem",
            old_name="coste_unitario",
            new_name="unit_cost",
        ),
        migrations.RenameField(
            model_name="maintenanceitem",
            old_name="albaran_ref",
            new_name="delivery_note_ref",
        ),
        migrations.RenameField(
            model_name="maintenanceitem",
            old_name="creado_en",
            new_name="created_at",
        ),
    ]
