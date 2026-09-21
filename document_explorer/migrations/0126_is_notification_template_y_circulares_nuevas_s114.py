# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0126_is_notification_template_y_circulares_nuevas_s114.py
"""
H31 (S114). Corrección real de scope: el CRUD de circulares
(panel:circulars_list) y el selector de envío de notificación
filtraban por `domain` (PERSONAL/BOTH/COMPANY) -- eso listaba el
catálogo ENTERO de documentos de persona (DNI, nóminas,
reconocimientos médicos, cursos de formación...), no una lista de
plantillas de comunicación reutilizables. Miguel Ángel, tras ver la
pantalla real con las ~73 filas del catálogo completo, verbatim:
"eso es un galimatías [...] ahí están prácticamente todos los
documentos habidos y por haber. No es eso lo que queremos hacer
[...] aquí vamos a tener unas 10, 15, 20 plantillas como mucho".

Esta migración:
1. Añade `is_notification_template` (Boolean, False por defecto) --
   único criterio real a partir de ahora para decidir qué aparece en
   el CRUD de circulares y en el selector de envío, sustituyendo el
   filtro por `domain`.
2. Marca como True los tipos ya existentes que SÍ son plantillas de
   comunicación reales, confirmados contra uso histórico real
   (DocumentAcknowledgment, consulta de solo lectura de esta misma
   sesión): CIRCULAR_INFORMATIVA (1 circular real archivada,
   "CIRCULAR INFORMATIVA PERMISO CONDUCIR"), ENTREGA_INFORMACION (51
   usos históricos), PLAN_ACTUACION_CALOR (8 usos),
   INFORMACION_MEDIDAS_PROTECCION (ya con plantilla en archivo),
   RECURSO_PREVENTIVO (57 usos), NOMBRAMIENTO_RESPONSABLE_SEGURIDAD
   (4 usos), NOMBRAMIENTO_JEFE_MANIOBRAS (1 uso),
   NOMBRAMIENTO_RECURSO_PREVENTIVO. El resto del catálogo (~65 tipos
   de documento de persona -- DNI, contratos, formación, salud...)
   se queda en False, tal cual pidió Miguel Ángel.
3. Crea 4 tipos nuevos, pedidos explícitamente por Miguel Ángel como
   ejemplos reales de plantilla que todavía no existían en el
   catálogo (cambio de horario, cierre de instalaciones, evento de
   empresa, protocolo de actuación ante una circunstancia concreta)
   -- domain=COMPANY/family=ADMINISTRATIVO, mismo criterio que
   CIRCULAR_INFORMATIVA, is_notification_template=True,
   content_html vacío (se redacta después, uno a uno, desde el
   propio CRUD).

Deliberadamente NO toca EPIS -- Miguel Ángel: "las de entrega de EPIs
las vamos a tener marcadas en entrega de EPIs [...] de los EPIs nos
olvidamos" -- ese flujo ya tiene su propio mecanismo
(EpiDeliveryBatchTemplate), no pasa por is_notification_template.
"""
from django.db import migrations, models

_EXISTING_TEMPLATE_CODES = [
    "CIRCULAR_INFORMATIVA",
    "ENTREGA_INFORMACION",
    "PLAN_ACTUACION_CALOR",
    "INFORMACION_MEDIDAS_PROTECCION",
    "RECURSO_PREVENTIVO",
    "NOMBRAMIENTO_RESPONSABLE_SEGURIDAD",
    "NOMBRAMIENTO_JEFE_MANIOBRAS",
    "NOMBRAMIENTO_RECURSO_PREVENTIVO",
]

_NEW_TEMPLATES = [
    {
        "code": "CIRCULAR_CAMBIO_HORARIO",
        "label": "Circular de cambio de horario",
    },
    {
        "code": "CIRCULAR_CIERRE_INSTALACIONES",
        "label": "Circular de cierre de instalaciones",
    },
    {
        "code": "CIRCULAR_EVENTO_EMPRESA",
        "label": "Circular de evento de empresa",
    },
    {
        "code": "CIRCULAR_PROTOCOLO_ACTUACION",
        "label": "Circular de protocolo de actuación",
    },
]


def seed_notification_templates(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")

    DocumentTypeCatalog.objects.filter(
        code__in=_EXISTING_TEMPLATE_CODES,
    ).update(is_notification_template=True)

    for entry in _NEW_TEMPLATES:
        DocumentTypeCatalog.objects.get_or_create(
            code=entry["code"],
            defaults={
                "label": entry["label"],
                "domain": "COMPANY",
                "family": "ADMINISTRATIVO",
                "is_active": True,
                "is_notification_template": True,
            },
        )


def unseed_notification_templates(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")

    DocumentTypeCatalog.objects.filter(
        code__in=_EXISTING_TEMPLATE_CODES,
    ).update(is_notification_template=False)

    DocumentTypeCatalog.objects.filter(
        code__in=[entry["code"] for entry in _NEW_TEMPLATES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0125_rename_job_position_a_requisitos_documentacion_s113"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypecatalog",
            name="is_notification_template",
            field=models.BooleanField(
                default=False,
                verbose_name="Plantilla de comunicación (circular/notificación)",
            ),
        ),
        migrations.RunPython(
            seed_notification_templates, unseed_notification_templates,
        ),
    ]
