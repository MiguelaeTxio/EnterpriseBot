# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0084_seed_autorizacion_generica_capacitacion_s105.py
"""
H35 (S105). Alta de 2 tipos documentales nuevos, confirmados con
muestra real (20 ficheros BAJA_PERSONAL de Jorge Ramirez Garcia,
DNI 53696300V, texto embebido + OCR Tesseract español) durante la
investigacion del punto 2 de la hoja de ruta S105 (ampliar
CONTENT_SIGNALS con los tipos nuevos detectados en S104).

- AUTORIZACION_GENERICA: confirmado con pk=32726 -- "AUTORIZACION
  / D. ADOLFO ALVAREZ DIAZ con DNI... como representante de la
  empresa TRANSGRUAL S.L. en calidad de GERENTE... AUTORIZO A: D.
  JORGE RAMIREZ GARCIA... Para el uso de los siguientes vehiculos
  y/o maquinaria relacionada". Distinto de AUTORIZACION_USO_
  MAQUINARIA (migracion 0004, ya existente): esta es una
  autorizacion generica de representacion/acceso, sin checklist de
  maquinaria concreta -- ese checklist es precisamente lo que
  distingue al pk=32724/32725 de esta misma sesion, que SI encajan
  en AUTORIZACION_USO_MAQUINARIA ya existente ("AUTORIZACION DE
  MANEJO DE MAQUINARIA", checklist Grua/Camion Pluma/Trailer).

- CAPACITACION: confirmado con pk=32728/32729 -- "CAPACITACION POR
  PARTE DE LA EMPRESA DE LAS ACTIVIDADES QUE PUEDE REALIZAR EL
  TRABAJADOR", listado numerado de actividades autorizadas
  (conduccion de grua, trabajos en altura...). Coincide letra por
  letra con la hipotesis del anexo H35 S104.

Ambos con tracks_expiry=False (declaraciones puntuales fechadas, sin
version "vigente" que sustituya a la anterior -- mismo criterio que
CAMBIO_IRPF/COMUNICACION_CONTRATO, migracion 0045/0046), domain
PERSONAL, family LABORAL (mismo grupo que CAMBIO_IRPF/
COMUNICACION_CONTRATO, por ser declaraciones administrativas de la
relacion laboral, no PRL/formacion tecnica).

Comprobado en el propio codigo (migraciones existentes) antes de
crear nada: CAMBIO_IRPF, COMUNICACION_CONTRATO, EPIS,
AUTORIZACION_USO_MAQUINARIA y TACOGRAFO ya existian en el catalogo
-- no se re-siembran aqui, solo les falta su entrada en
CONTENT_SIGNALS (ver document_explorer/personal_content_
classification.py, mismo commit).
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "AUTORIZACION_GENERICA",
        "label": "Autorización genérica de representación/acceso",
        "domain": "PERSONAL",
        "family": "LABORAL",
        "tracks_expiry": False,
    },
    {
        "code": "CAPACITACION",
        "label": "Capacitación de actividades por parte de la empresa",
        "domain": "PERSONAL",
        "family": "LABORAL",
        "tracks_expiry": False,
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
        ("document_explorer", "0083_personaldossiertemplate_person_to_company_s103"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
