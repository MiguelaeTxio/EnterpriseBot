# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0034_driverdevicetoken_s133.py
"""
H37 (S133). Device tokens of the driver app.

---

H37 (S133). Tokens de dispositivo de la app del conductor
(EBotDeliveryNotes).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0033_workorderassistanceunit_traffic_s133"),
        ("ivr_config", "0049_companyuser_role_assist_supervisor_s132"),
    ]

    operations = [
        migrations.CreateModel(
            name="DriverDeviceToken",
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
                    "key_hash",
                    models.CharField(
                        help_text=(
                            "SHA-256 del token; el token en claro no se "
                            "guarda."
                        ),
                        max_length=64,
                        unique=True,
                        verbose_name="Huella del token",
                    ),
                ),
                (
                    "device_name",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=120,
                        verbose_name="Dispositivo",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Creado",
                    ),
                ),
                (
                    "last_used_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Último uso",
                    ),
                ),
                (
                    "revoked_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Vacío mientras el token es válido.",
                        null=True,
                        verbose_name="Revocado",
                    ),
                ),
                (
                    "company_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="driver_device_tokens",
                        to="ivr_config.companyuser",
                        verbose_name="Usuario",
                    ),
                ),
            ],
            options={
                "verbose_name": "Token de la app del conductor",
                "verbose_name_plural": "Tokens de la app del conductor",
                "ordering": ["-created_at"],
            },
        ),
    ]
