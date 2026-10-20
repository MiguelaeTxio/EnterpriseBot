# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0032_workorderassistanceunit_notify_sending_s132.py
"""
H37 (S132). "Enviando aviso" status for a unit.

---

H37 (S132). Estado NOTIFY_SENDING ("Enviando aviso"): el aviso por
WhatsApp está aceptado por Twilio pero su entrega aún no está
confirmada. NOTIFIED pasa a significar entrega confirmada.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0031_workorderassistanceunit_notify_status_s132"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workorderassistanceunit",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pendiente"),
                    ("NOTIFY_SENDING", "Enviando aviso"),
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
                    'PENDING: unidad creada, pendiente de notificar al '
                    'operario. NOTIFY_SENDING: aviso aceptado por Twilio,'
                    ' entrega sin confirmar. NOTIFIED: WhatsApp confirma '
                    'la entrega del aviso al operario. NOTIFY_FAILED: '
                    'Twilio informa de que el aviso no se entregó. '
                    'DOWNLOADED: operario ha abierto el albarán en la '
                    'app. IN_PROGRESS: operario en servicio activo. '
                    'COMPLETED: albarán recibido en plataforma con firma.'
                    ' CLOSED_UNSIGNED: albarán recibido sin firma — '
                    'pendiente de gestión. SIGNED_RECEIVED: supervisor '
                    'confirma firma recibida del cliente.'
                ),
                max_length=20,
                verbose_name="Estado",
            ),
        ),
    ]
