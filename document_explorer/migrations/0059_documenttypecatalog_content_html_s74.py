# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0059_documenttypecatalog_content_html_s74.py
"""
H31 (S74). Campo content_html en DocumentTypeCatalog -- cuerpo de
texto enriquecido para tipos documentales que son circulares o
notificaciones. Decisión explícita de Miguel Ángel (S73): campo NUEVO
en BD, manteniendo `current_template` (plantilla legacy en archivo)
en paralelo, no sustituyéndolo de golpe.

`blank=True, default=""` -- el catálogo tiene decenas de tipos
documentales físicos (ITV, seguros, DNIs...) que nunca tendrán cuerpo
de texto; se deja vacío por defecto para todos ellos, sin exigir
ningún valor por defecto real de negocio (caso 2.3 de com-migrations:
campo de texto, `blank=True`/`default=""` es la resolución obvia, no
hace falta un default distinto para las filas ya existentes).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0058_epiitemcatalog_standard_expiry_years_s73"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypecatalog",
            name="content_html",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="Contenido enriquecido (circular/notificación)",
                help_text=(
                    "H31 (S74). Cuerpo real de texto enriquecido (HTML "
                    "básico -- color, negrita, listas) para tipos "
                    "documentales que son circulares/notificaciones "
                    "(p. ej. CIRCULAR_INFORMATIVA, "
                    "NOMBRAMIENTO_RESPONSABLE_SEGURIDAD). Campo NUEVO "
                    "en BD, decisión explícita de Miguel Ángel (S73): "
                    "mantener `current_template` (plantilla legacy en "
                    "archivo) en paralelo, no sustituirlo de golpe. "
                    "Vacío por defecto -- solo se rellena para los "
                    "tipos que de verdad usan el CRUD de circulares de "
                    "H31; el resto del catálogo (tipos físicos/"
                    "documentales sin cuerpo de texto) lo deja en "
                    "blanco sin más. Mismo patrón que "
                    "`current_template`: campo directo en este modelo, "
                    "no un modelo aparte -- no hay necesidad de "
                    "versionado histórico por ahora."
                ),
            ),
        ),
    ]
