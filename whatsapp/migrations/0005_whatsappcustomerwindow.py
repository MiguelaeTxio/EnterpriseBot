# H30 (S127). Ventana de atención de 24 horas de Meta por teléfono.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0002_phonenumber_capabilities"),
        ("whatsapp", "0004_add_pending_broadcast_messages"),
    ]

    operations = [
        migrations.CreateModel(
            name="WhatsAppCustomerWindow",
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
                    "phone_number",
                    models.CharField(
                        help_text="Teléfono del remitente en formato E.164 (+34XXXXXXXXX).",
                        max_length=20,
                        verbose_name="Número de teléfono",
                    ),
                ),
                (
                    "last_inbound_at",
                    models.DateTimeField(
                        help_text="Fecha y hora del último mensaje recibido de este teléfono. La ventana de 24 horas de Meta se cuenta desde aquí.",
                        verbose_name="Último mensaje entrante",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="whatsapp_customer_windows",
                        to="ivr_config.company",
                        verbose_name="Empresa",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ventana de atención de WhatsApp",
                "verbose_name_plural": "Ventanas de atención de WhatsApp",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("company", "phone_number"),
                        name="unique_whatsapp_customer_window",
                    )
                ],
            },
        ),
    ]
