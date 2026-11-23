# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0051_clockattempt_s149.py
# H24 (S149, sesión invasora): intentos de fichar que el móvil no guardó,
# con el motivo (Antonio Fontalba, 20/11).
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0063_role_services_s149"),
        ("hr_calendar", "0050_clockevent_worker_note_s149"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClockAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("client_id", models.CharField(max_length=64, unique=True, verbose_name="Id del móvil")),
                ("attempted_at", models.DateTimeField(verbose_name="Pulsado (móvil)")),
                ("received_at", models.DateTimeField(auto_now_add=True, verbose_name="Recibido")),
                ("reason", models.CharField(choices=[("TOO_SOON", "Menos de 2 minutos desde el anterior"), ("NO_GPS", "Sin permiso de ubicación"), ("CANCELLED", "Pulsó y dijo «No» en la confirmación"), ("SAVE_ERROR", "No se pudo guardar en el móvil"), ("REJECTED", "El servidor no lo admitió")], max_length=12, verbose_name="Motivo")),
                ("kind", models.CharField(blank=True, default="", max_length=4, verbose_name="Lo que iba a fichar")),
                ("message", models.CharField(blank=True, default="", max_length=500, verbose_name="Mensaje que vio")),
                ("screen", models.CharField(blank=True, default="", max_length=500, verbose_name="Lo que tenía en pantalla")),
                ("user_agent", models.CharField(blank=True, default="", max_length=255, verbose_name="Navegador")),
                ("company_user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="clock_attempts", to="ivr_config.companyuser", verbose_name="Trabajador")),
            ],
            options={
                "verbose_name": "Intento de fichar no guardado",
                "verbose_name_plural": "Intentos de fichar no guardados",
                "indexes": [models.Index(fields=["company_user", "attempted_at"], name="clockattempt_user_at")],
            },
        ),
    ]
