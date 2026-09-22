# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0134_circulares_obra_variable_s115.py
"""
H31 (S115). Sustituye el hueco literal "en la obra ____________________"
(20 guiones bajos, heredado del documento de ejemplo original, pensado
para rellenarse a mano en papel) por la variable real {{obra.nombre}}
en las dos plantillas que lo llevaban -- NOMBRAMIENTO_JEFE_MANIOBRAS y
NOMBRAMIENTO_RESPONSABLE_SEGURIDAD -- ahora que existe el modelo real
worksites.Worksite (ver deuda técnica 4.23 del documento maestro) para
resolverla contra datos reales vía _render_document_variables.

Reversible: la reversa restaura el guion bajo original tal cual.
"""
from django.db import migrations

_BLANK = "____________________"
_TOKEN = "{{obra.nombre}}"
_AFFECTED_CODES = ["NOMBRAMIENTO_JEFE_MANIOBRAS", "NOMBRAMIENTO_RESPONSABLE_SEGURIDAD"]


def add_obra_token(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    for code in _AFFECTED_CODES:
        dt = DocumentTypeCatalog.objects.filter(code=code).first()
        if dt is not None and _BLANK in dt.content_html:
            dt.content_html = dt.content_html.replace(_BLANK, _TOKEN)
            dt.save(update_fields=["content_html"])


def restore_blank(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    for code in _AFFECTED_CODES:
        dt = DocumentTypeCatalog.objects.filter(code=code).first()
        if dt is not None and _TOKEN in dt.content_html:
            dt.content_html = dt.content_html.replace(_TOKEN, _BLANK)
            dt.save(update_fields=["content_html"])


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0133_documentacknowledgment_worksite_s115"),
    ]

    operations = [
        migrations.RunPython(add_obra_token, restore_blank),
    ]
