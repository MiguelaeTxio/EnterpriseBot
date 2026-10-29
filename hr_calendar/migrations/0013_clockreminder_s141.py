# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0013_clockreminder_s141.py
# H24 (S141): recordatorios por WhatsApp de fichajes olvidados (entrada
# y salida).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0012_absenceperiod_s130"),
        ("ivr_config", "0050_role_crane_operator_s137"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClockReminder",
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
                ("day", models.DateField(verbose_name="Día")),
                (
                    "kind",
                    models.CharField(
                        choices=[("IN", "Entrada"), ("OUT", "Salida")],
                        max_length=3,
                        verbose_name="Fichaje que falta",
                    ),
                ),
                (
                    "scheduled_time",
                    models.TimeField(
                        help_text="Hora de entrada o de salida del "
                                  "horario del trabajador ese día.",
                        verbose_name="Hora del horario",
                    ),
                ),
                (
                    "phone",
                    models.CharField(max_length=20, verbose_name="Móvil"),
                ),
                (
                    "message_sid",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="Mensaje de Twilio",
                    ),
                ),
                (
                    "sent_as_text",
                    models.BooleanField(
                        default=False,
                        help_text="Dentro de la ventana de 24 horas sale "
                                  "como texto libre; fuera, con la "
                                  "plantilla.",
                        verbose_name="Enviado como texto",
                    ),
                ),
                (
                    "sent_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Enviado",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clock_reminders",
                        to="ivr_config.company",
                        verbose_name="Empresa",
                    ),
                ),
                (
                    "company_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clock_reminders",
                        to="ivr_config.companyuser",
                        verbose_name="Trabajador",
                    ),
                ),
            ],
            options={
                "verbose_name": "Recordatorio de fichaje",
                "verbose_name_plural": "Recordatorios de fichaje",
                "ordering": ["-sent_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("company_user", "day", "kind"),
                        name="clockreminder_unique_user_day_kind",
                    ),
                ],
            },
        ),
    ]
