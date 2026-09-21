# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0124_grualdi_fiscal_profile_y_fix_alias_transgrual_s113.py
"""
H31 (S113). Corrección real tras confirmación explícita de Miguel
Ángel: GRUALDI S.L. NO es una variante de texto sin resolver -- es
la 4ª empresa real del grupo, ya reconocida como tal en el propio
filtro "Empresa" del panel (`COMPANY_FILTER_CHOICES`,
`panel/views_documentation_h30.py`, decisión de S76). Esa constante
ya tenía la agrupación correcta y se me pasó por alto al construir
`CompanyFiscalProfile` en la migración 0123 -- esta migración la
alinea:

1. Añade el perfil fiscal que faltaba, GRUALDI S.L. -- CIF B29739059
   (verificado contra registro mercantil público, Axesor), dirección
   C/ Diseminado de Cantos, 12, Málaga (misma zona real que el resto
   del grupo). Miguel Ángel, verbatim: "esas son las empresas que hay
   y ya está. Ya no tenemos más empresas."
2. Corrige `name_aliases` de Transgrual para incluir "TRANSGRUAL Y
   ASITENCIA" -- ya agrupada con Transgrual en
   `COMPANY_FILTER_CHOICES` desde S76 ("TRANSGRUAL S.L." (con puntos)
   y "TRANSGRUAL Y ASITENCIA" son variantes de escritura de la misma
   empresa"), pero la migración 0123 no la incluyó.
"""
from django.db import migrations


def fix_company_fiscal_profiles(apps, schema_editor):
    CompanyFiscalProfile = apps.get_model(
        "document_explorer", "CompanyFiscalProfile",
    )
    address = "C/ Ronda del Norte, 12, Santa Rosalía, 29591 Málaga"
    transgrual = CompanyFiscalProfile.objects.get(tax_id="B92493022")
    transgrual.name_aliases = (
        "TRANSGRUAL SL\nTRANSGRUAL S.L.\nTRANSGRUAL Y ASITENCIA"
    )
    transgrual.save(update_fields=["name_aliases"])

    CompanyFiscalProfile.objects.create(
        legal_name="Grualdi, S.L.",
        tax_id="B29739059",
        fiscal_address="C/ Diseminado de Cantos, 12, Málaga",
        name_aliases="GRUALDI S.L",
    )


def unfix_company_fiscal_profiles(apps, schema_editor):
    CompanyFiscalProfile = apps.get_model(
        "document_explorer", "CompanyFiscalProfile",
    )
    CompanyFiscalProfile.objects.filter(tax_id="B29739059").delete()
    transgrual = CompanyFiscalProfile.objects.filter(
        tax_id="B92493022",
    ).first()
    if transgrual is not None:
        transgrual.name_aliases = "TRANSGRUAL SL\nTRANSGRUAL S.L."
        transgrual.save(update_fields=["name_aliases"])


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0123_companyfiscalprofile_epideliverybatchtemplate_s113"),
    ]

    operations = [
        migrations.RunPython(
            fix_company_fiscal_profiles, unfix_company_fiscal_profiles,
        ),
    ]
