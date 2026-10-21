# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0039_origin_queue_s133.py
"""
H37 (S133). Origin of the service and queued albaranes.

---

H37 (S133). Origen del servicio (panel, foto, WhatsApp, llamada) y
albaranes en cola. Las órdenes que ya existen quedan con origen
"Panel" (default), las unidades sin cola.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0038_unit_helpers_s133"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorderassistance",
            name="origin",
            field=models.CharField(
                choices=[
                    ("PANEL", "Panel (a mano)"),
                    ("PHOTO", "Foto (TIREA u otra plataforma)"),
                    ("WHATSAPP", "WhatsApp"),
                    ("PHONE", "Llamada"),
                ],
                default="PANEL",
                help_text="Por dónde entró el servicio.",
                max_length=10,
                verbose_name="Origen",
            ),
        ),
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="queued_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Se envía solo cuando el conductor termina el servicio "
                    "anterior."
                ),
                null=True,
                verbose_name="En cola desde",
            ),
        ),
    ]
