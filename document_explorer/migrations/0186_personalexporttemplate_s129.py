# H31 (S129): plantillas de exportación a Excel del listado de Personal.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0185_remove_dossiertemplate_is_active_s128"),
        ("ivr_config", "0047_trusteddevice_s129"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonalExportTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_global", models.BooleanField(default=False, help_text="Visible para todos; solo un ADMIN la crea o edita.", verbose_name="Plantilla global")),
                ("name", models.CharField(max_length=100, verbose_name="Nombre")),
                ("is_default", models.BooleanField(default=False, help_text="La que sale elegida al abrir el modal (una por usuario).", verbose_name="Por defecto")),
                ("columns", models.JSONField(default=list, help_text="Claves de columna, en el orden del Excel.", verbose_name="Columnas")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="personal_export_templates", to="ivr_config.company", verbose_name="Empresa")),
                ("company_user", models.ForeignKey(blank=True, help_text="Dueño de la plantilla personal; vacío en las globales.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="personal_export_templates", to="ivr_config.companyuser", verbose_name="Usuario")),
            ],
            options={
                "verbose_name": "Plantilla de exportación de personal",
                "verbose_name_plural": "Plantillas de exportación de personal",
                "ordering": ["-is_global", "-is_default", "name"],
            },
        ),
    ]
