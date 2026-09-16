# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0094_seed_informacion_riesgos_prl_terceros_s108.py
"""
H35 (S108). Alta de 1 tipo documental nuevo, confirmado con 14 muestras
reales durante el punto 2 de la hoja de ruta de S107 (INVESTIGACION_
ACCIDENTE, 72 IDs pendientes).

INFORMACION_RIESGOS_PRL_TERCEROS: dos plantillas reales, ninguna es una
investigacion de accidente, ambas son la misma idea funcional --
constancia de que el trabajador recibio informacion/documentacion de
riesgos PRL de un TERCERO (cliente/obra) antes de acceder a sus
instalaciones, nunca una investigacion propia de un accidente real:

1. "CERTIFICADO DE INFORMACION DE LOS RIESGOS DE LAS INSTALACIONES DE
   ENDESA" (pk=27031/27032/27037/27038/27039/27040/27047/27048/27049/
   27050, 10 muestras) -- Grupo Alvarez/Transgrual certificando ante
   Endesa que el trabajador recibio informacion de riesgos para
   acceder a sus subestaciones (Art. 18 LPRL).
2. "INFORMACION Y ENTREGA DEL PLAN DE SEGURIDAD Y SALUD A TRABAJADORES"
   (pk=27068/27078/27082/27087, 4 muestras) -- F.C.C. Construccion
   entregando copia del Plan de Seguridad y Salud de una obra concreta
   (Autovia del Mediterraneo) al trabajador.

Domain PERSONAL (vive en la ficha del trabajador que recibe la
informacion), family PRL_FORMACION (mismo grupo que FORMACION_PRL_
GENERICA/CAPACITACION/RECURSO_PREVENTIVO). tracks_expiry False (no
caduca, es un hecho puntual de una obra/cliente concreto). is_cumulative
True: un trabajador puede acumular varios de estos a lo largo del
tiempo (una obra distinta, un cliente distinto), ninguno sustituye al
anterior.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "INFORMACION_RIESGOS_PRL_TERCEROS",
        "label": "Información de riesgos PRL entregada por cliente/obra",
        "domain": "PERSONAL",
        "family": "PRL_FORMACION",
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
        ("document_explorer", "0093_seed_factura_servicios_citacion_rm_s108"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
