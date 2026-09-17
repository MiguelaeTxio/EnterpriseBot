# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0095_seed_factura_informe_empresa_s108.py
"""
H35 (S108). Alta de 2 tipos documentales nuevos, dominio COMPANY
(CompanyWorksite), decision explicita de Miguel Angel durante el
cierre del punto 5 (barrido de otra persona): 3 documentos
(pk=30077, 39829, 27197) no solo estaban mal tipados dentro de la
ficha de una persona -- el contenido no es de esa persona en
absoluto, es de la EMPRESA entera, exactamente el mismo patron por el
que nacio CompanyWorksite en H30/S58 (ver su docstring en models.py).

FACTURA_SERVICIOS_EMPRESA: confirmado con 2 muestras reales (pk=30077,
39829) -- facturas de Correos (Sociedad Estatal Correos y Telegrafos)
por servicios postales a nombre de TRANSGRUAL/GRUAS ADOLFO ALVAREZ,
nunca de un trabajador concreto. Domain COMPANY, family FINANCIERO
(mismo family que FACTURA_SERVICIOS_PERSONAL, migracion 0093, pero
domain distinto). tracks_expiry False. is_cumulative True: la empresa
recibe facturas de forma recurrente, ninguna sustituye a la anterior.

INFORME_ACCIDENTES_EMPRESA: confirmado con 1 muestra real (pk=27197)
-- "RELACION DE ACCIDENTES DE TRABAJO OCURRIDOS... SIN BAJA MEDICA",
informe agregado MENSUAL de toda la empresa (Delt@), no de un
trabajador. Domain COMPANY, family LABORAL (mismo family que
PAGO_CORRIENTE). tracks_expiry False. is_cumulative True: un informe
por mes, todos coexisten.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "FACTURA_SERVICIOS_EMPRESA",
        "label": "Factura de servicios a nombre de la empresa (no de un trabajador)",
        "domain": "COMPANY",
        "family": "FINANCIERO",
        "tracks_expiry": False,
        "is_cumulative": True,
    },
    {
        "code": "INFORME_ACCIDENTES_EMPRESA",
        "label": "Informe/relación agregada de accidentes de toda la empresa (mensual)",
        "domain": "COMPANY",
        "family": "LABORAL",
        "tracks_expiry": False,
        "is_cumulative": True,
    },
]


def seed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    for spec in NEW_TYPES:
        DocumentTypeCatalog.objects.get_or_create(
            code=spec["code"],
            defaults={
                "label": spec["label"],
                "domain": spec["domain"],
                "family": spec["family"],
                "tracks_expiry": spec["tracks_expiry"],
                "is_cumulative": spec["is_cumulative"],
                "is_active": True,
            },
        )


def unseed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=[spec["code"] for spec in NEW_TYPES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0094_seed_informacion_riesgos_prl_terceros_s108"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
