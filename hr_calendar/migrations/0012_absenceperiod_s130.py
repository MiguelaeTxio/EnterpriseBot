# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0012_absenceperiod_s130.py
# H24 (S130): ausencias que no son vacaciones ni baja (punto 4 de la
# hoja de ruta 7.5 del anexo V24).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0186_personalexporttemplate_s129"),
        ("hr_calendar", "0011_clockevent_sent_by_manual_s130"),
        ("ivr_config", "0047_trusteddevice_s129"),
    ]

    operations = [
        migrations.CreateModel(
            name="AbsencePeriod",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "date_start",
                    models.DateField(
                        help_text="Primer día de la ausencia (inclusive).",
                        verbose_name="Desde",
                    ),
                ),
                (
                    "date_end",
                    models.DateField(
                        help_text="Último día de la ausencia (inclusive).",
                        verbose_name="Hasta",
                    ),
                ),
                (
                    "note",
                    models.TextField(
                        blank=True,
                        help_text="Obligatoria si el tipo de ausencia la "
                                  "exige.",
                        verbose_name="Nota",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Fecha de registro",
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="absence_periods",
                        to="ivr_config.absencecategory",
                        verbose_name="Tipo de ausencia",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="absence_periods",
                        to="ivr_config.company",
                        verbose_name="Empresa",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="absence_periods_created",
                        to="ivr_config.companyuser",
                        verbose_name="Registrada por",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="absence_periods",
                        to="document_explorer.personidentity",
                        verbose_name="Trabajador",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ausencia",
                "verbose_name_plural": "Ausencias",
                "ordering": ["-date_start"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("date_end__gte", models.F("date_start")),
                        ),
                        name="absenceperiod_date_end_gte_date_start",
                    ),
                ],
            },
        ),
    ]
