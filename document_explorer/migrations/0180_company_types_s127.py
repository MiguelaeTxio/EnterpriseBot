# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0180_company_types_s127.py
"""
H30 (S127). Tipos de documentación de EMPRESA aprobados por Miguel Ángel
(regla 4 de la revisión de NO CONFORMES: el H28 no tenía dónde archivar
balances, modelos fiscales, escrituras, cuentas, seguros de empresa...).
Dominio COMPANY; la subcarpeta de DOC. EMPRESA de cada tipo vive en
`buckets.COMPANY_TYPE_FOLDERS`.
"""
from django.db import migrations

NEW_TYPES = [
    # (código, etiqueta, familia)
    ("IMPUESTO_SOCIEDADES", "Impuesto sobre Sociedades (modelo 200)",
     "FINANCIERO"),
    ("IVA_TRIMESTRAL", "IVA trimestral (modelo 303)", "FINANCIERO"),
    ("IVA_RESUMEN_ANUAL", "IVA, resumen anual (modelo 390)", "FINANCIERO"),
    ("CUENTAS_ANUALES", "Cuentas anuales / balance y pérdidas y ganancias",
     "FINANCIERO"),
    ("ESCRITURA_SOCIETARIA", "Escritura o acuerdo societario",
     "ADMINISTRATIVO"),
    ("NIF_EMPRESA", "Tarjeta de NIF de la empresa", "ADMINISTRATIVO"),
    ("CERTIFICADO_CUENTA_EMPRESA",
     "Certificado de titularidad de cuenta de la empresa", "FINANCIERO"),
    ("FINANCIACION_EMPRESA",
     "Financiación de la empresa (no ligada a una máquina)", "FINANCIERO"),
    ("POLIZA_SEGURO_EMPRESA", "Póliza de seguro de la empresa", "SEGUROS"),
    ("RECIBO_SEGURO_EMPRESA", "Recibo de seguro de la empresa", "SEGUROS"),
    ("DESCARGA_TACOGRAFOS",
     "Control de descargas de tarjetas de tacógrafo", "ADMINISTRATIVO"),
    ("MATERIAL_FORMACION", "Material o temario de formación",
     "PRL_FORMACION"),
]


def forwards(apps, schema_editor):
    """Crea los tipos de empresa (idempotente)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    for code, label, family in NEW_TYPES:
        catalog.objects.update_or_create(
            code=code,
            defaults={
                "label": label, "domain": "COMPANY", "family": family,
                "tracks_expiry": False, "is_cumulative": True,
                "is_active": True,
            },
        )


def backwards(apps, schema_editor):
    """Borra los tipos (solo si ningún documento los usa: PROTECT)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.filter(code__in=[row[0] for row in NEW_TYPES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0179_extincion_nacimiento_types_s127"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
