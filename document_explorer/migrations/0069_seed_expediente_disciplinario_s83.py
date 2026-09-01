# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0069_seed_expediente_disciplinario_s83.py
"""
H30 (S83). Alta de 1 tipo documental nuevo: EXPEDIENTE_DISCIPLINARIO.

Detectado en el Punto 2 de la hoja de ruta de H30 (el unico documento
EPIS que nunca llego a leerse en S82, id=36552,
"Indisciplina o desobediencia en el trabajo Art 52 7 epis.doc"). Tras
instalar el paquete de sistema que faltaba (libreoffice-writer, ver
SESSION_VARIABLES.md) y poder leerlo por fin, Miguel Angel confirmo
verbatim que es una notificacion real de falta muy grave, mal
clasificada como EPIS -- decidio explicitamente crear un tipo
documental propio en vez de dejarlo sin tipificar, para cubrir este y
futuros casos similares.

- domain=PERSONAL (notificacion a una persona concreta, nunca a una
  maquina).
- family=LABORAL, mismo criterio que CONTRATO/AUTONOMO (migraciones
  0028/0039): documento laboral, no de identidad ni de salud.
- tracks_expiry=False: un expediente disciplinario no caduca ni tiene
  una version "vigente" que sustituya a la anterior -- nunca participa
  en vigencia_service.evaluate_substitution().

La reclasificacion real del documento id=36552 (cambiar su
document_type de EPIS a este codigo nuevo) es una correccion de datos
puntual sobre una fila ya existente, fuera de alcance de esta
migracion (que solo siembra el catalogo) -- se hace aparte en la
misma sesion, Comando S sobre la BD real.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "EXPEDIENTE_DISCIPLINARIO",
        "label": "Expediente disciplinario / notificación de falta",
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
        ("document_explorer", "0068_seed_chaleco_chaqueton_chaqueta_trabajo_s83"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
