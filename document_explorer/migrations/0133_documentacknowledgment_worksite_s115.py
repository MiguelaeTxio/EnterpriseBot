# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0133_documentacknowledgment_worksite_s115.py
"""
H31 (S115). Añade `DocumentAcknowledgment.worksite` (FK nula a la
nueva app `worksites.Worksite`), para que las circulares que
referencian una obra concreta (p. ej. NOMBRAMIENTO_JEFE_MANIOBRAS)
puedan resolver `{{obra.*}}` a datos reales -- ver deuda técnica 4.23
del documento maestro.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0132_documentacknowledgment_channel_s115"),
        ("worksites", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentacknowledgment",
            name="worksite",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="document_acknowledgments",
                to="worksites.worksite",
                verbose_name="Obra",
            ),
        ),
    ]
