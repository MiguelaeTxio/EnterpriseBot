# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0162_requires_signature_s124.py
# H30 (S124): circulares que requieren firma certificada (Docuten).
# Marcadas de inicio las que son acuse de recibo o nombramiento firmado
# (su propio texto pide la firma del trabajador); las CIRCULAR_* son
# informativas y se quedan sin firma. Editable desde "Editar" circular.

from django.db import migrations, models

SIGNATURE_CODES = [
    "ENTREGA_INFORMACION",
    "INFORMACION_MEDIDAS_PROTECCION",
    "NOMBRAMIENTO_JEFE_MANIOBRAS",
    "NOMBRAMIENTO_RECURSO_PREVENTIVO",
    "NOMBRAMIENTO_RESPONSABLE_SEGURIDAD",
    "PLAN_ACTUACION_CALOR",
    "RECURSO_PREVENTIVO",
]


def mark_signature_circulars(apps, schema_editor):
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.filter(code__in=SIGNATURE_CODES).update(
        requires_signature=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('document_explorer', '0161_systemagentheartbeat_s123'),
    ]

    operations = [
        migrations.AddField(
            model_name='documenttypecatalog',
            name='requires_signature',
            field=models.BooleanField(default=False, help_text='H30 (S124). Solo las circulares marcadas aquí se envían a firmar por Docuten (Personal > Información > Preparar para Docuten). Miguel Ángel: "Docuten solo intervendrá en el caso que sea necesaria una firma certificada". El resto se envía directamente por WhatsApp/email.', verbose_name='Requiere firma certificada (Docuten)'),
        ),
        migrations.RunPython(
            mark_signature_circulars, migrations.RunPython.noop,
        ),
    ]
