# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0052_workday_schedule_days_s141.py
# H24 (S141): horario de jornada distinto según el día de la semana.

import django.db.models.deletion
from django.db import migrations, models

WEEKDAY_CHOICES = [
    (0, "Lunes"),
    (1, "Martes"),
    (2, "Miércoles"),
    (3, "Jueves"),
    (4, "Viernes"),
    (5, "Sábado"),
    (6, "Domingo"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0051_role_admin_supervisor_s141"),
    ]

    operations = [
        migrations.AddField(
            model_name="workdayschedule",
            name="varies_by_day",
            field=models.BooleanField(
                default=False,
                help_text="Si está activo, cada día de la semana (lunes a "
                          "domingo) tiene su propio horario de mañana y "
                          "tarde.",
                verbose_name="Horario distinto según el día",
            ),
        ),
        migrations.CreateModel(
            name="WorkdayScheduleDay",
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
                    "weekday",
                    models.PositiveSmallIntegerField(
                        choices=WEEKDAY_CHOICES,
                        verbose_name="Día de la semana",
                    ),
                ),
                (
                    "works",
                    models.BooleanField(
                        default=True, verbose_name="Se trabaja",
                    ),
                ),
                (
                    "start_time_morning",
                    models.TimeField(
                        blank=True, null=True, verbose_name="Entrada mañana",
                    ),
                ),
                (
                    "end_time_morning",
                    models.TimeField(
                        blank=True, null=True, verbose_name="Salida mañana",
                    ),
                ),
                (
                    "start_time_afternoon",
                    models.TimeField(
                        blank=True, null=True, verbose_name="Entrada tarde",
                    ),
                ),
                (
                    "end_time_afternoon",
                    models.TimeField(
                        blank=True, null=True, verbose_name="Salida tarde",
                    ),
                ),
                (
                    "schedule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="days",
                        to="ivr_config.workdayschedule",
                        verbose_name="Horario",
                    ),
                ),
            ],
            options={
                "verbose_name": "Día de horario de jornada",
                "verbose_name_plural": "Días de horario de jornada",
                "ordering": ["schedule", "weekday"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("schedule", "weekday"),
                        name="workdayscheduleday_unique_schedule_weekday",
                    ),
                ],
            },
        ),
    ]
