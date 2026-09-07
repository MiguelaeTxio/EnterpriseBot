# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0070_documenttypecatalog_domain_epi_choice_s95.py
"""
H31 (S95). Auditoria real del campo domain de DocumentTypeCatalog
(Punto 4 de la hoja de ruta) contra el uso real en DocumentIndexEntry.

FICHA_TECNICA_EPI tenia domain=PERSONAL desde su alta
(0056_seed_ficha_tecnica_epi_s73.py), pero sus 7 entradas reales estan
vinculadas al 100% a EpiItemCatalog, nunca a PersonIdentity -- venian
de carpetas de personal por error de origen, confirmado por Miguel
Angel ("Deben quedar asignadas a su EPI"). Ninguno de los 4 valores
existentes (MACHINE/PERSONAL/BOTH/COMPANY) representa "ficha de un
modelo de EPI" -- se anade un valor nuevo al catalogo cerrado en vez
de forzar uno de los existentes.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0069_seed_expediente_disciplinario_s83"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documenttypecatalog",
            name="domain",
            field=models.CharField(
                choices=[
                    ("MACHINE", "Maquinaria"),
                    ("PERSONAL", "Personal"),
                    ("BOTH", "Ambos"),
                    ("COMPANY", "Empresa y obra (CompanyWorksite, H30 S58)"),
                    ("EPI", "EPI (EpiItemCatalog, H31 S95)"),
                ],
                default="BOTH",
                help_text="A qué tipo de entidad aplica este tipo documental.",
                max_length=8,
                verbose_name="Dominio",
            ),
        ),
    ]
