# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/migrations/0005_remove_blind_cae_requirements_s156.py
"""
S156. Fuera los 4 requisitos «CAE ·» de la migración 0003: juntaban lo
que piden todas las plataformas y se asignaron a ciegas, así que daban
faltas que no lo son (Miguel Ángel: "¿qué sentido tiene mirar a ver si
el ciclomotor tiene o no tiene OCA pasada?"). El flujo bueno: el
requisito es el conjunto de documentos que pide un correo; se compara
con las máquinas o personas que nombra ese correo (pantalla Correos
CAE). Al borrarlos se van también sus asignaciones.
"""
from django.db import migrations

NAMES = (
    "CAE · Empresa", "CAE · Máquina", "CAE · Trabajador",
    "CAE · Trabajador Cellnex",
)


def remove(apps, schema_editor):
    JobPosition = apps.get_model("document_explorer", "JobPosition")
    JobPosition.objects.filter(name__in=NAMES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cae_mail", "0004_cae_machine_requirement_fix_s156"),
    ]

    operations = [
        migrations.RunPython(remove, migrations.RunPython.noop),
    ]
