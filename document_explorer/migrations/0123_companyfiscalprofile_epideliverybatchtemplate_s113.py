# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0123_companyfiscalprofile_epideliverybatchtemplate_s113.py
"""
H31 (S113). Dos tablas nuevas:

- CompanyFiscalProfile: CIF/dirección fiscal reales por razón social
  del grupo, para el encabezado del documento de entrega de EPIs.
  Sembrado con las 3 empresas reales confirmadas por Miguel Ángel en
  esta sesión (CIF ya existente en `spare_parts.services.
  _RECIPIENT_TAX_ID_TO_COMPANY_CODE`, dirección fiscal confirmada
  explícitamente por Miguel Ángel -- las tres en C/ Ronda del Norte,
  12, Santa Rosalía, 29591 Málaga). `name_aliases` cubre las
  variantes reales de `PersonIdentity.employer_company` encontradas
  por consulta SQL en esta misma sesión. Dos variantes reales
  quedan SIN cubrir a propósito (2 personas con "GRUALDI S.L", 1 con
  "TRANSGRUAL Y ASITENCIA") -- Miguel Ángel no ha confirmado a qué
  empresa real corresponden; sus documentos de entrega saldrán sin
  encabezado de empresa hasta que se aclare, nunca con un dato
  inventado.

- EpiDeliveryBatchTemplate: lote de EPIs reutilizable, nombre libre
  puesto por el supervisor (M2M a EpiItemCatalog).

Ninguna fila de EpiDeliveryBatchTemplate se siembra aquí -- el
supervisor crea sus propios lotes desde el panel.
"""
from django.db import migrations, models


def seed_company_fiscal_profiles(apps, schema_editor):
    CompanyFiscalProfile = apps.get_model(
        "document_explorer", "CompanyFiscalProfile",
    )
    address = "C/ Ronda del Norte, 12, Santa Rosalía, 29591 Málaga"
    CompanyFiscalProfile.objects.create(
        legal_name="Gruas Adolfo Alvarez, S.L.",
        tax_id="B29405040",
        fiscal_address=address,
        name_aliases="GRUAS ADOLFO ALVAREZ SL",
    )
    CompanyFiscalProfile.objects.create(
        legal_name="Transgrual, S.L.",
        tax_id="B92493022",
        fiscal_address=address,
        name_aliases="TRANSGRUAL SL\nTRANSGRUAL S.L.",
    )
    CompanyFiscalProfile.objects.create(
        legal_name="Asistencia y Gruas Granada, S.L.",
        tax_id="B93261824",
        fiscal_address=address,
        name_aliases=(
            "ASIST.GRUAS GRANADA\n"
            "ASISTENCIA Y GRUAS GRANADA SL\n"
            "ASISTENCIA Y GRUAS GRANADA S.L."
        ),
    )


def unseed_company_fiscal_profiles(apps, schema_editor):
    CompanyFiscalProfile = apps.get_model(
        "document_explorer", "CompanyFiscalProfile",
    )
    CompanyFiscalProfile.objects.filter(
        tax_id__in=["B29405040", "B92493022", "B93261824"],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0122_alter_personidentity_ss_affiliation_number_s113"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyFiscalProfile",
            fields=[
                ("id", models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name="ID",
                )),
                ("legal_name", models.CharField(
                    max_length=200, verbose_name="Razón social",
                )),
                ("tax_id", models.CharField(
                    max_length=20, verbose_name="CIF",
                )),
                ("fiscal_address", models.CharField(
                    blank=True, max_length=300,
                    verbose_name="Dirección fiscal",
                )),
                ("name_aliases", models.TextField(
                    blank=True,
                    verbose_name="Variantes de texto (una por línea)",
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Perfil fiscal de empresa",
                "verbose_name_plural": "Perfiles fiscales de empresa",
                "ordering": ["legal_name"],
            },
        ),
        migrations.CreateModel(
            name="EpiDeliveryBatchTemplate",
            fields=[
                ("id", models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name="ID",
                )),
                ("name", models.CharField(
                    max_length=150, unique=True,
                    verbose_name="Nombre del lote",
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("items", models.ManyToManyField(
                    related_name="batch_templates",
                    to="document_explorer.epiitemcatalog",
                    verbose_name="EPIs del lote",
                )),
            ],
            options={
                "verbose_name": "Plantilla de lote de EPIs",
                "verbose_name_plural": "Plantillas de lote de EPIs",
                "ordering": ["name"],
            },
        ),
        migrations.RunPython(
            seed_company_fiscal_profiles, unseed_company_fiscal_profiles,
        ),
    ]
