# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0014_clockcorrection_s141.py
# H24 (S141): los fichajes no se modifican ni se borran; se corrigen con
# ClockCorrection (quién, cuándo, valor anterior y nuevo, motivo), que
# conserva el original. Nuevo origen CORRECTION en ClockEvent.sent_by.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0013_clockreminder_s141"),
        ("ivr_config", "0050_role_crane_operator_s137"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clockevent",
            name="sent_by",
            field=models.CharField(
                choices=[
                    ("ONLINE", "Al momento"),
                    ("BACKGROUND", "Al volver la cobertura (segundo plano)"),
                    ("PAGE", "Desde la página (al abrirla o con su botón)"),
                    ("MANUAL", "Fichaje manual (olvido)"),
                    ("CORRECTION", "Corrección del supervisor"),
                ],
                default="ONLINE",
                max_length=12,
                verbose_name="Cómo se envió",
            ),
        ),
        migrations.CreateModel(
            name="ClockCorrection",
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
                    "action",
                    models.CharField(
                        choices=[
                            ("CHANGE", "Cambio de hora o de tipo"),
                            ("CANCEL", "Anulación"),
                        ],
                        max_length=6,
                        verbose_name="Corrección",
                    ),
                ),
                (
                    "old_kind",
                    models.CharField(
                        choices=[("IN", "Entrada"), ("OUT", "Salida")],
                        max_length=3,
                        verbose_name="Tipo anterior",
                    ),
                ),
                (
                    "old_pressed_at",
                    models.DateTimeField(verbose_name="Hora anterior"),
                ),
                (
                    "new_kind",
                    models.CharField(
                        blank=True,
                        choices=[("IN", "Entrada"), ("OUT", "Salida")],
                        max_length=3,
                        verbose_name="Tipo nuevo",
                    ),
                ),
                (
                    "new_pressed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Hora nueva",
                    ),
                ),
                ("reason", models.TextField(verbose_name="Motivo")),
                (
                    "corrected_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Fecha de la corrección",
                    ),
                ),
                (
                    "user_agent",
                    models.CharField(
                        blank=True, max_length=200, verbose_name="Navegador",
                    ),
                ),
                (
                    "corrected_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="clock_corrections",
                        to="ivr_config.companyuser",
                        verbose_name="Corregido por",
                    ),
                ),
                (
                    "event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="correction",
                        to="hr_calendar.clockevent",
                        verbose_name="Fichaje corregido",
                    ),
                ),
                (
                    "replacement",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="replaces",
                        to="hr_calendar.clockevent",
                        verbose_name="Fichaje que lo sustituye",
                    ),
                ),
            ],
            options={
                "verbose_name": "Corrección de fichaje",
                "verbose_name_plural": "Correcciones de fichaje",
                "ordering": ["-corrected_at"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("reason", ""), _negated=True),
                        name="clockcorrection_reason_required",
                    ),
                ],
            },
        ),
    ]
