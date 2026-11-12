# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0037_payslipbatchshare_s153.py
# S153 (H24, nóminas): `PayslipBatchShare` -- a quién da acceso a una
# entrega de nóminas quien la sube (ver, descargar, visto bueno y envío).
# Solo esquema, ninguna fila. La copia cifrada de cada PDF subido ya no
# se borra al enviar (solo cambia su nombre visible).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0036_workerclocksetting_clock_mode_s148"),
        ("ivr_config", "0058_companyuser_payslip_full_access_s153"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payslipitem",
            name="staged_path",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Copia cifrada del PDF subido",
            ),
        ),
        migrations.CreateModel(
            name="PayslipBatchShare",
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
                    "granted_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Compartida",
                    ),
                ),
                (
                    "notified_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Avisado",
                    ),
                ),
                (
                    "notify_error",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="Error del aviso",
                    ),
                ),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shares",
                        to="hr_calendar.payslipbatch",
                        verbose_name="Entrega",
                    ),
                ),
                (
                    "company_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payslip_batch_shares",
                        to="ivr_config.companyuser",
                        verbose_name="Usuario",
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="ivr_config.companyuser",
                        verbose_name="Compartida por",
                    ),
                ),
            ],
            options={
                "verbose_name": "Acceso a una entrega de nóminas",
                "verbose_name_plural": "Accesos a las entregas de nóminas",
                "ordering": ["pk"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("batch", "company_user"),
                        name="unique_payslip_share_per_user",
                    )
                ],
            },
        ),
    ]
