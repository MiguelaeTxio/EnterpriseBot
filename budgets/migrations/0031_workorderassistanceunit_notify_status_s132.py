# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0031_workorderassistanceunit_notify_status_s132.py
"""
H37 (S132). Delivery status of the WhatsApp notice of a unit.

---

H37 (S132). Estado de entrega del aviso por WhatsApp de una unidad:
nuevo estado NOTIFY_FAILED ("Aviso fallido") y los campos
notify_message_sid y notify_error.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0030_budget_manual_toll_segments_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="notify_message_sid",
            field=models.CharField(
                blank=True,
                default="",
                help_text="SID de Twilio del último aviso por WhatsApp.",
                max_length=64,
                verbose_name="SID del aviso",
            ),
        ),
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="notify_error",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Motivo por el que el último aviso no se entregó.",
                max_length=255,
                verbose_name="Error del aviso",
            ),
        ),
        migrations.AlterField(
            model_name="workorderassistanceunit",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pendiente"),
                    ("NOTIFIED", "Notificado"),
                    ("NOTIFY_FAILED", "Aviso fallido"),
                    ("DOWNLOADED", "Descargado"),
                    ("IN_PROGRESS", "En curso"),
                    ("COMPLETED", "Completado"),
                    ("CLOSED_UNSIGNED", "Cerrado sin firma"),
                    ("SIGNED_RECEIVED", "Firma recibida"),
                ],
                default="PENDING",
                help_text=(
                    "PENDING: unidad creada, pendiente de notificar al "
                    "operario. NOTIFIED: template WhatsApp enviado al "
                    "operario. NOTIFY_FAILED: Twilio informa de que el "
                    "aviso no se entregó. DOWNLOADED: operario ha abierto "
                    "el albarán en la app. IN_PROGRESS: operario en "
                    "servicio activo. COMPLETED: albarán recibido en "
                    "plataforma con firma. CLOSED_UNSIGNED: albarán "
                    "recibido sin firma — pendiente de gestión. "
                    "SIGNED_RECEIVED: supervisor confirma firma recibida "
                    "del cliente."
                ),
                max_length=20,
                verbose_name="Estado",
            ),
        ),
    ]
