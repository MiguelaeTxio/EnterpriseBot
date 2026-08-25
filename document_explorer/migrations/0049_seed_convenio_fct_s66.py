# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0049_seed_convenio_fct_s66.py
"""
H30 (S66). Alta de CONVENIO_FCT, confirmado con contenido real:
"Gruas Alvarez - Delegacion.pdf" (DOC. PERSONAL/PERSONAL/TALLER/
CAÑAMERO NAVARRO, PABLO (GR)/CAÑAMERO NAVARRO, PABLO) es en realidad
un "Acuerdo de Colaboracion Formativa entre el Centro Docente y el
Centro de Trabajo" (Anexo IV CFP, Junta de Andalucia) para la
Formacion en Centros de Trabajo (FCT) de un alumno en practicas
(Pablo Cañamero Navarro, DNI 77670117Z, 2º FP Electromecanica de
Vehiculos, C.D.P. San Jose, periodo 19/03/21-24/06/21) con Gruas
Adolfo Alvarez SL como centro de trabajo colaborador.

No es CONTRATO (no es relacion laboral, el alumnado no percibe
retribucion, articulo 1 de las clausulas del propio documento) ni
FORMACION (no es formacion por horas de un trabajador ya contratado,
es un convenio de practicas de un centro educativo externo) --
ningun codigo existente del catalogo cerrado cubre este concepto.

Family LABORAL (mismo criterio que CONTRATO, migracion 0028 --
documento formal que fija la relacion entre la persona y el centro
de trabajo), domain PERSONAL (va ligado al alumno/trabajador en
practicas, confirmado por Miguel Angel en S66).
"""
from django.db import migrations

NEW_TYPE = {
    "code": "CONVENIO_FCT",
    "label": "Convenio de Formación en Centros de Trabajo (FCT)",
    "domain": "PERSONAL",
    "family": "LABORAL",
}


def seed_new_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.get_or_create(
        code=NEW_TYPE["code"],
        defaults={
            "label": NEW_TYPE["label"],
            "domain": NEW_TYPE["domain"],
            "family": NEW_TYPE["family"],
            "is_active": True,
        },
    )


def unseed_new_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code=NEW_TYPE["code"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0048_seed_s65_cuarto_lote"),
    ]

    operations = [
        migrations.RunPython(seed_new_type, unseed_new_type),
    ]
