# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0098_seed_cuestionario_pacto_justificante_s109.py
"""
H36 (S109). Alta de 3 tipos documentales nuevos, decision explicita de
Miguel Angel al revisar contenido real de documentos que hoy llevan el
tipo generico FORMACION y NO son un certificado de curso -- mismo
patron de "cajon de sastre" que motivo H35 con BAJA_PERSONAL, aqui a
menor escala.

CUESTIONARIO_FORMACION: confirmado con muestra real (pk=24414/24415/
24419/24422/24424, varios trabajadores) -- el contenido real es un
cuestionario de evaluacion de una formacion puntual (COVID-19: vias de
entrada, sintomas, distancia de seguridad...), nunca el certificado de
un curso tecnico. Domain PERSONAL, family PRL_FORMACION (mismo grupo
que FORMACION -- es documentacion del mismo proceso formativo, solo
que es el cuestionario, no el certificado). tracks_expiry False (un
cuestionario no caduca). is_cumulative True: una persona puede
responder varios cuestionarios de formaciones puntuales distintas a lo
largo del tiempo.

PACTO_PERMANENCIA: confirmado con muestra real (pk=24670/24671,
CASTILLA_NAVARRO_FRANCISCO_MIGUEL) -- el contenido real es un pacto de
permanencia en la empresa ("REUNIDOS: De una parte... la EMPRESA... Y
de otra..."), documento legal ligado a una formacion bonificada, nunca
el propio certificado del curso. Domain PERSONAL, family LABORAL
(documento laboral/contractual, no de formacion en si). tracks_expiry
True: un pacto de permanencia tiene un periodo de vigencia real, mismo
criterio que CONTRATO ("puede tener o no fecha de caducidad").
is_cumulative True: una persona puede tener mas de un pacto real a lo
largo del tiempo (formaciones bonificadas distintas), ninguno sustituye
al anterior.

JUSTIFICANTE_PAGO_PERSONAL: confirmado con muestra real (pk=24296,
RAMIREZ_GARCIA_JORGE) -- el contenido real es un justificante de
transferencia bancaria real (Cajamar, "DETALE DE LA OPERACION" --
artefacto real de OCR, falta una L -- "ORDENANTE", "CUENTA DESTINO",
concepto "cap. Jorge Ramirez Garcia"), nunca un certificado de curso.
Domain PERSONAL, family FINANCIERO (mismo family que
FACTURA_SERVICIOS_PERSONAL, migracion 0093, pero es un justificante de
pago, no una factura -- documentos reales distintos aunque relacionados).
tracks_expiry False. is_cumulative True: mismo criterio que
FACTURA_SERVICIOS_PERSONAL.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "CUESTIONARIO_FORMACION",
        "label": "Cuestionario de evaluación de una formación puntual",
        "domain": "PERSONAL",
        "family": "PRL_FORMACION",
        "tracks_expiry": False,
        "is_cumulative": True,
    },
    {
        "code": "PACTO_PERMANENCIA",
        "label": "Pacto de permanencia en la empresa (ligado a formación bonificada)",
        "domain": "PERSONAL",
        "family": "LABORAL",
        "tracks_expiry": True,
        "is_cumulative": True,
    },
    {
        "code": "JUSTIFICANTE_PAGO_PERSONAL",
        "label": "Justificante de pago/transferencia a nombre de un trabajador",
        "domain": "PERSONAL",
        "family": "FINANCIERO",
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
        ("document_explorer", "0097_seed_formacion_tipos_curso_s109"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
