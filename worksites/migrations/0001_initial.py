# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/worksites/migrations/0001_initial.py
"""
H31 (S115). Migración inicial de la app worksites -- ver
worksites/models.py y la deuda técnica 4.23 del documento maestro.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("ivr_config", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Worksite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Nombre de la obra")),
                ("code", models.CharField(blank=True, default="", max_length=50, verbose_name="Código interno")),
                ("client_name", models.CharField(blank=True, default="", max_length=200, verbose_name="Cliente (texto libre)")),
                ("address", models.CharField(blank=True, default="", max_length=300, verbose_name="Ubicación")),
                ("is_active", models.BooleanField(default=True, verbose_name="Activa")),
                ("notes", models.TextField(blank=True, default="", verbose_name="Notas")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Fecha de modificación")),
                ("managing_company", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="worksites",
                    to="ivr_config.company",
                    verbose_name="Empresa del grupo que gestiona la obra",
                )),
            ],
            options={
                "verbose_name": "Obra",
                "verbose_name_plural": "Obras",
                "ordering": ["name"],
            },
        ),
    ]
