# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0029_seed_s50_new_types.py
"""
H30 (S50). Alta de 6 tipos documentales nuevos, todos confirmados por
Miguel Ángel con datos/documentos reales durante la sesión, tras
decidir explícitamente ("no queda más remedio, hay que añadirlos")
dejar de aplazar el alta para no bloquear Fase B1/OCR/Gemini con una
"selva documental" de tipos inexistentes.

- IEDMT: Impuesto Especial sobre Determinados Medios de Transporte
  (Modelo 06, Agencia Tributaria) -- el "impuesto de matriculación",
  estatal, pagado (o declarado exento, caso real que lo motivó:
  "A-69 IMPUESTO MEDIOS TRANSPORTES 06.pdf") UNA sola vez al
  matricular el vehículo. `tracks_expiry=False`: no se repite ni
  caduca.

- IVTM: Impuesto sobre Vehículos de Tracción Mecánica, autoliquidación
  municipal (caso real: "A-69 E-0124-BJL IVTA.pdf" -- el nombre de
  archivo real lleva la errata "IVTA", el contenido real del
  documento es IVTM). Confirmado con Miguel Ángel viendo el propio
  PDF: son dos impuestos reales distintos, nunca el mismo tipo.
  `tracks_expiry=True`: periódico, con plazo de pago propio cada
  ejercicio.

- CERT_EXENCION_PERMISO: certificado de exención de permiso (caso
  real: "Z-78 Cert.exencion perm 15-02-2021.pdf"). `tracks_expiry=
  True`, confirmado por Miguel Ángel tras consultar que este tipo de
  certificados suele tener vigencia limitada, no validez indefinida.

- SANCION_TRAFICO: sanción de tráfico (caso real: "Sancion 5462FJP
  2022 02 21 pagada.pdf"). `tracks_expiry=False` -- registro
  histórico de un hecho puntual, no un documento que caduque.

- CUADRO_AMORTIZACION: cuadro de amortización de préstamo/leasing
  (caso real: "BBVA 1723376 CUADRO AMORTIZACIÓN.pdf").
  `tracks_expiry=False`.

- GASTOS_TARJETA_COMBUSTIBLE: gasto de tarjeta de combustible (caso
  real: "Z92 gastos tarjeta gasoil SOLRED.pdf"). `tracks_expiry=
  False`.

Familias asignadas directamente en esta misma migración (campo
`family` ya existe desde la 0028, a diferencia de las altas de S49
que tuvieron que esperar a esa migración posterior).
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "IEDMT",
        "label": "Impuesto Especial sobre Determinados Medios de Transporte (Modelo 06)",
        "domain": "MACHINE",
        "family": "FINANCIERO",
        "tracks_expiry": False,
    },
    {
        "code": "IVTM",
        "label": "Impuesto sobre Vehículos de Tracción Mecánica (autoliquidación)",
        "domain": "MACHINE",
        "family": "FINANCIERO",
        "tracks_expiry": True,
    },
    {
        "code": "CERT_EXENCION_PERMISO",
        "label": "Certificado de exención de permiso",
        "domain": "MACHINE",
        "family": "CIRCULACION",
        "tracks_expiry": True,
    },
    {
        "code": "SANCION_TRAFICO",
        "label": "Sanción de tráfico",
        "domain": "MACHINE",
        "family": "CIRCULACION",
        "tracks_expiry": False,
    },
    {
        "code": "CUADRO_AMORTIZACION",
        "label": "Cuadro de amortización (préstamo/leasing)",
        "domain": "MACHINE",
        "family": "FINANCIERO",
        "tracks_expiry": False,
    },
    {
        "code": "GASTOS_TARJETA_COMBUSTIBLE",
        "label": "Gastos de tarjeta de combustible",
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
        ("document_explorer", "0028_add_family_and_backfill"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
