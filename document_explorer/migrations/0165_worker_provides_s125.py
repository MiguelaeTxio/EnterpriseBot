# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0165_worker_provides_s125.py
# H30 (S125): tipos documentales que aporta el propio trabajador (el
# supervisor puede pedírselos por WhatsApp desde Avisos). Marcados de
# inicio, con los códigos reales verificados por consulta en S125: DNI,
# permiso de conducción (CARNET_CONDUCIR), tarjeta de conductor
# (TACOGRAFO, nombre visible "Tarjeta de Conductor"), tarjeta de la
# Seguridad Social (SEG_SOCIAL) y tarjeta sanitaria. CONTRATO y
# RECONOCIMIENTO_MEDICO quedan sin marcar. Editable desde el Catálogo.

from django.db import migrations, models

WORKER_PROVIDES_CODES = [
    "DNI",
    "CARNET_CONDUCIR",
    "TACOGRAFO",
    "SEG_SOCIAL",
    "TARJETA_SANITARIA",
]


def mark_worker_provided_types(apps, schema_editor):
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.filter(code__in=WORKER_PROVIDES_CODES).update(
        worker_provides=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('document_explorer', '0164_medidas_proteccion_obra_s124'),
    ]

    operations = [
        migrations.AddField(
            model_name='documenttypecatalog',
            name='worker_provides',
            field=models.BooleanField(default=False, help_text='H30 (S125). Documentos que el propio trabajador puede aportar (DNI, permiso de conducción, tarjeta de conductor, tarjeta de la Seguridad Social, tarjeta sanitaria y similares). Solo para estos tipos el supervisor puede, desde Avisos, pedírselos por WhatsApp para que conteste con una foto o un PDF. Nunca lo que depende de la empresa (contrato, reconocimiento médico). Editable desde el Catálogo de tipos.', verbose_name='Lo aporta el trabajador'),
        ),
        migrations.RunPython(
            mark_worker_provided_types, migrations.RunPython.noop,
        ),
    ]
