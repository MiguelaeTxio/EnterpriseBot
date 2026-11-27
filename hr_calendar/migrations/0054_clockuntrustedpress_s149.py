# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0054_clockuntrustedpress_s149.py
# H24 (S149, sesión invasora): fichajes enviados desde móviles que no son
# de confianza, con ubicación, llave que traían y 4 últimos números del DNI.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0235_caedocumentreading_s156"),
        ("ivr_config", "0063_role_services_s149"),
        ("hr_calendar", "0053_pay_s163"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClockUntrustedPress",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name="ID")),
                ("client_id", models.CharField(
                    max_length=64, unique=True, verbose_name="Id del móvil")),
                ("first_seen", models.DateTimeField(
                    auto_now_add=True, verbose_name="Primer envío")),
                ("last_seen", models.DateTimeField(
                    auto_now=True, verbose_name="Último envío")),
                ("tries", models.PositiveIntegerField(
                    default=1, verbose_name="Envíos")),
                ("pressed_at", models.DateTimeField(
                    blank=True, null=True, verbose_name="Pulsado (móvil)")),
                ("kind", models.CharField(
                    blank=True, default="", max_length=4,
                    verbose_name="Tipo")),
                ("latitude", models.DecimalField(
                    blank=True, decimal_places=6, max_digits=9, null=True,
                    verbose_name="Latitud")),
                ("longitude", models.DecimalField(
                    blank=True, decimal_places=6, max_digits=9, null=True,
                    verbose_name="Longitud")),
                ("accuracy_m", models.PositiveIntegerField(
                    blank=True, null=True, verbose_name="Precisión (m)")),
                ("ip", models.CharField(
                    blank=True, default="", max_length=45,
                    verbose_name="Conexión")),
                ("user_agent", models.CharField(
                    blank=True, default="", max_length=255,
                    verbose_name="Navegador")),
                ("key_problem", models.CharField(
                    blank=True, default="", max_length=60,
                    verbose_name="Qué le pasa a la llave")),
                ("dni4", models.CharField(
                    blank=True, default="", max_length=4,
                    verbose_name="4 últimos números del DNI")),
                ("dni_matches", models.PositiveSmallIntegerField(
                    default=0, verbose_name="Trabajadores con esos números")),
                ("dni_person", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="document_explorer.personidentity",
                    verbose_name="Trabajador por el DNI")),
                ("key_user", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="ivr_config.companyuser",
                    verbose_name="Dueño de la llave que traía")),
            ],
            options={
                "verbose_name": "Fichaje desde un móvil sin permiso",
                "verbose_name_plural": "Fichajes desde móviles sin permiso",
                "indexes": [models.Index(
                    fields=["first_seen"],
                    name="clockuntrusted_first_seen")],
            },
        ),
    ]
