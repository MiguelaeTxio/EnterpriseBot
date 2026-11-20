# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0045_qr_editor_settings_s154.py
"""
H23 (S154, invasora) -- contraseña del editor de fichas QR dentro de la
aplicación de fichaje (una por empresa, cifrada).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0044_machine_qr_sheet_s154"),
        ("ivr_config", "0056_workdayscheduleday_holiday_s144"),
    ]

    operations = [
        migrations.CreateModel(
            name="QrEditorSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True,
                                           primary_key=True,
                                           serialize=False,
                                           verbose_name="ID")),
                ("password_hash", models.CharField(
                    blank=True, default="", max_length=256,
                    verbose_name="Contraseña (cifrada)")),
                ("updated_at", models.DateTimeField(
                    auto_now=True, verbose_name="Cambiada el")),
                ("company", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="qr_editor_settings",
                    to="ivr_config.company", verbose_name="Empresa")),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="ivr_config.companyuser",
                    verbose_name="Cambiada por")),
            ],
            options={
                "verbose_name": "Acceso al editor de fichas QR",
                "verbose_name_plural": "Acceso al editor de fichas QR",
            },
        ),
    ]
