# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0080_personidentity_ss_affiliation_number_s100.py
"""
H31 (S100). Número de afiliación a la Seguridad Social -- Miguel
Ángel, verbatim: "hay datos que sí son necesarios para la empresa,
para el supervisor y sin embargo no los ponemos ahí [...] el número
de afiliación a la Seguridad Social [...] siendo, como es, un dato
bastante importante." Ya aparece impreso en el ALTA (Seguridad Social)
y en el IDC ("número de afiliación"/"NSS") -- se guarda tal cual
aparece, sin normalizar un formato que Miguel Ángel no ha pedido.
Blank por defecto -- sin backfill retroactivo, mismo criterio que
0063/0067.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0079_seed_document_tags_machine_company_epi_s98"),
    ]

    operations = [
        migrations.AddField(
            model_name="personidentity",
            name="ss_affiliation_number",
            field=models.CharField(
                max_length=32, blank=True,
                verbose_name="Número de afiliación a la Seguridad Social",
                help_text=(
                    "H31 (S100). Tal cual aparece en el documento real "
                    "(ALTA, IDC) -- nunca normalizado a un formato "
                    "inventado aquí."
                ),
            ),
        ),
    ]
