# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0099_personaldossiertemplate_epi_items_s109.py
"""
H31/H36 (S109). Anade `PersonalDossierTemplate.epi_items` (M2M a
EpiItemCatalog, blank=True) -- ver docstring completo del campo en
models.py. Decision explicita de Miguel Angel: diseno de la plantilla
y del documento final SIN firma todavia (el pipeline de firma
electronica cualificada esta en fase de eleccion de proveedor,
fuera de alcance de esta migracion).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0098_seed_cuestionario_pacto_justificante_s109"),
    ]

    operations = [
        migrations.AddField(
            model_name="personaldossiertemplate",
            name="epi_items",
            field=models.ManyToManyField(
                blank=True,
                related_name="dossier_templates",
                to="document_explorer.epiitemcatalog",
                verbose_name="EPIs incluidos",
            ),
        ),
    ]
