# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0035_unit_closed_base_s133.py
"""
H37 (S133). Base closing of an albarán (dossier phase 4).

---

H37 (S133). Cierre en base del albarán (fase 4 del dossier): estado
CLOSED_BASE, km finales, repostaje y hora del cierre.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0034_driverdevicetoken_s133"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="base_closed_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Cerrado en base en"
            ),
        ),
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="base_km_end",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                help_text="Cuentakilómetros de la máquina al llegar a base.",
                max_digits=10,
                null=True,
                verbose_name="Km finales",
            ),
        ),
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="refuel_liters",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=7,
                null=True,
                verbose_name="Litros repostados",
            ),
        ),
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="refueled",
            field=models.BooleanField(
                blank=True,
                help_text=(
                    "Si el conductor repostó en el servicio. Vacío hasta el "
                    "cierre en base."
                ),
                null=True,
                verbose_name="Ha repostado",
            ),
        ),
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
                    ("CLOSED_BASE", "Cerrado en base"),
                ],
                default="PENDING",
                help_text=(
                    "PENDING: unidad creada, pendiente de notificar al "
                    "operario. NOTIFY_SENDING: aviso aceptado por Twilio, "
                    "entrega sin confirmar. NOTIFIED: WhatsApp confirma la "
                    "entrega del aviso al operario. NOTIFY_FAILED: Twilio "
                    "informa de que el aviso no se entregó. DOWNLOADED: "
                    "operario ha abierto el albarán en la app. IN_PROGRESS: "
                    "operario en servicio activo. COMPLETED: albarán recibido "
                    "en plataforma con firma. CLOSED_UNSIGNED: albarán "
                    "recibido sin firma — pendiente de gestión. "
                    "SIGNED_RECEIVED: supervisor confirma firma recibida del "
                    "cliente. CLOSED_BASE: el conductor cierra en base con km "
                    "finales y repostaje; conductor y máquina quedan libres."
                ),
                max_length=20,
                verbose_name="Estado",
            ),
        ),
    ]
