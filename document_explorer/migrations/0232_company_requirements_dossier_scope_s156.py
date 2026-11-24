# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0232_company_requirements_dossier_scope_s156.py
"""
S156 (CAE). Requisitos de documentación asignables a cada empresa del
grupo (CompanyFiscalProfile.document_requirements) y ámbito «Empresa»
en las plantillas de dosier.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0231_seed_cae_company_types_s156"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyfiscalprofile",
            name="document_requirements",
            field=models.ManyToManyField(
                blank=True,
                related_name="companies",
                to="document_explorer.jobposition",
                verbose_name="Requisitos de documentación",
            ),
        ),
        migrations.AlterField(
            model_name="personaldossiertemplate",
            name="scope",
            field=models.CharField(
                choices=[
                    ("PERSONAL", "Personal"),
                    ("MACHINE", "Maquinaria"),
                    ("COMPANY", "Empresa"),
                ],
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
