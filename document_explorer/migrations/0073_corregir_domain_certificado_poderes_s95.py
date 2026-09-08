# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0073_corregir_domain_certificado_poderes_s95.py
"""
H31 (S95). Ultima correccion del Punto 4 (auditoria de domain vs uso
real): CERTIFICADO_PODERES tenia domain=COMPANY desde su alta
(0025_poliza_poderes_factura_terceros), asumiendo vinculacion a
CompanyWorksite -- el uso real (117 documentos) nunca la tiene (0
casos CompanyWorksite; 78 MachineAsset, 36 sin vincular, 3
PersonIdentity residuales).

Confirmado por contenido real (descarga directa del blob, nunca por
heuristica de nombre ni por el agregado de vinculacion en solitario):
son certificados de firma digital / mandatos de representacion de un
gestor administrativo para tramitar matriculacion o cambio de
titularidad de un vehiculo concreto, firmados por el representante de
turno de una de las empresas del grupo (GR=Gruas Adolfo Alvarez SL,
TR=Transgrual SL). El poder en si es de empresa, pero el documento se
genera y archiva siempre por y para la transaccion de un vehiculo
concreto -- nunca del ambito de una obra (CompanyWorksite). Miguel
Angel, verbatim: "Aplica" (tras revisar el contenido real de 4
ejemplos descargados).
"""
from django.db import migrations


def correct_domain(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code="CERTIFICADO_PODERES").update(
        domain="MACHINE",
    )


def revert_domain(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code="CERTIFICADO_PODERES").update(
        domain="COMPANY",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0072_seed_reforma_dgt_citacion_s95"),
    ]

    operations = [
        migrations.RunPython(correct_domain, revert_domain),
    ]
