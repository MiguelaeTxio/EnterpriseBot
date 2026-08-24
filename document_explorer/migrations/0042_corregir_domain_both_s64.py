# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0042_corregir_domain_both_s64.py
"""
H30 (S64). Corrige el dominio de 4 tipos documentales que quedaron en
BOTH sin ninguna decision real detras -- domain=BOTH es el default
del propio campo del modelo (DocumentTypeCatalog.domain,
default=DOMAIN_BOTH), y estos 4 tipos se dieron de alta (migraciones
0004 y 0025) sin especificar dominio explicito, cayendo en ese
default por descuido, no por diseno.

Miguel Angel, verbatim (S64): "no puede haber documentos que liguen a
una persona con una determinada maquina, porque aqui nadie lleva una
maquina en exclusividad (...) un documento no puede ser a la vez para
una persona y para una maquina."

Confirmado con muestra real (S64, 6 archivos por tipo,
domain_object_id pendiente):
- SEGURO: 100% bajo DOC. MAQUINAS (barca, cabezas tractoras) -> MACHINE.
- CERTIFICADO_PODERES: 100% bajo DOC. MAQUINAS (mandato/poder de
  compra de vehiculo, DOC OFIAUTO, transferencias DOLLYS) -> MACHINE.
  (Distinto del "Certificado de poderes" pensado originalmente para
  representacion de empresa -- el uso real es documentacion de compra
  de maquinaria.)
- POLIZA_SEGURO: 100% bajo DOC. MAQUINAS (polizas R.C. Mapfre/
  Generali de maquinaria) -> MACHINE.
- TACOGRAFO: 100% bajo DOC. PERSONAL (solicitud de tarjeta de
  tacografo del conductor, PTE CONTRATACION) -> PERSONAL.

Mismo patron RunPython reversible que las migraciones 0038/0041.
"""
from django.db import migrations

_REASIGNACIONES = {
    "SEGURO": "MACHINE",
    "CERTIFICADO_PODERES": "MACHINE",
    "POLIZA_SEGURO": "MACHINE",
    "TACOGRAFO": "PERSONAL",
}


def _reasignar_dominios(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    for code, domain in _REASIGNACIONES.items():
        DocumentTypeCatalog.objects.filter(code=code).update(domain=domain)


def _revertir_dominios(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    for code in _REASIGNACIONES:
        DocumentTypeCatalog.objects.filter(code=code).update(domain="BOTH")


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0041_reasignar_css_domain_company_s64"),
    ]

    operations = [
        migrations.RunPython(
            _reasignar_dominios,
            _revertir_dominios,
        ),
    ]
