# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0028_add_family_and_backfill.py
"""
H30 (S49). Campo `family` en `DocumentTypeCatalog` -- agrupación del
acordeón de la ficha (en vez de solo Vigentes/Histórico) y base de la
búsqueda granular ("ver el seguro de esta máquina"). Decisión de
Miguel Ángel: campo real en el modelo (no calculado en la vista) y
lista fija de choices en código (no tabla configurable aparte).

Backfill de las 37 filas reales del catálogo cerrado a fecha de esta
migración, agrupadas según la propuesta confirmada por Miguel Ángel
en S49. Distinta de la familia normativa de máquina (A/B/Z/H/MK/P/T/
V/S de fleet.MachineAsset, cerrada al inicio de esta misma sesión)
-- esta agrupa TIPOS DOCUMENTALES para la interfaz, esa otra dice qué
documentos son obligatorios por tipo de máquina.
"""
from django.db import migrations, models


FAMILY_BY_CODE = {
    # -- Circulación --
    "FICHA_TECNICA": "CIRCULACION",
    "PERMISO_CIRCULACION": "CIRCULACION",
    "ITV": "CIRCULACION",
    "ITC": "CIRCULACION",
    "OCA": "CIRCULACION",
    "CERT_NO_TARJ_TTES": "CIRCULACION",
    "TARJETA_TRANSPORTE": "CIRCULACION",
    "TACOGRAFO": "CIRCULACION",
    # -- Técnica y seguridad --
    "CE": "TECNICA_SEGURIDAD",
    "C_ADECUACION": "TECNICA_SEGURIDAD",
    "CERT_MANTENIMIENTO": "TECNICA_SEGURIDAD",
    "CERT_REVISION": "TECNICA_SEGURIDAD",
    "LIBRO_HISTORIAL": "TECNICA_SEGURIDAD",
    "TABLA_DE_CARGA": "TECNICA_SEGURIDAD",
    "MANUAL_USO": "TECNICA_SEGURIDAD",
    "IPO": "TECNICA_SEGURIDAD",
    "RAE": "TECNICA_SEGURIDAD",
    "CERT_ACCESORIO_ELEVACION": "TECNICA_SEGURIDAD",
    # -- Seguros --
    "SEGURO": "SEGUROS",
    "POLIZA_SEGURO": "SEGUROS",
    # -- Financiero y compraventa --
    "LEASING": "FINANCIERO",
    "RECIBO_LEASING": "FINANCIERO",
    "PRESTAMO": "FINANCIERO",
    "FACTURA_COMPRA": "FINANCIERO",
    "FACTURA_TERCEROS": "FINANCIERO",
    "PROFORMA": "FINANCIERO",
    "DOC_VENTA": "FINANCIERO",
    "CONTRATO_COMPRAVENTA": "FINANCIERO",
    "ALBARAN_ENTREGA": "FINANCIERO",
    # -- Bajas de máquina --
    "BAJA_TEMPORAL": "BAJAS_MAQUINA",
    "BAJA_DEFINITIVA": "BAJAS_MAQUINA",
    "DOC_BAJA_DEFINITIVA": "BAJAS_MAQUINA",
    # -- Administrativo --
    "CERTIFICADO_PODERES": "ADMINISTRATIVO",
    "MANDATO": "ADMINISTRATIVO",
    "SOLICITUD_ADMINISTRATIVA": "ADMINISTRATIVO",
    # -- Identidad y personal (base) --
    "DNI": "IDENTIDAD_PERSONAL",
    "SEG_SOCIAL": "IDENTIDAD_PERSONAL",
    "CARNET_CONDUCIR": "IDENTIDAD_PERSONAL",
    "CAP": "IDENTIDAD_PERSONAL",
    # -- Laboral --
    "CONTRATO": "LABORAL",
    "ALTA": "LABORAL",
    "BAJA_PERSONAL": "LABORAL",
    "EXCEDENCIA": "LABORAL",
    "NOMINA": "LABORAL",
    "PAGO_CORRIENTE": "LABORAL",
    "IDC": "LABORAL",
    "CSS": "LABORAL",
    "VACACIONES": "LABORAL",
    "MOD_145": "LABORAL",
    # -- Salud y bajas de persona --
    "RECONOCIMIENTO_MEDICO": "SALUD_BAJAS_PERSONA",
    "ALTA_MEDICA": "SALUD_BAJAS_PERSONA",
    "PARTE_BAJA_MEDICA": "SALUD_BAJAS_PERSONA",
    "INVESTIGACION_ACCIDENTE": "SALUD_BAJAS_PERSONA",
    # -- PRL y formación --
    "EPIS": "PRL_FORMACION",
    "ENTREGA_INFORMACION": "PRL_FORMACION",
    "FORMACION": "PRL_FORMACION",
    "CURSO": "PRL_FORMACION",
    "AUTORIZACION_USO_MAQUINARIA": "PRL_FORMACION",
    "ESTIBA_PLATAFORMAS": "PRL_FORMACION",
}


def backfill_family(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    unmatched = []
    for entry in DocumentTypeCatalog.objects.all():
        family = FAMILY_BY_CODE.get(entry.code)
        if family is None:
            unmatched.append(entry.code)
            continue
        entry.family = family
        entry.save(update_fields=["family"])
    if unmatched:
        # No detiene el despliegue -- deja constancia en el log del
        # Action para revisión manual (código nuevo dado de alta
        # entre S49 y el momento del deploy, no cubierto por el mapa
        # de esta migración).
        print(
            "AVISO 0028: códigos sin familia asignada (revisar a mano): "
            + ", ".join(unmatched)
        )


def noop_reverse(apps, schema_editor):
    """No se revierte el backfill -- family queda en blanco, no se pierde nada más."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0027_seed_albaran_entrega"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypecatalog",
            name="family",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CIRCULACION", "Circulación"),
                    ("TECNICA_SEGURIDAD", "Técnica y seguridad"),
                    ("SEGUROS", "Seguros"),
                    ("FINANCIERO", "Financiero y compraventa"),
                    ("BAJAS_MAQUINA", "Bajas de máquina"),
                    ("ADMINISTRATIVO", "Administrativo"),
                    ("IDENTIDAD_PERSONAL", "Identidad y personal (base)"),
                    ("LABORAL", "Laboral"),
                    ("SALUD_BAJAS_PERSONA", "Salud y bajas de persona"),
                    ("PRL_FORMACION", "PRL y formación"),
                ],
                max_length=32,
                help_text=(
                    "H30 (S49). Agrupación del acordeón de la ficha "
                    "(en vez de solo Vigentes/Histórico) y base de la "
                    "búsqueda granular ('ver el seguro de esta "
                    "máquina'). Lista fija de choices en código (a "
                    "diferencia de tracks_expiry/ocr_unreliable) "
                    "porque las familias son un puñado estable de "
                    "categorías, no crecen sesión a sesión como los "
                    "tipos documentales -- decisión explícita de "
                    "Miguel Ángel (S49). Distinta de la familia "
                    "normativa de máquina (A/B/Z/H/MK/P/T/V/S de "
                    "fleet.MachineAsset): esta agrupa TIPOS "
                    "DOCUMENTALES para la interfaz, esa otra dice qué "
                    "documentos son obligatorios por tipo de máquina."
                ),
                verbose_name="Familia de documento",
            ),
        ),
        migrations.RunPython(backfill_family, noop_reverse),
    ]
