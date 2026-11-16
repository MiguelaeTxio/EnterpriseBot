# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0038_machine_logbook_s154.py
"""
H23 (S154, invasora) -- libro historial de la grúa: datos de
identificación, pesos y dimensiones y titularidad inicial en la ficha
de la máquina, y las filas leídas de los libros escaneados.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0037_machineasset_first_itv_s153"),
        ("document_explorer", "0146_undo_machine_document_requirement_s119"),
        ("ivr_config", "0056_workdayscheduleday_holiday_s144"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineasset",
            name="crane_serial_number",
            field=models.CharField(
                blank=True, default="", max_length=100,
                verbose_name="Número de serie",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="manufacture_year",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Año de fabricación",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="max_capacity",
            field=models.CharField(
                blank=True, default="", max_length=60,
                help_text="Tal como figura en el libro (p. ej. 35 t).",
                verbose_name="Capacidad máxima",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="length_mm",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Longitud (mm)",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="width_mm",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Anchura (mm)",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="height_mm",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Altura (mm)",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="mass_kg",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Masa (kg)",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="axle_count",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Número de ejes",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="axle_mass",
            field=models.CharField(
                blank=True, default="", max_length=120,
                help_text="Tal como figura en el libro (p. ej. 12.000 kg).",
                verbose_name="Masa por eje",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="first_owner_name",
            field=models.CharField(
                blank=True, default="", max_length=200,
                verbose_name="Primer propietario",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="first_owner_tax_id",
            field=models.CharField(
                blank=True, default="", max_length=20,
                verbose_name="NIF/CIF del primer propietario",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="first_owner_address",
            field=models.CharField(
                blank=True, default="", max_length=255,
                verbose_name="Domicilio del primer propietario",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="first_owner_city",
            field=models.CharField(
                blank=True, default="", max_length=255,
                verbose_name="C.P. y población del primer propietario",
            ),
        ),
        migrations.CreateModel(
            name="MachineLogbookSource",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True,
                        serialize=False, verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("SCAN", "Libro escaneado"),
                            ("GENERATED", "Libro generado"),
                        ],
                        max_length=10, verbose_name="Origen",
                    ),
                ),
                (
                    "rows_found",
                    models.PositiveIntegerField(
                        default=0, verbose_name="Filas leídas",
                    ),
                ),
                (
                    "error",
                    models.TextField(
                        blank=True, default="",
                        verbose_name="Error de lectura",
                    ),
                ),
                (
                    "processed_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Procesado el",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+", to="ivr_config.companyuser",
                        verbose_name="Generado por",
                    ),
                ),
                (
                    "document",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logbook_source",
                        to="document_explorer.documentindexentry",
                        verbose_name="Documento",
                    ),
                ),
                (
                    "machine",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logbook_sources",
                        to="fleet.machineasset",
                        verbose_name="Centro de gasto",
                    ),
                ),
            ],
            options={
                "verbose_name": "Documento del libro historial",
                "verbose_name_plural": "Documentos del libro historial",
                "ordering": ["-processed_at"],
            },
        ),
        migrations.CreateModel(
            name="MachineLogbookEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True,
                        serialize=False, verbose_name="ID",
                    ),
                ),
                (
                    "section",
                    models.CharField(
                        choices=[
                            ("INSPECTION_BASE",
                             "Inspección oficial de la base"),
                            ("INSPECTION_STRUCTURE",
                             "Inspección oficial de la estructura"),
                            ("PERIODIC_REVIEW",
                             "Revisión técnica periódica"),
                            ("REPAIR", "Pieza sustituida o reparación"),
                            ("ACCIDENT", "Accidente"),
                            ("NOTE", "Nota"),
                            ("OWNERSHIP", "Cambio de titularidad"),
                        ],
                        max_length=25, verbose_name="Sección",
                    ),
                ),
                (
                    "entry_date",
                    models.DateField(
                        blank=True, null=True, verbose_name="Fecha",
                    ),
                ),
                (
                    "entry_type",
                    models.CharField(
                        blank=True, default="", max_length=120,
                        verbose_name="Tipo",
                    ),
                ),
                (
                    "concept",
                    models.TextField(
                        blank=True, default="", verbose_name="Concepto",
                    ),
                ),
                (
                    "entity",
                    models.CharField(
                        blank=True, default="", max_length=200,
                        verbose_name="Entidad o empresa",
                    ),
                ),
                (
                    "result",
                    models.CharField(
                        blank=True, default="", max_length=200,
                        verbose_name="Resultado",
                    ),
                ),
                (
                    "next_date",
                    models.DateField(
                        blank=True, null=True,
                        verbose_name="Próxima revisión",
                    ),
                ),
                (
                    "machine",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logbook_entries",
                        to="fleet.machineasset",
                        verbose_name="Centro de gasto",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="fleet.machinelogbooksource",
                        verbose_name="Documento de origen",
                    ),
                ),
            ],
            options={
                "verbose_name": "Fila del libro historial",
                "verbose_name_plural": "Filas del libro historial",
                "ordering": ["machine", "section", "entry_date", "id"],
            },
        ),
    ]
