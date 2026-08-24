# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0041_reasignar_css_domain_company_s64.py
"""
H30 (S64). Reasigna el dominio de CSS de PERSONAL a COMPANY (dato, via
RunPython), mismo patron que la migracion 0038 para PAGO_CORRIENTE.

CSS se dio de alta en la migracion 0003 con label "Certificado de
estar al corriente (Seguridad Social)" y domain=PERSONAL -- pero los
2 archivos reales encontrados bajo este codigo en S64
(document_type OK, domain pendiente, dry-run de
resolve_domain_pending_types) no son ese certificado en absoluto:
son "CONTRATO ENCOMIENDA AGG 27-12-17.pdf" y "CONTRATO ENCOMIENDA
GRUALDI 27-12-17.pdf" -- adhesiones al Contrato de Encomienda de
EpiCenter/Fundacion Estatal para la Formacion en el Empleo, firmadas
por el representante legal de la empresa (Jose Luis Alvarez Diaz),
con CIF/CNAE/cuenta de cotizacion de la propia empresa, no de un
trabajador concreto.

Miguel Angel, tras revisar el PDF real: "Si, si, lo pasamos a company
sin problemas." Mismo criterio ya aplicado a PAGO_CORRIENTE en S58:
tipo cuyo dominio real es de empresa, no de persona, aunque el
catalogo lo definiera originalmente como PERSONAL.

Nota, sin resolver en esta migracion (fuera de alcance de lo pedido):
el label original ("Certificado de estar al corriente...") no
describe el contenido real de estos 2 archivos -- posible
desactualizacion del label, a revisar en otra sesion si aparece mas
volumen real de este tipo.
"""
from django.db import migrations


def _reasignar_dominio_css(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(code="CSS").update(domain="COMPANY")


def _revertir_dominio_css(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(code="CSS").update(domain="PERSONAL")


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0040_seed_cert_limitaciones_s60"),
    ]

    operations = [
        migrations.RunPython(
            _reasignar_dominio_css,
            _revertir_dominio_css,
        ),
    ]
