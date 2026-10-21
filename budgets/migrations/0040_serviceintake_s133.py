# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0040_serviceintake_s133.py
"""
H37 (S133). Services given by WhatsApp or by phone.

---

H37 (S133). Altas de servicio por conversación (WhatsApp o llamada).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0039_origin_queue_s133"),
        ("ivr_config", "0049_companyuser_role_assist_supervisor_s132"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceIntake",
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
                    "channel",
                    models.CharField(
                        choices=[
                            ("WHATSAPP", "WhatsApp"),
                            ("PHONE", "Llamada"),
                        ],
                        max_length=10,
                        verbose_name="Canal",
                    ),
                ),
                (
                    "phone_number",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=30,
                        verbose_name="Teléfono",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("OPEN", "En curso"),
                            ("LAUNCHED", "Lanzado"),
                            ("CANCELLED", "Cancelado"),
                        ],
                        default="OPEN",
                        max_length=10,
                        verbose_name="Estado",
                    ),
                ),
                (
                    "data",
                    models.JSONField(
                        blank=True, default=dict,
                        verbose_name="Datos recogidos",
                    ),
                ),
                (
                    "conversation",
                    models.JSONField(
                        blank=True, default=list,
                        verbose_name="Conversación",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Empezado",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Último mensaje",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_intakes",
                        to="ivr_config.company",
                        verbose_name="Empresa",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_intakes",
                        to="ivr_config.companyuser",
                        verbose_name="Quién da el servicio",
                    ),
                ),
                (
                    "work_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="intakes",
                        to="budgets.workorderassistance",
                        verbose_name="Orden creada",
                    ),
                ),
            ],
            options={
                "verbose_name": "Alta de servicio por conversación",
                "verbose_name_plural": "Altas de servicio por conversación",
                "ordering": ["-created_at"],
            },
        ),
    ]
