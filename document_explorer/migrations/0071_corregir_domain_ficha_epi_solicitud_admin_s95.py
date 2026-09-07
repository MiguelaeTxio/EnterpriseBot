# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0071_corregir_domain_ficha_epi_solicitud_admin_s95.py
"""
H31 (S95). Auditoria real del campo domain (Punto 4 de la hoja de
ruta), dos correcciones confirmadas por Miguel Angel contra evidencia
real de uso (DocumentIndexEntry.domain_content_type):

- FICHA_TECNICA_EPI: PERSONAL -> EPI. Sus 7 entradas reales estan
  vinculadas al 100% a EpiItemCatalog, nunca a PersonIdentity.
  Verbatim Miguel Angel: "Evidentemente es una ficha tecnica de un
  EPI, el unico problema ha sido que venian de carpetas de personal.
  Deben quedar asignadas a su EPI."
- SOLICITUD_ADMINISTRATIVA: PERSONAL -> BOTH. Uso real: 161
  PersonIdentity + 24 MachineAsset -- proporcion demasiado alta para
  ser ruido aislado. Miguel Angel confirma que existen solicitudes
  administrativas reales sobre una maquina (p. ej. autorizacion para
  circular sin tacografo), no solo sobre una persona.

Pendiente, fuera de esta migracion (requiere inspeccionar los
documentos reales antes de poder reasignar su document_type, no es un
simple cambio de domain en el catalogo):
- BAJA_PERSONAL: 122 entradas reales vinculadas a MachineAsset estan
  mal tipadas -- deberian ser BAJA_DEFINITIVA/BAJA_TEMPORAL segun el
  caso. Confirmado por Miguel Angel ("hay que tipar bien las bajas de
  maquinaria en su lugar").
- RAE: 57 entradas reales vinculadas a PersonIdentity estan mal
  tipadas -- RAE es el Registro de Aparatos Elevadores de la Junta de
  Andalucia, exclusivo de maquinaria. Confirmado por Miguel Angel.
- CERTIFICADO_PODERES: declarado COMPANY pero su uso real es
  mayoritariamente MachineAsset (78) y nunca CompanyWorksite (0) --
  queda pendiente de revision, sin decision tomada todavia.
"""
from django.db import migrations


def correct_domains(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code="FICHA_TECNICA_EPI").update(
        domain="EPI",
    )
    DocumentTypeCatalog.objects.filter(code="SOLICITUD_ADMINISTRATIVA").update(
        domain="BOTH",
    )


def revert_domains(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code="FICHA_TECNICA_EPI").update(
        domain="PERSONAL",
    )
    DocumentTypeCatalog.objects.filter(code="SOLICITUD_ADMINISTRATIVA").update(
        domain="PERSONAL",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0070_documenttypecatalog_domain_epi_choice_s95"),
    ]

    operations = [
        migrations.RunPython(correct_domains, revert_domains),
    ]
