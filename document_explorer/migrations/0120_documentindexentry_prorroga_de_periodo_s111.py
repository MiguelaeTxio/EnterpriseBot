# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0120_documentindexentry_prorroga_de_periodo_s111.py
"""
H31 (S111). Añade `DocumentIndexEntry.prorroga_de` (FK a si mismo,
nullable) y `period_start_date`/`period_end_date`, para poder
representar una prorroga (o una transformacion a indefinido) como lo
que es -- una extension de un contrato existente, con su propio
periodo, en vez de forzarla a compartir el unico campo `issue_date`
con la fecha real de alta. La antiguedad real (`PersonIdentity.
hire_date`) se calcula recorriendo esta cadena hasta la raiz, nunca
duplicada en un campo propio.

Origen real: Martin Gonzalez Jesus (alta real 01/11/2006,
transformacion a indefinido 30/04/2007 -- dos fechas reales de un
mismo contrato que `issue_date` por si solo no podia distinguir). Ver
docstring completo de `prorroga_de` en models.py.

Solo esquema, ninguna fila sembrada -- las tres columnas quedan
vacias hasta que se enlacen las prorrogas ya identificadas.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0119_reasigna_ultimo_huerfano_s110"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentindexentry",
            name="prorroga_de",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prorrogas",
                to="document_explorer.documentindexentry",
                verbose_name="Prórroga del contrato",
            ),
        ),
        migrations.AddField(
            model_name="documentindexentry",
            name="period_start_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Inicio del periodo (prórroga)",
            ),
        ),
        migrations.AddField(
            model_name="documentindexentry",
            name="period_end_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Fin del periodo (prórroga)",
            ),
        ),
    ]
