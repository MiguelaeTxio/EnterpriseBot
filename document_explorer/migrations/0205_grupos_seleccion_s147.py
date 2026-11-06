# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0205_grupos_seleccion_s147.py
"""
H24 (S147 invasora). "Grupos de reparto" are now "Grupos de selección".

---

Solo nombres visibles (Miguel Ángel: "grupos de selección, que es más
acorde con lo que hace"). Sin cambios en la base de datos.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0204_justificante_asistencia_medica_s147"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="persongrouptemplate",
            options={
                "ordering": ["name"],
                "verbose_name": "Grupo de selección",
                "verbose_name_plural": "Grupos de selección",
            },
        ),
        migrations.AlterField(
            model_name="noticerecipientscope",
            name="personal_groups",
            field=models.ManyToManyField(
                blank=True, related_name="notice_scopes",
                to="document_explorer.persongrouptemplate",
                verbose_name="Grupos de selección",
            ),
        ),
    ]
