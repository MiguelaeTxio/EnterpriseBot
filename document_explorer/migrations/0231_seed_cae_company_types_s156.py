# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0231_seed_cae_company_types_s156.py
"""
S156. Tipos documentales de EMPRESA que piden las plataformas de
coordinacion de actividades (egestiona, Cellnex, Nalanda, Quioo), sacados
de la carpeta "00 DOCUMENTACION MENSUAL 2026" de OneDrive. Miguel Angel:
"habra que crear subtipos y habra que subirlos al cubo".

Todos con `tracks_expiry=True` y `expires=False`: su fecha es la del
propio certificado o boletin (mensual), no una caducidad -- el vigente
es el ultimo. `PROCEDIMIENTOS_TRABAJO` no tiene fecha real.

El certificado de pago de salarios ya existe (PAGO_CORRIENTE) y el de
estar al corriente con la Seguridad Social de un trabajador (CSS, de
PERSONA) se deja como esta; aqui va el de la empresa.
"""
from django.db import migrations


CAE_TYPES = (
    ("TC1_EMPRESA", "Boletín de cotización TC1 (empresa)",
     "LABORAL", True),
    ("TC2_EMPRESA", "Relación nominal de trabajadores TC2 (empresa)",
     "LABORAL", True),
    ("RECIBO_LIQUIDACION_SS",
     "Recibo de liquidación de cotizaciones (Seguridad Social)",
     "LABORAL", True),
    ("ITA_EMPRESA", "ITA -- Informe de trabajadores en alta (empresa)",
     "LABORAL", True),
    ("VIDA_LABORAL_EMPRESA",
     "Vida laboral de la empresa (cuenta de cotización)",
     "LABORAL", True),
    ("CERT_CORRIENTE_SS_EMPRESA",
     "Certificado de estar al corriente con la Seguridad Social "
     "(empresa)",
     "LABORAL", True),
    ("CERT_ART42_TGSS",
     "Certificado del art. 42 ET de la TGSS (contratas)",
     "LABORAL", True),
    ("CERT_CORRIENTE_AEAT",
     "Certificado de estar al corriente con Hacienda (AEAT)",
     "FINANCIERO", True),
    ("CERT_CONTRATISTAS_AEAT",
     "Certificado de contratistas y subcontratistas (AEAT, nominativo)",
     "FINANCIERO", True),
    ("CERT_REA",
     "Certificado de inscripción en el REA (Registro de Empresas "
     "Acreditadas)",
     "ADMINISTRATIVO", True),
    ("RECIBO_IAE",
     "Recibo del Impuesto de Actividades Económicas (IAE)",
     "FINANCIERO", True),
    ("EVALUACION_RIESGOS_EMPRESA",
     "Evaluación de riesgos laborales de la empresa",
     "PRL_FORMACION", True),
    ("PLANIFICACION_PREVENTIVA",
     "Planificación de la actividad preventiva",
     "PRL_FORMACION", True),
    ("PLAN_PREVENCION", "Plan de prevención de riesgos laborales",
     "PRL_FORMACION", True),
    ("MEDIDAS_EMERGENCIA", "Medidas de emergencia",
     "PRL_FORMACION", True),
    ("PROCEDIMIENTOS_TRABAJO", "Procedimientos de trabajo",
     "PRL_FORMACION", False),
    ("CERT_SERVICIO_PREVENCION",
     "Certificado del servicio de prevención ajeno (concierto y pago)",
     "PRL_FORMACION", True),
    ("CERT_ASOCIACION_MUTUA", "Certificado de asociación a la mutua",
     "ADMINISTRATIVO", True),
)


def seed_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog")
    for code, label, family, tracks_expiry in CAE_TYPES:
        DocumentTypeCatalog.objects.get_or_create(
            code=code,
            defaults={
                "label": label,
                "domain": "COMPANY",
                "family": family,
                "tracks_expiry": tracks_expiry,
                "expires": False,
                "is_active": True,
            },
        )


def unseed_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(
        code__in=[row[0] for row in CAE_TYPES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0230_epidelivery_safety_dates_s163"),
    ]

    operations = [
        migrations.RunPython(seed_types, unseed_types),
    ]
