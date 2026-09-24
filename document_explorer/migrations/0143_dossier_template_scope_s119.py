# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0143_dossier_template_scope_s119.py
"""
H30 (S119), punto 6. Añade `PersonalDossierTemplate.scope` (PERSONAL /
MACHINE) para ofrecer plantillas de dossier también en la ficha de
máquina con el mismo mecanismo que Personal. `default="PERSONAL"`: todas
las plantillas ya existentes son de Personal y siguen igual.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0142_tipo_cert_propiedad_s118"),
    ]

    operations = [
        migrations.AddField(
            model_name="personaldossiertemplate",
            name="scope",
            field=models.CharField(
                choices=[("PERSONAL", "Personal"), ("MACHINE", "Maquinaria")],
                default="PERSONAL",
                help_text=(
                    "Personal o Maquinaria: en qué fichas se ofrece la "
                    "plantilla y qué tipos documentales puede incluir."
                ),
                max_length=10,
                verbose_name="Ámbito",
            ),
        ),
    ]
