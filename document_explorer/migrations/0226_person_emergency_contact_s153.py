# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0226_person_emergency_contact_s153.py
"""
S153: contacto y teléfono de emergencia en la ficha de personal.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0225_signedform_waiting_s156"),
    ]

    operations = [
        migrations.AddField(
            model_name="personidentity",
            name="emergency_contact",
            field=models.CharField(
                blank=True, help_text="A quién llamar (nombre y parentesco).",
                max_length=120, verbose_name="Contacto de emergencia"),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="phone_emergency",
            field=models.CharField(blank=True, max_length=30,
                                   verbose_name="Teléfono de emergencia"),
        ),
    ]
