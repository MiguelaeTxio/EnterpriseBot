# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/worksites/migrations/0002_worksite_code_help_text_s115.py
"""
H31 (S115). Solo actualiza el help_text de Worksite.code tras
quitarlo del formulario de alta -- pasa a autogenerarse (formato
OBRA-0001) en vez de introducirse a mano, a petición explícita de
Miguel Ángel ("no un código generado al tuntún por el usuario de
turno"). Sin efecto real en el esquema de BD.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("worksites", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="worksite",
            name="code",
            field=models.CharField(
                blank=True, default="", max_length=50,
                verbose_name="Código interno",
            ),
        ),
    ]
