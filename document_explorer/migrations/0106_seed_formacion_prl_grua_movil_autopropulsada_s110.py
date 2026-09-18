# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0106_seed_formacion_prl_grua_movil_autopropulsada_s110.py
"""
H36 (S110). Alta de un 17o tipo de curso real, encontrado al revisar
la muestra del grupo mayoritario de ambiguos de FORMACION (20 de 52):
"PRL para grua movil autopropulsada" -- choca con CARNET_GRUISTA
(menciona "grua movil" en el titulo) y con FORMACION_PRL_ART_18_19
(mismo boilerplate legal de siempre), pero es un curso real distinto
de ambos, confirmado con 2 muestras reales:

- pk=34124, "FORM.PRL GRUA MOVIL AUT. ALVAREZ GEA 6-11-15.pdf"
- pk=36061, "FORM.PRL GRUA MOV.AUT.HIDALGO ROSAS 23-10-17.pdf"
  (esta ultima en carpeta OBSOLETOS)

Mismos criterios que el resto de tipos de FORMACION_* (0097): domain
PERSONAL, family PRL_FORMACION, tracks_expiry True, is_cumulative
True.

Nota aparte, sin resolver en esta migracion: la mitad de la muestra
de este grupo (pk=35313, pk=40315) son certificados combinados
reales "GRUA MOVIL AUT+CAMION AUT" en un mismo PDF -- esos quedan
correctamente ambiguos para decision manual, no se fuerza ningun
CONTENT_WINS entre este tipo nuevo y FORMACION_OPERADOR_CAMION_AUTOCARGANTE.
"""
from django.db import migrations


def seed_new_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.get_or_create(
        code="FORMACION_PRL_GRUA_MOVIL_AUTOPROPULSADA",
        defaults={
            "label": "Formación PRL grúa móvil autopropulsada",
            "domain": "PERSONAL",
            "family": "PRL_FORMACION",
            "tracks_expiry": True,
            "is_cumulative": True,
            "is_active": True,
        },
    )


def unseed_new_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code="FORMACION_PRL_GRUA_MOVIL_AUTOPROPULSADA",
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0105_carnet_gruista_skip_light_ocr_engines_s110"),
    ]

    operations = [
        migrations.RunPython(seed_new_type, unseed_new_type),
    ]
