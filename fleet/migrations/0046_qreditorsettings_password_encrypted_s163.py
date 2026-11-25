# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0046_qreditorsettings_password_encrypted_s163.py
"""
S163 (invasora, H31) -- la contraseña del editor de fichas QR también
cifrada de forma recuperable, para verla en la nueva interfaz.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0045_qr_editor_settings_s154"),
    ]

    operations = [
        migrations.AddField(
            model_name="qreditorsettings",
            name="password_encrypted",
            field=models.TextField(
                blank=True, default="",
                verbose_name="Contraseña (recuperable)"),
        ),
    ]
