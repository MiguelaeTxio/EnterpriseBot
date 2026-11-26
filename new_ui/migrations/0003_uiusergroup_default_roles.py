# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/migrations/0003_uiusergroup_default_roles.py
"""
S163 (26/11): perfil de permisos por defecto de cada puesto.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("new_ui", "0002_move_company_views"),
    ]

    operations = [
        migrations.AddField(
            model_name="uiusergroup",
            name="default_roles",
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name="Perfil por defecto de los puestos",
            ),
        ),
    ]
