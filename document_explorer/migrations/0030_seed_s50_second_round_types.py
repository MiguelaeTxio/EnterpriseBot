# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0030_seed_s50_second_round_types.py
"""
H30 (S50), segunda ronda. Miguel Ángel, verbatim, tras la primera
ronda de 6 tipos (migración 0029): "no lo entiendo por qué hacemos
las cosas así [...] sacas un listado, son 80 palabras, pues las 80
[...] no podemos estar dejándonos en el camino documentos." Se
repasaron las 504 palabras reales con 3+ apariciones (no solo el top
80), no las 80 originales -- ver EnterpriseBot_048_GET.txt de la
sesión. La inmensa mayoría eran ruido real (nombres de empresa,
fragmentos de matrícula, correspondencia RGM ya cubierta por RAE,
artefactos de sistema) sin valor de tipo documental. Los siguientes 8
tipos SÍ tienen identidad real, confirmada con muestra descargada
directamente de GCS y extracción de texto real (ver
EnterpriseBot_046..049), no solo por nombre de archivo:

- CONTRATO_ARRENDAMIENTO: contrato real de alquiler de maquinaria
  entre empresas del grupo (caso real confirmado por texto extraído:
  "CONTRATO DE ARRENDAMIENTO DE MAQUINARIA" entre Grúas Adolfo Álvarez
  y Transgrual). Incluye también "RENTING" como variante -- mismo
  concepto de alquiler de vehículo/maquinaria bajo otro nombre
  comercial.

- CAMBIO_TITULARIDAD: solicitud de cambio de titularidad de vehículo
  (caso real confirmado por texto: "JUSTIFICANTE PROFESIONAL DE
  SOLICITUD DE CAMBIO DE TITULARIDAD", trámite DGT).

- CARTA_VERDE: certificado internacional de seguro del vehículo.
  Confirmado por Miguel Ángel verbatim: "la carta verde es el seguro
  internacional [...] lleva la fecha de caducidad del seguro, tiene la
  misma duración y caduca igual que la póliza" -- `tracks_expiry=True`.

- REVISION_ESLINGAS: revisión periódica de eslingas y elementos de
  izado (patrón real "REV.ESLINGAS Y ELEM.IZADO GC [fecha]", repetido
  por máquina con distintas fechas -- histórico de inspecciones).
  Miguel Ángel confirmó explícitamente `tracks_expiry=True`, mismo
  criterio que IPO/CERT_MANTENIMIENTO.

- GARANTIA_FABRICANTE: garantía de fabricante/concesionario (caso real
  confirmado: "Z-124 GARANTIA JLG.pdf", "GARANTIA AUTOCARE.pdf").
  `tracks_expiry=True` -- una garantía tiene periodo de cobertura real.

- INFORME_INCIDENCIAS: informe de incidencias de máquina (caso real
  confirmado: "Z106 INFORME DE INCIDENCIAS.docx", "Z-42 INFORME DE
  INCIDENCIAS.docx"). `tracks_expiry=False` -- registro puntual de un
  hecho, no un documento que caduque.

- PEDIDO_COMPRA: pedido de compra, distinto de la factura ya emitida
  (caso real confirmado: "MERCEDES Pedido Firmado.pdf", "MERCEDES
  Pedido a la firma.pdf"). `tracks_expiry=False`.

- PROVISION_FONDOS: autorización de provisión de fondos para compra/
  importación de maquinaria (caso real confirmado: "Autorizacion
  provision fondos [...] firmado.pdf", "Provision fondos gastos
  operacion firmada.pdf"). `tracks_expiry=False`.

Ninguno de los 8 se adivinó por nombre de archivo -- todos se
confirmaron con texto real extraído del PDF (pdftotext) o con
confirmación explícita de Miguel Ángel sobre el concepto.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "CONTRATO_ARRENDAMIENTO",
        "label": "Contrato de arrendamiento de maquinaria/vehículo",
        "domain": "MACHINE",
        "family": "FINANCIERO",
        "tracks_expiry": False,
    },
    {
        "code": "CAMBIO_TITULARIDAD",
        "label": "Solicitud de cambio de titularidad",
        "domain": "MACHINE",
        "family": "CIRCULACION",
        "tracks_expiry": False,
    },
    {
        "code": "CARTA_VERDE",
        "label": "Carta verde (certificado internacional de seguro)",
        "domain": "MACHINE",
        "family": "SEGUROS",
        "tracks_expiry": True,
    },
    {
        "code": "REVISION_ESLINGAS",
        "label": "Revisión de eslingas y elementos de izado",
        "domain": "MACHINE",
        "family": "TECNICA_SEGURIDAD",
        "tracks_expiry": True,
    },
    {
        "code": "GARANTIA_FABRICANTE",
        "label": "Garantía de fabricante/concesionario",
        "domain": "MACHINE",
        "family": "TECNICA_SEGURIDAD",
        "tracks_expiry": True,
    },
    {
        "code": "INFORME_INCIDENCIAS",
        "label": "Informe de incidencias",
        "domain": "MACHINE",
        "family": "TECNICA_SEGURIDAD",
        "tracks_expiry": False,
    },
    {
        "code": "PEDIDO_COMPRA",
        "label": "Pedido de compra",
        "domain": "MACHINE",
        "family": "FINANCIERO",
        "tracks_expiry": False,
    },
    {
        "code": "PROVISION_FONDOS",
        "label": "Autorización de provisión de fondos",
        "domain": "MACHINE",
        "family": "FINANCIERO",
        "tracks_expiry": False,
    },
]


def seed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    for spec in NEW_TYPES:
        DocumentTypeCatalog.objects.get_or_create(
            code=spec["code"],
            defaults={
                "label": spec["label"],
                "domain": spec["domain"],
                "family": spec["family"],
                "tracks_expiry": spec["tracks_expiry"],
                "is_active": True,
            },
        )


def unseed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(
        code__in=[spec["code"] for spec in NEW_TYPES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0029_seed_s50_new_types"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
