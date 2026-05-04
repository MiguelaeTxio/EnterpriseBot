# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/migrations/0007_rename_fields_english.py

from django.db import migrations


class Migration(migrations.Migration):
    """
    Renames six fields in WorkOrderEntry and WorkOrderEntryLine to comply
    with the platform's Regla de Oro del Idioma (all identifiers in English).

    Fields renamed in WorkOrderEntry:
      fecha_incierta  → uncertain_date

    Fields renamed in WorkOrderEntryLine:
      maquina_raw        → machine_raw
      maquina_norm       → machine_norm
      descripcion_averia → fault_description
      reparacion         → repair_notes
      delta_horas        → delta_hours

    No data migration is required — RenameField only alters the column name.
    The Gemini extraction prompt contract (JSON keys) is NOT affected by this
    migration: the prompt uses castellano keys ('maquina_raw', 'descripcion_averia',
    etc.) which are read via dict.get() in services.py / tasks.py and mapped to
    the renamed model fields. Those .get() calls are updated in subsequent PMA
    deliveries (not here).

    ---

    Renombra seis campos en WorkOrderEntry y WorkOrderEntryLine para cumplir
    con la Regla de Oro del Idioma de la plataforma (todos los identificadores
    en inglés).

    Campos renombrados en WorkOrderEntry:
      fecha_incierta  → uncertain_date

    Campos renombrados en WorkOrderEntryLine:
      maquina_raw        → machine_raw
      maquina_norm       → machine_norm
      descripcion_averia → fault_description
      reparacion         → repair_notes
      delta_horas        → delta_hours

    No se requiere migración de datos — RenameField solo altera el nombre de la
    columna. El contrato del prompt de extracción Gemini (claves JSON) NO se ve
    afectado por esta migración: el prompt usa claves en castellano que se leen
    mediante dict.get() en services.py / tasks.py y se mapean a los campos
    renombrados del modelo. Esas llamadas .get() se actualizan en entregas PMA
    posteriores (no aquí).
    """

    dependencies = [
        ("work_order_processor", "0006_workorder_unique_pdf_hash_per_company"),
    ]

    operations = [
        # ------------------------------------------------------------------
        # WorkOrderEntry
        # ------------------------------------------------------------------
        migrations.RenameField(
            model_name="workorderentry",
            old_name="fecha_incierta",
            new_name="uncertain_date",
        ),

        # ------------------------------------------------------------------
        # WorkOrderEntryLine
        # ------------------------------------------------------------------
        migrations.RenameField(
            model_name="workorderentryline",
            old_name="maquina_raw",
            new_name="machine_raw",
        ),
        migrations.RenameField(
            model_name="workorderentryline",
            old_name="maquina_norm",
            new_name="machine_norm",
        ),
        migrations.RenameField(
            model_name="workorderentryline",
            old_name="descripcion_averia",
            new_name="fault_description",
        ),
        migrations.RenameField(
            model_name="workorderentryline",
            old_name="reparacion",
            new_name="repair_notes",
        ),
        migrations.RenameField(
            model_name="workorderentryline",
            old_name="delta_horas",
            new_name="delta_hours",
        ),
    ]
