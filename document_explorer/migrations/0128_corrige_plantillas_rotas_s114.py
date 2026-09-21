# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0128_corrige_plantillas_rotas_s114.py
"""
H31 (S114). Dos incidencias reales encontradas por Miguel Ángel al
revisar el listado de circulares corregido (0126):

1. `CIRCULAR_INFORMATIVA.current_template` apuntaba a
   `DocumentIndexEntry` id=23496 ("Circular Leave Letter.doc") --
   verificado visualmente por Miguel Ángel (captura de Word real):
   es una carta real de ANAGRUAL (agrupación empresarial de grúas),
   firmada por su secretario general, sobre el certificado "Leave
   Letter" de exención de tacógrafo -- NO es una circular de Grupo
   Álvarez, está mal atribuida a este tipo. (Nota: la lectura previa
   de esta sesión vía el conector de Drive había dado este archivo
   como "vacío" -- falso negativo real, el conector no extrae texto
   de `.doc` legacy de forma fiable; el contenido real solo se
   confirmó abriendo el archivo en Word.)

2. `RECURSO_PREVENTIVO.current_template` apuntaba a
   `DocumentIndexEntry` id=42920
   ("PLANTILLA_RECURSO_PREVENTIVO.docx") -- verificado con consulta
   real que esa fila tiene `deleted_at` no nulo (papelera desde
   2026-08-27), lo que produce un 404 real
   ("No DocumentIndexEntry matches the given query") al pulsar "Ver"
   desde el panel -- enlace roto a un archivo borrado.

Se limpia `current_template` (a NULL) en ambos -- ninguno de los dos
archivos reales se toca ni se borra, solo se desvincula la referencia
incorrecta/rota. La reversión restaura los IDs originales por si
hiciera falta deshacer.
"""
from django.db import migrations


def clear_broken_templates(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(
        code__in=["CIRCULAR_INFORMATIVA", "RECURSO_PREVENTIVO"],
    ).update(current_template=None)


def restore_templates(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(code="CIRCULAR_INFORMATIVA").update(current_template_id=23496)
    DocumentTypeCatalog.objects.filter(code="RECURSO_PREVENTIVO").update(current_template_id=42920)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0127_limpia_etiquetas_dominio_s114"),
    ]

    operations = [
        migrations.RunPython(
            clear_broken_templates, restore_templates,
        ),
    ]
