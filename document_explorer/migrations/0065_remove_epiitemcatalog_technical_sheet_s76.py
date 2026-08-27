# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0065_remove_epiitemcatalog_technical_sheet_s76.py
"""
H31 (S76). Retira EpiItemCatalog.technical_sheet (añadido en la
migración 0064, en esta misma sesión) -- redundante: ya existía un
mecanismo real desde H30 S73 para vincular fichas técnicas/manuales
de EPI, vía el patrón genérico ya usado en toda la plataforma
(DocumentIndexEntry.domain_content_type/domain_object_id apuntando a
EpiItemCatalog), con 7 documentos reales ya vinculados así
(POLO_ALTA_VISIBILIDAD, PANTALON_ALTA_VISIBILIDAD,
CAMISETA_ALTA_VISIBILIDAD, ARNES_SEGURIDAD -- verificado contra BD
real en esta sesión). El campo `technical_sheet` (FK única) además
asumía un solo documento por EPI, cuando la realidad tiene varios
(ficha técnica + declaración de conformidad) -- el mecanismo genérico
ya soporta eso sin cambios.

Ningún dato real se pierde: el campo nunca llegó a rellenarse para
ningún EPI (verificado contra BD antes de esta migración).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0064_epiitemcatalog_technical_sheet_s76"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="epiitemcatalog",
            name="technical_sheet",
        ),
    ]
